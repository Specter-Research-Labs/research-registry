use crate::site::records::{self, SiteRecord};
use serde_json::{json, Value};
use std::collections::HashMap;

use crate::manifest::REPO_TREE_URL;

fn catalog_item(record: &SiteRecord, dossier_by_slug: &HashMap<&str, &SiteRecord>) -> Value {
    let mut item = json!({
        "slug": record.slug,
        "title": record.title,
        "summary": record.summary,
        "license": record.license,
        "status": record.status,
        "release_stage": record.release_stage,
        "release_surfaces": record.release_surfaces,
        "last_activity": record.last_activity,
        "repo_path": record.repo_path,
        "repo_url": record.repo_url,
        "featured": record.featured,
        "featured_order": record.featured_order,
        "labels": record.labels,
        "series": record.series,
    });
    let obj = item.as_object_mut().unwrap();
    if record.kind == "dossier" {
        obj.insert("has_docs".into(), json!(record.has_docs_dir));
        obj.insert("has_docs_readme".into(), json!(record.has_docs_readme));
        obj.insert("hub_path".into(), json!(record.hub_path));
        obj.insert("hub_href".into(), json!(record.hub_href()));
        obj.insert("cabinet_href".into(), json!(record.cabinet_href()));
    } else {
        obj.insert("linked_dossier".into(), json!(record.related_dossier));
        let dossier_href = records::related_visible_dossier(record, dossier_by_slug)
            .and_then(SiteRecord::hub_href);
        obj.insert("linked_dossier_href".into(), json!(dossier_href));
    }
    item
}

pub fn build_catalog_json(records: &[SiteRecord]) -> String {
    let slices = records::slice_records(records);

    let dossiers: Vec<Value> = slices
        .visible_dossiers
        .iter()
        .map(|r| catalog_item(r, &slices.dossier_by_slug))
        .collect();
    let addenda: Vec<Value> = slices
        .visible_addenda
        .iter()
        .map(|r| catalog_item(r, &slices.dossier_by_slug))
        .collect();
    let featured_dossier_slugs: Vec<&str> = slices
        .featured_dossiers
        .iter()
        .map(|r| r.slug.as_str())
        .collect();
    let featured_addenda_slugs: Vec<&str> = slices
        .featured_addenda
        .iter()
        .map(|r| r.slug.as_str())
        .collect();

    let catalog = json!({
        "version": 1,
        "repo_tree_url": REPO_TREE_URL,
        "dossiers": dossiers,
        "addenda": addenda,
        "featured": {
            "dossiers": featured_dossier_slugs,
            "addenda": featured_addenda_slugs,
        },
    });

    serde_json::to_string_pretty(&catalog).unwrap() + "\n"
}
