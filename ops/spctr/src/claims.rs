//! Number claims for `spctr doc build`.
//!
//! A report cites a number as `{claim:key}`, or another report's number as
//! `{claim:<document-id>:key}`. Each claim lives in the `claims.json` next to
//! its report.md and names the JSON artifacts it was read from. Every build
//! re-reads those artifacts, so a changed file, a drifted value or a withdrawn
//! claim stops the build instead of reaching a reader.

use anyhow::{bail, Context, Result};
use camino::{Utf8Path, Utf8PathBuf};
use regex_lite::Regex;
use serde::{Deserialize, Deserializer, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fmt::Write as _;
use std::fs;

pub const FILE: &str = "claims.json";

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Claim {
    value: String,
    display: String,
    sources: Vec<Source>,
    run: String,
    verified: String,
    status: Status,
    engine_ids: Option<Vec<String>>,
    #[allow(clippy::option_option)]
    #[serde(default, deserialize_with = "present")]
    superseded_by: Option<Option<String>>,
    reason: Option<String>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Source {
    path: String,
    pointer: String,
    sha256: String,
    format: Option<Format>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Format {
    digits: Option<usize>,
    #[serde(default)]
    percent: bool,
    #[serde(default)]
    thousands: bool,
}

#[derive(Debug, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
enum Status {
    Current,
    Withdrawn,
}

/// Distinguishes an explicit `"superseded_by": null` from a missing field,
/// because a withdrawn claim must say whether anything replaces it.
#[allow(clippy::option_option)]
fn present<'de, D: Deserializer<'de>>(d: D) -> Result<Option<Option<String>>, D::Error> {
    Option::<String>::deserialize(d).map(Some)
}

/// What the report template needs to render one cited claim.
#[derive(Debug, Serialize, PartialEq, Eq)]
pub struct Resolved {
    pub value: String,
    pub run: String,
    pub engine_ids: Vec<String>,
    pub sources: Vec<String>,
    pub verified: String,
}

pub struct Expanded {
    pub markdown: String,
    /// Keyed by the reference as written, `key` or `document-id:key`.
    pub claims: BTreeMap<String, Resolved>,
}

const KEY: &str = "[a-z0-9][a-z0-9-]*";

/// Replaces every claim reference in `markdown` with a `[value]{claim=ref}`
/// span after checking the claim against its sources.
pub fn expand(dir: &Utf8Path, markdown: &str) -> Result<Expanded> {
    let reference = Regex::new(&format!(r"\{{claim:(?:({KEY}):)?({KEY})\}}")).expect("valid regex");
    let mut ledgers: BTreeMap<Utf8PathBuf, BTreeMap<String, Claim>> = BTreeMap::new();
    let mut claims = BTreeMap::new();
    let mut out = String::with_capacity(markdown.len());
    let mut last = 0;
    for found in reference.captures_iter(markdown) {
        let whole = found.get(0).expect("match");
        let text = &markdown[last..whole.start()];
        check_no_malformed(text)?;
        out.push_str(text);
        last = whole.end();
        let key = &found[2];
        let (name, owner) = match found.get(1) {
            Some(document) => (
                format!("{}:{key}", document.as_str()),
                report_dir(dir, document.as_str())?,
            ),
            None => (key.to_owned(), dir.to_owned()),
        };
        if !ledgers.contains_key(&owner) {
            let ledger = load(&owner)?;
            verify_current(&owner, &ledger)?;
            ledgers.insert(owner.clone(), ledger);
        }
        let claim = ledgers[&owner].get(key).with_context(|| {
            format!(
                "{} cites claim '{name}', but {} has no key '{key}'",
                dir.join("report.md"),
                owner.join(FILE)
            )
        })?;
        if claim.status == Status::Withdrawn {
            let successor = match claim.superseded_by.as_ref().and_then(Option::as_deref) {
                Some(next) => format!("cite {{claim:{next}}} instead"),
                None => "nothing supersedes it".to_owned(),
            };
            bail!(
                "{} cites withdrawn claim '{name}' ({}); {successor}",
                dir.join("report.md"),
                claim.reason.as_deref().expect("checked on load")
            );
        }
        write!(out, "[{}]{{claim={name}}}", escape_markdown(&claim.value))
            .expect("writing to a String");
        claims.entry(name).or_insert_with(|| Resolved {
            value: claim.value.clone(),
            run: claim.run.clone(),
            engine_ids: claim.engine_ids.clone().unwrap_or_default(),
            sources: claim
                .sources
                .iter()
                .map(|s| format!("{}#{}", s.path, s.pointer))
                .collect(),
            verified: claim.verified.clone(),
        });
    }
    check_no_malformed(&markdown[last..])?;
    out.push_str(&markdown[last..]);
    if claims.is_empty() && dir.join(FILE).is_file() {
        verify_current(dir, &load(dir)?)?;
    }
    Ok(Expanded {
        markdown: out,
        claims,
    })
}

fn check_no_malformed(text: &str) -> Result<()> {
    if let Some(at) = text.find("{claim") {
        let tail: String = text[at..].chars().take(60).collect();
        bail!("malformed claim reference {tail:?}; write {{claim:key}} or {{claim:document-id:key}} with lowercase keys");
    }
    Ok(())
}

/// Loads a claims file and checks every entry's shape, so a malformed claim
/// fails even when no report cites it yet.
fn load(dir: &Utf8Path) -> Result<BTreeMap<String, Claim>> {
    let path = dir.join(FILE);
    let text = fs::read_to_string(&path).with_context(|| format!("failed to read {path}"))?;
    let ledger: BTreeMap<String, Claim> = serde_json::from_str(&text)
        .with_context(|| format!("{path} is not a valid claims file"))?;
    let key = Regex::new(&format!("^{KEY}$")).expect("valid regex");
    let successor = Regex::new(&format!("^{KEY}:{KEY}$")).expect("valid regex");
    for (name, claim) in &ledger {
        let at = format!("{path}: claim '{name}'");
        if !key.is_match(name) {
            bail!("{at}: keys use lowercase letters, digits and hyphens");
        }
        if claim.sources.is_empty() {
            bail!("{at}: needs at least one source");
        }
        if claim.run.trim().is_empty() {
            bail!("{at}: run is empty");
        }
        chrono::NaiveDate::parse_from_str(&claim.verified, "%Y-%m-%d").with_context(|| {
            format!(
                "{at}: verified must be a YYYY-MM-DD date, found {:?}",
                claim.verified
            )
        })?;
        if let Some(ids) = &claim.engine_ids {
            if ids.is_empty() || ids.iter().any(|id| id.trim().is_empty()) {
                bail!("{at}: engine_ids must be a non-empty list of ids; drop the field when the run has none");
            }
        }
        for source in &claim.sources {
            if Utf8Path::new(&source.path).is_absolute()
                || Utf8Path::new(&source.path).extension() != Some("json")
            {
                bail!("{at}: source path must be a .json file relative to the report directory, found {:?}", source.path);
            }
            if !source.pointer.starts_with('/') {
                bail!(
                    "{at}: pointer must be an RFC 6901 pointer starting with '/', found {:?}",
                    source.pointer
                );
            }
            if source.sha256.len() != 64
                || !source
                    .sha256
                    .bytes()
                    .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
            {
                bail!("{at}: sha256 must be 64 lowercase hex digits");
            }
        }
        placeholders(&claim.display, claim.sources.len()).with_context(|| at.clone())?;
        match claim.status {
            Status::Current => {
                if claim.superseded_by.is_some() || claim.reason.is_some() {
                    bail!("{at}: only withdrawn claims carry superseded_by and reason");
                }
            }
            Status::Withdrawn => {
                let Some(next) = &claim.superseded_by else {
                    bail!("{at}: a withdrawn claim needs superseded_by, a document-id:key or null");
                };
                if let Some(next) = next {
                    if !successor.is_match(next) {
                        bail!("{at}: superseded_by must be document-id:key, found {next:?}");
                    }
                }
                if claim.reason.as_deref().is_none_or(|r| r.trim().is_empty()) {
                    bail!("{at}: a withdrawn claim needs a reason");
                }
            }
        }
    }
    Ok(ledger)
}

/// Re-reads the sources of every current claim. A withdrawn claim keeps its
/// receipt as history; its source may have moved on, which is why it was withdrawn.
fn verify_current(dir: &Utf8Path, ledger: &BTreeMap<String, Claim>) -> Result<()> {
    let mut files: BTreeMap<String, (String, Value)> = BTreeMap::new();
    for (name, claim) in ledger.iter().filter(|(_, c)| c.status == Status::Current) {
        let at = format!("{}: claim '{name}'", dir.join(FILE));
        let mut values = Vec::new();
        for source in &claim.sources {
            if !files.contains_key(&source.path) {
                let path = dir.join(&source.path);
                let bytes =
                    fs::read(&path).with_context(|| format!("{at}: failed to read {path}"))?;
                let json = serde_json::from_slice(&bytes)
                    .with_context(|| format!("{at}: {path} is not JSON"))?;
                files.insert(
                    source.path.clone(),
                    (format!("{:x}", Sha256::digest(&bytes)), json),
                );
            }
            let (hash, json) = &files[&source.path];
            if *hash != source.sha256 {
                bail!(
                    "{at}: {} changed since the claim was verified (sha256 {hash}, recorded {}); re-check the number and update the claim",
                    source.path,
                    source.sha256
                );
            }
            let value = json.pointer(&source.pointer).with_context(|| {
                format!("{at}: {} has nothing at {}", source.path, source.pointer)
            })?;
            values.push(
                format_value(value, source.format.as_ref())
                    .with_context(|| format!("{at}: {}#{}", source.path, source.pointer))?,
            );
        }
        let shown = fill(&claim.display, &values);
        if shown != claim.value {
            bail!(
                "{at}: sources give {shown:?}, but the claim records {:?}",
                claim.value
            );
        }
    }
    Ok(())
}

/// Finds the sibling report directory whose `report.md` has this `document_id`.
fn report_dir(dir: &Utf8Path, document_id: &str) -> Result<Utf8PathBuf> {
    #[derive(Deserialize)]
    struct Front {
        document_id: Option<String>,
    }
    let parent = dir
        .parent()
        .with_context(|| format!("{dir} has no parent directory"))?;
    let mut found = Vec::new();
    for entry in fs::read_dir(parent).with_context(|| format!("failed to list {parent}"))? {
        let candidate = Utf8PathBuf::try_from(entry?.path())?;
        let source = candidate.join("report.md");
        if !source.is_file() {
            continue;
        }
        let text =
            fs::read_to_string(&source).with_context(|| format!("failed to read {source}"))?;
        let Some(data) = gray_matter::Matter::<gray_matter::engine::YAML>::new()
            .parse(&text)
            .data
        else {
            continue;
        };
        let front: Front = data
            .deserialize()
            .with_context(|| format!("{source}: document_id must be a string"))?;
        if front.document_id.as_deref() == Some(document_id) {
            found.push(candidate);
        }
    }
    match found.len() {
        1 => Ok(found.remove(0)),
        0 => bail!("no report under {parent} has document_id '{document_id}'"),
        _ => bail!("several reports under {parent} have document_id '{document_id}': {found:?}"),
    }
}

/// Checks that `display` uses each source exactly through `{0}`..`{n-1}` and
/// no other braces, so every source shows up in the number a reader sees.
fn placeholders(display: &str, sources: usize) -> Result<()> {
    let mut used = vec![false; sources];
    let mut rest = display;
    while let Some(open) = rest.find(['{', '}']) {
        let tail = &rest[open..];
        let close = tail.find('}').filter(|_| tail.starts_with('{'));
        let index = close.and_then(|c| tail[1..c].parse::<usize>().ok());
        match (close, index) {
            (Some(close), Some(index)) if index < sources => {
                used[index] = true;
                rest = &tail[close + 1..];
            }
            _ => bail!(
                "display {display:?} may contain only {{0}}..{{{}}} placeholders",
                sources - 1
            ),
        }
    }
    if let Some(unused) = used.iter().position(|u| !u) {
        bail!("display {display:?} never shows source {{{unused}}}");
    }
    Ok(())
}

fn fill(display: &str, values: &[String]) -> String {
    let mut out = display.to_owned();
    for (i, value) in values.iter().enumerate() {
        out = out.replace(&format!("{{{i}}}"), value);
    }
    out
}

fn format_value(value: &Value, format: Option<&Format>) -> Result<String> {
    match (value, format) {
        (Value::String(text), None) => Ok(text.clone()),
        (Value::String(_), Some(_)) => bail!("format applies only to numbers"),
        (Value::Number(number), None) => Ok(number.to_string()),
        (Value::Number(number), Some(format)) => {
            let text = match (format.digits, format.percent) {
                (Some(digits), percent) => {
                    let x = number.as_f64().expect("JSON numbers are finite");
                    format!("{:.digits$}", if percent { x * 100.0 } else { x })
                }
                (None, true) => {
                    bail!("percent needs digits, because x100 of a float has no exact decimal form")
                }
                (None, false) => number.to_string(),
            };
            let text = if format.thousands { group(&text) } else { text };
            Ok(if format.percent {
                format!("{text}%")
            } else {
                text
            })
        }
        (other, _) => bail!("value must be a number or a string, found {other}"),
    }
}

fn group(text: &str) -> String {
    let (sign, digits) = text
        .strip_prefix('-')
        .map_or(("", text), |rest| ("-", rest));
    let (whole, fraction) = digits
        .split_once('.')
        .map_or((digits, None), |(w, f)| (w, Some(f)));
    let mut grouped = String::new();
    for (i, c) in whole.chars().enumerate() {
        if i > 0 && (whole.len() - i) % 3 == 0 {
            grouped.push(',');
        }
        grouped.push(c);
    }
    match fraction {
        Some(fraction) => format!("{sign}{grouped}.{fraction}"),
        None => format!("{sign}{grouped}"),
    }
}

fn escape_markdown(value: &str) -> String {
    let mut out = String::with_capacity(value.len());
    for c in value.chars() {
        if r"\[]*_`<>$^~@#|&{}".contains(c) {
            out.push('\\');
        }
        out.push(c);
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn sha(bytes: &[u8]) -> String {
        format!("{:x}", Sha256::digest(bytes))
    }

    type Change = fn(&mut Value);

    struct Fixture {
        _temp: tempfile::TempDir,
        root: Utf8PathBuf,
    }

    impl Fixture {
        fn new() -> Self {
            let temp = tempfile::tempdir().unwrap();
            let root = Utf8PathBuf::try_from(temp.path().to_owned()).unwrap();
            Self { _temp: temp, root }
        }

        fn report(
            &self,
            name: &str,
            document_id: &str,
            artifact: &Value,
            claims: &Value,
        ) -> Utf8PathBuf {
            let dir = self.root.join(name);
            fs::create_dir_all(dir.join("assets")).unwrap();
            fs::write(
                dir.join("report.md"),
                format!("---\ndocument_id: {document_id}\n---\n"),
            )
            .unwrap();
            fs::write(dir.join("assets/derived.json"), artifact.to_string()).unwrap();
            fs::write(dir.join(FILE), claims.to_string()).unwrap();
            dir
        }
    }

    fn artifact() -> Value {
        json!({"closed": 367, "total": 1064, "share": 0.344_924, "label": "rw", "nested": {"a/b": 12}})
    }

    fn claim(value: &str, display: &str, sources: &[(&str, Value)]) -> Value {
        let bytes = artifact().to_string();
        json!({
            "value": value,
            "display": display,
            "sources": sources.iter().map(|(pointer, format)| {
                let mut s = json!({"path": "assets/derived.json", "pointer": pointer, "sha256": sha(bytes.as_bytes())});
                if !format.is_null() { s["format"] = format.clone(); }
                s
            }).collect::<Vec<_>>(),
            "run": "wonton-postfix-001",
            "verified": "2026-11-14",
            "status": "current",
        })
    }

    fn recovered() -> Value {
        claim(
            "367 of 1,064",
            "{0} of {1}",
            &[
                ("/closed", Value::Null),
                ("/total", json!({"thousands": true})),
            ],
        )
    }

    fn error(result: Result<Expanded>) -> String {
        format!("{:#}", result.err().expect("expected an error"))
    }

    #[test]
    fn expands_local_and_cross_report_claims() {
        let f = Fixture::new();
        let mut ledger = json!({"recovered": recovered()});
        ledger["engine-share"] = claim(
            "34.5%",
            "{0}",
            &[("/share", json!({"digits": 1, "percent": true}))],
        );
        ledger["engine-share"]["engine_ids"] = json!(["reprover-7f3a"]);
        f.report(
            "other",
            "wonton-other",
            &artifact(),
            &json!({"label": claim("rw", "{0}", &[("/label", Value::Null)])}),
        );
        let dir = f.report("main", "wonton-main", &artifact(), &ledger);
        let out = expand(&dir, "A {claim:recovered} B {claim:engine-share} C {claim:wonton-other:label} D {claim:recovered}").unwrap();
        assert_eq!(
            out.markdown,
            "A [367 of 1,064]{claim=recovered} B [34.5%]{claim=engine-share} C [rw]{claim=wonton-other:label} D [367 of 1,064]{claim=recovered}"
        );
        assert_eq!(out.claims.len(), 3);
        assert_eq!(out.claims["engine-share"].engine_ids, vec!["reprover-7f3a"]);
        assert_eq!(
            out.claims["recovered"].sources,
            vec!["assets/derived.json#/closed", "assets/derived.json#/total"]
        );
        assert_eq!(out.claims["wonton-other:label"].run, "wonton-postfix-001");
    }

    #[test]
    fn pointers_follow_rfc_6901_escapes() {
        let f = Fixture::new();
        let dir = f.report(
            "main",
            "m",
            &artifact(),
            &json!({"n": claim("12", "{0}", &[("/nested/a~1b", Value::Null)])}),
        );
        assert_eq!(expand(&dir, "{claim:n}").unwrap().markdown, "[12]{claim=n}");
    }

    #[test]
    fn changed_source_fails() {
        let f = Fixture::new();
        let dir = f.report("main", "m", &artifact(), &json!({"recovered": recovered()}));
        fs::write(
            dir.join("assets/derived.json"),
            json!({"closed": 367, "total": 1064, "extra": 1}).to_string(),
        )
        .unwrap();
        assert!(error(expand(&dir, "{claim:recovered}"))
            .contains("assets/derived.json changed since the claim was verified"));
    }

    #[test]
    fn drifted_value_fails() {
        let f = Fixture::new();
        let mut c = recovered();
        c["value"] = json!("367 of 1064");
        let dir = f.report("main", "m", &artifact(), &json!({"recovered": c}));
        assert!(error(expand(&dir, "{claim:recovered}"))
            .contains(r#"sources give "367 of 1,064", but the claim records "367 of 1064""#));
    }

    #[test]
    fn missing_key_fails() {
        let f = Fixture::new();
        let dir = f.report("main", "m", &artifact(), &json!({"recovered": recovered()}));
        assert!(error(expand(&dir, "{claim:recoverd}")).contains("has no key 'recoverd'"));
    }

    #[test]
    fn missing_pointer_fails() {
        let f = Fixture::new();
        let dir = f.report(
            "main",
            "m",
            &artifact(),
            &json!({"n": claim("1", "{0}", &[("/absent", Value::Null)])}),
        );
        assert!(error(expand(&dir, "{claim:n}")).contains("has nothing at /absent"));
    }

    #[test]
    fn withdrawn_claim_fails_and_names_its_successor() {
        let f = Fixture::new();
        let mut old = claim("0.725", "{0}", &[("/share", json!({"digits": 3}))]);
        old["status"] = json!("withdrawn");
        old["superseded_by"] = json!("wonton-main:recovered");
        old["reason"] = json!("the shape features leaked the label");
        old["sources"][0]["sha256"] = json!("0".repeat(64));
        let dir = f.report(
            "main",
            "wonton-main",
            &artifact(),
            &json!({"recovered": recovered(), "r2": old}),
        );
        let message = error(expand(&dir, "{claim:r2}"));
        assert!(message.contains("cites withdrawn claim 'r2' (the shape features leaked the label); cite {claim:wonton-main:recovered} instead"), "{message}");
        let mut orphan = old.clone();
        orphan["superseded_by"] = Value::Null;
        fs::write(dir.join(FILE), json!({"r2": orphan}).to_string()).unwrap();
        assert!(error(expand(&dir, "{claim:r2}")).contains("nothing supersedes it"));
    }

    #[test]
    fn stale_uncited_claim_still_fails() {
        let f = Fixture::new();
        let mut c = recovered();
        c["value"] = json!("368 of 1,064");
        let dir = f.report("main", "m", &artifact(), &json!({"recovered": c}));
        assert!(error(expand(&dir, "no claims cited")).contains("but the claim records"));
    }

    #[test]
    fn malformed_reference_fails() {
        let f = Fixture::new();
        let dir = f.report("main", "m", &artifact(), &json!({"recovered": recovered()}));
        assert!(error(expand(&dir, "{claim:Recovered}")).contains("malformed claim reference"));
        assert!(error(expand(&dir, "{claims:recovered}")).contains("malformed claim reference"));
    }

    #[test]
    fn unknown_cross_report_fails() {
        let f = Fixture::new();
        let dir = f.report("main", "m", &artifact(), &json!({"recovered": recovered()}));
        assert!(
            error(expand(&dir, "{claim:nowhere:recovered}")).contains("has document_id 'nowhere'")
        );
    }

    #[test]
    fn claim_shapes_are_checked() {
        let f = Fixture::new();
        let cases: Vec<(Change, &str)> = vec![
            (|c| c["colour"] = json!("red"), "unknown field `colour`"),
            (|c| c["status"] = json!("draft"), "unknown variant `draft`"),
            (
                |c| c["verified"] = json!("14 Nov"),
                "verified must be a YYYY-MM-DD date",
            ),
            (
                |c| c["engine_ids"] = json!([]),
                "engine_ids must be a non-empty list",
            ),
            (|c| c["display"] = json!("{0}"), "never shows source {1}"),
            (|c| c["display"] = json!("{0} of {2}"), "placeholders"),
            (
                |c| c["sources"][0]["path"] = json!("/abs/x.json"),
                "relative to the report directory",
            ),
            (|c| c["sources"][0]["pointer"] = json!("closed"), "RFC 6901"),
            (|c| c["reason"] = json!("x"), "only withdrawn claims"),
            (|c| c["status"] = json!("withdrawn"), "needs superseded_by"),
            (
                |c| {
                    c["status"] = json!("withdrawn");
                    c["superseded_by"] = Value::Null;
                },
                "needs a reason",
            ),
            (
                |c| c["sources"][0]["format"] = json!({"percent": true}),
                "percent needs digits",
            ),
        ];
        for (change, expected) in cases {
            let mut c = recovered();
            change(&mut c);
            let dir = f.report("main", "m", &artifact(), &json!({"recovered": c}));
            let message = error(expand(&dir, "{claim:recovered}"));
            assert!(
                message.contains(expected),
                "expected {expected:?} in {message}"
            );
        }
    }

    #[test]
    fn formats_numbers() {
        let digits = |d, percent, thousands| Format {
            digits: d,
            percent,
            thousands,
        };
        assert_eq!(
            format_value(&json!(1_234_567), Some(&digits(None, false, true))).unwrap(),
            "1,234,567"
        );
        assert_eq!(
            format_value(&json!(-1234.5), Some(&digits(Some(2), false, true))).unwrap(),
            "-1,234.50"
        );
        assert_eq!(
            format_value(&json!(0.0381), Some(&digits(Some(3), false, false))).unwrap(),
            "0.038"
        );
        assert_eq!(
            format_value(&json!(0.25), Some(&digits(Some(0), true, false))).unwrap(),
            "25%"
        );
        assert_eq!(format_value(&json!(0.725), None).unwrap(), "0.725");
        assert!(format_value(&json!(true), None).is_err());
        assert!(format_value(&json!("x"), Some(&digits(Some(1), false, false))).is_err());
    }

    #[test]
    fn values_are_escaped_for_markdown() {
        assert_eq!(escape_markdown("a*b_[c]"), r"a\*b\_\[c\]");
    }
}
