use anyhow::{bail, Result};
use regex_lite::Regex;

pub fn replace_region(text: &str, name: &str, rendered: &str, path: &str) -> Result<String> {
    let pattern = Regex::new(&format!(
        r"(?m)^([ \t]*)<!-- GENERATED:{} START -->\n(?s:.*?)^[ \t]*<!-- GENERATED:{} END -->",
        regex_lite::escape(name),
        regex_lite::escape(name),
    ))
    .expect("valid region regex");

    let mut matches = pattern.find_iter(text);
    let m = matches
        .next()
        .ok_or_else(|| anyhow::anyhow!("{path}: missing generated region markers for {name}"))?;
    if matches.next().is_some() {
        bail!("{path}: duplicate generated region markers for {name}");
    }

    let start_indent = pattern
        .captures(&text[m.start()..m.end()])
        .and_then(|caps| caps.get(1))
        .map_or("", |g| g.as_str());

    let replacement = format!(
        "{start_indent}<!-- GENERATED:{name} START -->\n\
         {rendered}\n\
         {start_indent}<!-- GENERATED:{name} END -->"
    );

    let mut result = String::with_capacity(text.len());
    result.push_str(&text[..m.start()]);
    result.push_str(&replacement);
    result.push_str(&text[m.end()..]);
    Ok(result)
}
