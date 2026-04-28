use crate::graph::{self, GraphBuildOptions};
use anyhow::{bail, Context, Result};
use camino::Utf8Path;
use globset::{Glob, GlobSet, GlobSetBuilder};
use std::collections::BTreeSet;
use std::process::Command;
use std::sync::OnceLock;

const NEUTRAL_CONTEXT_PATTERNS: &[&str] = &[".github/workflows/site-projects.yml"];

#[derive(Clone, Debug)]
struct GeneratedRule {
    output_path: String,
    source_patterns: Vec<String>,
}

fn build_globset<I, S>(patterns: I) -> GlobSet
where
    I: IntoIterator<Item = S>,
    S: AsRef<str>,
{
    let mut builder = GlobSetBuilder::new();
    for pattern in patterns {
        let pattern = pattern.as_ref();
        builder.add(
            Glob::new(pattern)
                .unwrap_or_else(|error| panic!("invalid glob pattern `{pattern}`: {error}")),
        );
    }
    builder
        .build()
        .unwrap_or_else(|error| panic!("failed to build globset: {error}"))
}

fn neutral_context_set() -> &'static GlobSet {
    static SET: OnceLock<GlobSet> = OnceLock::new();
    SET.get_or_init(|| build_globset(NEUTRAL_CONTEXT_PATTERNS))
}

fn run_git(repo_root: &Utf8Path, args: &[&str]) -> Result<std::process::Output> {
    Command::new("git")
        .args(args)
        .current_dir(repo_root)
        .output()
        .with_context(|| format!("failed to run git {}", args.join(" ")))
}

pub fn resolve_base_ref(repo_root: &Utf8Path, requested: Option<&str>) -> Result<String> {
    if let Some(requested) = requested {
        return Ok(requested.to_owned());
    }
    for candidate in ["origin/main", "main"] {
        let output = run_git(repo_root, &["rev-parse", "--verify", candidate])?;
        if output.status.success() {
            return Ok(candidate.to_owned());
        }
    }
    bail!("could not resolve a base ref for site project provenance; pass --base-ref explicitly");
}

pub fn changed_paths(repo_root: &Utf8Path, base_ref: &str) -> Result<Vec<String>> {
    let output = run_git(
        repo_root,
        &[
            "diff",
            "--name-only",
            "--diff-filter=ACMR",
            &format!("{base_ref}...HEAD"),
            "--",
        ],
    )?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr).trim().to_owned();
        bail!(
            "failed to compute changed paths against {base_ref}: {}",
            if stderr.is_empty() {
                "git diff failed"
            } else {
                &stderr
            }
        );
    }
    Ok(String::from_utf8_lossy(&output.stdout)
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty())
        .map(ToOwned::to_owned)
        .collect())
}

pub fn find_provenance_violations_for_repo<'a>(
    repo_root: &Utf8Path,
    changed_paths: impl IntoIterator<Item = &'a str>,
) -> Result<Vec<String>> {
    let rules = repo_generated_rules(repo_root)?;
    Ok(find_provenance_violations_with_rules(changed_paths, &rules))
}

fn find_provenance_violations_with_rules<'a>(
    changed_paths: impl IntoIterator<Item = &'a str>,
    rules: &[GeneratedRule],
) -> Vec<String> {
    let paths = changed_paths.into_iter().collect::<Vec<_>>();
    let pure_generated_sync = paths.iter().all(|path| {
        rules.iter().any(|rule| rule.output_path == *path) || neutral_context_set().is_match(path)
    });

    let mut violations = Vec::new();
    for rule in rules {
        if !paths.iter().any(|path| *path == rule.output_path) {
            continue;
        }
        if pure_generated_sync {
            continue;
        }
        let has_upstream_change = paths.iter().any(|candidate| {
            *candidate != rule.output_path && matches_any(candidate, &rule.source_patterns)
        });
        if has_upstream_change {
            continue;
        }
        violations.push(format!(
            "{}: changed without a matching site-project source change; expected one of {}",
            rule.output_path,
            rule.source_patterns.join(", ")
        ));
    }
    violations
}

fn repo_generated_rules(repo_root: &Utf8Path) -> Result<Vec<GeneratedRule>> {
    let graph_artifact =
        graph::build_with_options(repo_root, None, GraphBuildOptions::site_projection())?;
    Ok(graph_generated_rules(&graph_artifact))
}

fn graph_generated_rules(graph_artifact: &graph::RegistryGraph) -> Vec<GeneratedRule> {
    graph_artifact
        .nodes_of_kind("site_output")
        .filter_map(|node| {
            let output_path = graph::attr_str(node, "path")?.to_owned();
            let source_patterns = dedup_sources(
                graph_artifact
                    .outgoing_edges(&node.id, "output_depends_on")
                    .filter_map(|edge| graph_artifact.node(&edge.dst))
                    .filter_map(rule_source_path),
            );
            Some(GeneratedRule {
                output_path,
                source_patterns,
            })
        })
        .collect()
}

fn rule_source_path(node: &graph::GraphNode) -> Option<String> {
    graph::attr_str(node, "source_path").map(str::to_owned)
}

fn dedup_sources<I>(paths: I) -> Vec<String>
where
    I: IntoIterator<Item = String>,
{
    paths
        .into_iter()
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect()
}

fn matches_any(path: &str, patterns: &[String]) -> bool {
    build_globset(patterns.iter().map(String::as_str)).is_match(path)
}

pub fn check_repo_from_git(repo_root: &Utf8Path, requested_base_ref: Option<&str>) -> Result<()> {
    let base_ref = resolve_base_ref(repo_root, requested_base_ref)?;
    let changed = changed_paths(repo_root, &base_ref)?;
    let violations =
        find_provenance_violations_for_repo(repo_root, changed.iter().map(String::as_str))?;
    if violations.is_empty() {
        println!("ok: site project provenance is consistent");
        return Ok(());
    }
    let mut message = String::from("site project provenance check failed:");
    for violation in violations {
        message.push_str("\n- ");
        message.push_str(&violation);
    }
    bail!(message);
}
