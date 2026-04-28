use anyhow::{bail, Context, Result};
use camino::{Utf8Path, Utf8PathBuf};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, HashMap, HashSet};

use crate::manifest::{self, ProjectManifest};

const REGISTRY_FILE: &str = "spctr-registry.json";

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Registry {
    pub version: u32,
    pub counters: BTreeMap<String, u32>,
    pub series: BTreeMap<String, SeriesEntry>,
    pub docs: BTreeMap<String, DocSeries>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SeriesEntry {
    pub slug: String,
    pub title: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DocSeries {
    pub next_counter: u32,
    pub entries: BTreeMap<String, String>,
}

pub fn registry_path(repo_root: &Utf8Path) -> Utf8PathBuf {
    repo_root.join(REGISTRY_FILE)
}

pub fn load_registry(repo_root: &Utf8Path) -> Result<Registry> {
    let path = registry_path(repo_root);
    let text =
        std::fs::read_to_string(&path).with_context(|| format!("failed to read {}", path))?;
    let reg: Registry =
        serde_json::from_str(&text).with_context(|| format!("invalid JSON in {REGISTRY_FILE}"))?;
    validate_registry(&reg)?;
    Ok(reg)
}

pub fn save_registry(repo_root: &Utf8Path, registry: &Registry) -> Result<()> {
    let path = registry_path(repo_root);
    let text = serde_json::to_string_pretty(registry)? + "\n";
    std::fs::write(&path, &text).with_context(|| format!("failed to write {}", path))?;
    Ok(())
}

fn validate_registry(reg: &Registry) -> Result<()> {
    if reg.version != 1 {
        bail!("{REGISTRY_FILE}: unsupported version {}", reg.version);
    }

    for (key, _) in &reg.counters {
        if key != "D" && key != "A" && key != "B" {
            bail!("{REGISTRY_FILE}: unknown counter key '{key}'");
        }
    }

    let mut slugs_by_type: HashMap<&str, HashSet<&str>> = HashMap::new();
    for (series_id, entry) in &reg.series {
        validate_series_id(series_id)?;
        let type_key = &series_id[..1];
        if !slugs_by_type
            .entry(type_key)
            .or_default()
            .insert(&entry.slug)
        {
            bail!(
                "{REGISTRY_FILE}: duplicate slug '{}' within {type_key}-series",
                entry.slug
            );
        }
    }

    let mut all_doc_ids: HashSet<&str> = HashSet::new();
    for (series_id, doc_series) in &reg.docs {
        if !reg.series.contains_key(series_id) {
            bail!("{REGISTRY_FILE}: docs references unknown series '{series_id}'");
        }

        let mut max_seq: u32 = 0;
        for (_, doc_id) in &doc_series.entries {
            validate_doc_id(doc_id, series_id)?;
            if !all_doc_ids.insert(doc_id) {
                bail!("{REGISTRY_FILE}: duplicate doc id '{doc_id}'");
            }
            let seq = parse_doc_seq(doc_id)?;
            if seq > max_seq {
                max_seq = seq;
            }
        }

        if doc_series.next_counter <= max_seq {
            bail!(
                "{REGISTRY_FILE}: {series_id} next_counter ({}) must be > max existing seq ({max_seq})",
                doc_series.next_counter
            );
        }
    }

    Ok(())
}

fn validate_series_id(id: &str) -> Result<()> {
    let valid = (id.starts_with("D-") || id.starts_with("A-") || id.starts_with("B-"))
        && id.len() >= 5
        && id[2..].chars().all(|c| c.is_ascii_digit());
    if !valid {
        bail!("{REGISTRY_FILE}: invalid series id '{id}' (expected e.g. D-001)");
    }
    Ok(())
}

fn validate_doc_id(doc_id: &str, series_id: &str) -> Result<()> {
    let prefix = format!("{series_id}.");
    if !doc_id.starts_with(&prefix) {
        bail!("{REGISTRY_FILE}: doc id '{doc_id}' must start with '{prefix}'");
    }
    let seq_part = &doc_id[prefix.len()..];
    if seq_part.len() < 3 || !seq_part.chars().all(|c| c.is_ascii_digit()) {
        bail!("{REGISTRY_FILE}: doc id '{doc_id}' has invalid sequence part");
    }
    Ok(())
}

fn parse_doc_seq(doc_id: &str) -> Result<u32> {
    let seq_str = doc_id
        .rsplit('.')
        .next()
        .ok_or_else(|| anyhow::anyhow!("invalid doc id '{doc_id}'"))?;
    seq_str
        .parse::<u32>()
        .with_context(|| format!("invalid doc id sequence in '{doc_id}'"))
}

pub fn validate_manifest_consistency(
    registry: &Registry,
    manifests: &[ProjectManifest],
) -> Result<()> {
    let slug_to_series: BTreeMap<&str, &str> = registry
        .series
        .iter()
        .map(|(sid, entry)| (entry.slug.as_str(), sid.as_str()))
        .collect();

    for manifest in manifests {
        let Some(ref manifest_series) = manifest.series else {
            continue;
        };
        match slug_to_series.get(manifest.slug.as_str()) {
            None => bail!(
                "{}: series '{}' declared but slug '{}' not in registry",
                manifest.path,
                manifest_series,
                manifest.slug
            ),
            Some(&expected) if expected != manifest_series.as_str() => bail!(
                "{}: series mismatch: manifest says '{}' but registry says '{expected}'",
                manifest.path,
                manifest_series
            ),
            _ => {}
        }
    }

    Ok(())
}

pub fn series_for_slug<'a>(
    registry: &'a Registry,
    type_prefix: &str,
    slug: &str,
) -> Option<&'a str> {
    registry
        .series
        .iter()
        .find(|(sid, entry)| sid.starts_with(type_prefix) && entry.slug == slug)
        .map(|(sid, _)| sid.as_str())
}

