use anyhow::{bail, Context, Result};
use camino::{Utf8Path, Utf8PathBuf};
use serde::Serialize;
use std::fs;
use std::process::Command;

pub struct InitOptions {
    pub repo_root: Option<Utf8PathBuf>,
    pub generated_root: Option<Utf8PathBuf>,
    pub records_bureau_root: Option<Utf8PathBuf>,
}

#[derive(Serialize)]
struct InitReport {
    repo_root: String,
    generated_root: String,
    records_bureau_root: String,
}

pub fn init(options: InitOptions, json: bool) -> Result<()> {
    let repo_root = match options.repo_root {
        Some(path) => path,
        None => crate::manifest::repo_root()?,
    };
    if !repo_root.exists() {
        bail!("repo root does not exist: {repo_root}");
    }
    let parent = repo_root
        .parent()
        .context("repo root must have a parent directory")?;
    let generated_root = options
        .generated_root
        .unwrap_or_else(|| parent.join("generated"));
    let records_bureau_root = options
        .records_bureau_root
        .unwrap_or_else(|| parent.join("records-bureau"));

    ensure_workspace_repo(&generated_root, "generated")?;
    ensure_workspace_repo(&records_bureau_root, "records-bureau")?;

    let report = InitReport {
        repo_root: repo_root.to_string(),
        generated_root: generated_root.to_string(),
        records_bureau_root: records_bureau_root.to_string(),
    };
    if json {
        println!("{}", serde_json::to_string_pretty(&report)?);
    } else {
        println!("workspace sibling repos ready:");
        println!("  {}", report.generated_root);
        println!("  {}", report.records_bureau_root);
    }
    Ok(())
}

fn ensure_workspace_repo(path: &Utf8Path, title: &str) -> Result<()> {
    fs::create_dir_all(path).with_context(|| format!("failed to create {path}"))?;
    if !path.join(".git").exists() && !path.join(".jj").exists() {
        init_repo(path)?;
    }
    write_if_missing(
        &path.join("README.md"),
        &format!("# {title}\n\nPrivate local repository for Specter Labs.\n"),
    )?;
    write_if_missing(&path.join(".gitignore"), ".DS_Store\n")?;
    Ok(())
}

fn write_if_missing(path: &Utf8Path, content: &str) -> Result<()> {
    if path.exists() {
        return Ok(());
    }
    fs::write(path, content).with_context(|| format!("failed to write {path}"))
}

fn init_repo(path: &Utf8Path) -> Result<()> {
    if let Some(stderr) = run_init(["jj", "--quiet", "git", "init", "--colocate", path.as_str()])? {
        bail!("{stderr}");
    }
    Ok(())
}

fn run_init<const N: usize>(args: [&str; N]) -> Result<Option<String>> {
    let program = args[0];
    let command_args = &args[1..];
    match Command::new(program).args(command_args).output() {
        Ok(output) if output.status.success() => Ok(None),
        Ok(output) if program == "jj" => {
            let stderr = String::from_utf8_lossy(&output.stderr).trim().to_owned();
            if stderr.is_empty() {
                bail!("jj git init failed");
            }
            Ok(Some(stderr))
        }
        Ok(output) => {
            let stderr = String::from_utf8_lossy(&output.stderr).trim().to_owned();
            if stderr.is_empty() {
                bail!("{program} init failed");
            }
            bail!("{stderr}");
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound && program == "jj" => {
            let destination = command_args
                .last()
                .copied()
                .context("missing destination path for repo init")?;
            run_init(["git", "init", destination])
        }
        Err(error) => Err(error).with_context(|| format!("failed to run {program}")),
    }
}
