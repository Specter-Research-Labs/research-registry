use crate::config::load_machine_config;
use crate::drivers::resolve_surface;
use crate::manifest::{self, discover_surfaced_manifests, ProjectManifest};
use crate::surface::{checkpoint_surface, CheckpointResult};
use anyhow::Result;
use rayon::prelude::*;

struct SyncTarget {
    manifest: ProjectManifest,
    resolved: crate::drivers::ResolvedSurface,
}

pub fn sync(json: bool) -> Result<()> {
    let repo_root = manifest::repo_root()?;
    let machine = load_machine_config()?;
    let manifests = discover_surfaced_manifests(&repo_root)?;

    let mut targets: Vec<SyncTarget> = Vec::new();
    for manifest in &manifests {
        let spctr = manifest.spctr.as_ref().unwrap();
        for surface_config in spctr.surfaces.values() {
            let resolved = resolve_surface(manifest, surface_config, &machine)?;
            targets.push(SyncTarget {
                manifest: manifest.clone(),
                resolved,
            });
        }
    }

    if targets.is_empty() {
        if !json {
            eprintln!("no surfaced projects found");
        }
        if json {
            println!("[]");
        }
        return Ok(());
    }

    let results: Vec<CheckpointResult> = targets
        .par_iter()
        .map(|target| checkpoint_surface(&machine, &target.manifest, &target.resolved))
        .collect::<Result<Vec<_>>>()?;

    if json {
        println!("{}", serde_json::to_string_pretty(&results)?);
    } else {
        for result in &results {
            match &result.checkpoint_id {
                Some(id) => eprintln!("{}: checkpoint={id}", result.surface),
                None => eprintln!("{}: no changes", result.surface),
            }
        }
    }
    Ok(())
}