pub fn doc_id_for_slug<'a>(
    registry: &'a Registry,
    series_id: &str,
    doc_slug: &str,
) -> Option<&'a str> {
    registry
        .docs
        .get(series_id)
        .and_then(|doc_series| doc_series.entries.get(doc_slug))
        .map(String::as_str)
}

pub fn allocate_series(
    registry: &mut Registry,
    kind: &str,
    slug: &str,
    title: &str,
) -> Result<String> {
    let type_key = match kind {
        "dossier" => "D",
        "addendum" => "A",
        "article" => "B",
        _ => bail!("unknown project kind '{kind}'"),
    };

    for (sid, entry) in &registry.series {
        if entry.slug == slug && sid.starts_with(type_key) {
            bail!("slug '{slug}' already has a {type_key}-series assignment");
        }
    }

    let counter = registry.counters.entry(type_key.to_owned()).or_insert(1);
    let series_id = format!("{type_key}-{counter:03}");
    *counter += 1;

    registry.series.insert(
        series_id.clone(),
        SeriesEntry {
            slug: slug.to_owned(),
            title: title.to_owned(),
        },
    );

    Ok(series_id)
}

#[derive(Debug, Serialize)]
struct SeriesAssignResult {
    series_id: String,
    kind: String,
    slug: String,
}

pub fn series_assign(repo_root: &Utf8Path, kind: &str, slug: &str, json: bool) -> Result<()> {
    let parent_dir = match kind {
        "dossier" => "dossiers",
        "addendum" => "addenda",
        _ => bail!("unknown project kind '{kind}'"),
    };

    let manifest_path = repo_root.join(parent_dir).join(slug).join("spctr.toml");
    if !manifest_path.is_file() {
        bail!("manifest not found: {}", manifest_path);
    }

    let loaded = manifest::load_project_manifest(&manifest_path, None)?;

    if loaded.series.is_some() {
        bail!(
            "{} already has series = {:?}",
            manifest_path,
            loaded.series.unwrap()
        );
    }

    let mut reg = load_registry(repo_root)?;
    let series_id = allocate_series(&mut reg, kind, slug, &loaded.title)?;
    save_registry(repo_root, &reg)?;

    let toml_text = std::fs::read_to_string(&manifest_path)?;
    let patched = crate::series::patch_toml_series(&toml_text, &series_id)?;
    std::fs::write(&manifest_path, &patched)?;

    if json {
        println!(
            "{}",
            serde_json::to_string_pretty(&SeriesAssignResult {
                series_id: series_id.clone(),
                kind: kind.to_owned(),
                slug: slug.to_owned(),
            })?
        );
    } else {
        eprintln!("assigned {series_id} to {parent_dir}/{slug}");
        println!("{series_id}");
    }
    Ok(())
}

pub fn allocate_doc_id(registry: &mut Registry, series_id: &str, doc_slug: &str) -> Result<String> {
    if !registry.series.contains_key(series_id) {
        bail!("unknown series '{series_id}'");
    }

    let doc_series = registry
        .docs
        .entry(series_id.to_owned())
        .or_insert_with(|| DocSeries {
            next_counter: 1,
            entries: BTreeMap::new(),
        });

    if let Some(existing) = doc_series.entries.get(doc_slug) {
        return Ok(existing.clone());
    }

    let existing_ids: HashSet<String> = doc_series.entries.values().cloned().collect();

    let mut counter = doc_series.next_counter;
    let doc_id = loop {
        let candidate = format!("{series_id}.{counter:03}");
        if !existing_ids.contains(&candidate) {
            break candidate;
        }
        counter += 1;
    };

    doc_series
        .entries
        .insert(doc_slug.to_owned(), doc_id.clone());
    doc_series.next_counter = counter + 1;

    Ok(doc_id)
}
