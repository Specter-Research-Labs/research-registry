use std::collections::HashSet;

use anyhow::Context;
use tokio_postgres::NoTls;

use crate::dispatch::{assets_root, env::load_env_file_from_var};

const MIGRATIONS_TABLE_SQL: &str = r#"
    CREATE TABLE IF NOT EXISTS dispatch_schema_migrations (
      filename TEXT PRIMARY KEY,
      applied_at TEXT NOT NULL
    )
"#;

pub async fn run() -> anyhow::Result<()> {
    load_env_file_from_var()?;
    let config = crate::dispatch::env::DispatchConfig::from_process();
    let database_url = config.require_database_url()?.to_owned();
    let (client, connection) = tokio_postgres::connect(&database_url, NoTls).await?;
    tokio::spawn(async move {
        if let Err(error) = connection.await {
            eprintln!("dispatch postgres connection failed: {error}");
        }
    });

    client.batch_execute(MIGRATIONS_TABLE_SQL).await?;

    let rows = client
        .query("SELECT filename FROM dispatch_schema_migrations", &[])
        .await?;
    let mut applied = rows
        .into_iter()
        .map(|row| row.get::<_, String>("filename"))
        .collect::<HashSet<_>>();

    for migration in sorted_migration_filenames()? {
        if applied.contains(&migration) {
            continue;
        }
        let sql_path = assets_root().join("migrations").join(&migration);
        let sql = std::fs::read_to_string(&sql_path)
            .with_context(|| format!("failed to read {}", sql_path))?;
        if let Err(error) = apply_migration(&client, &migration, &sql).await {
            let _ = client.batch_execute("ROLLBACK").await;
            return Err(error);
        }
        println!("applied migration {migration}");
        applied.insert(migration);
    }

    Ok(())
}

async fn apply_migration(
    client: &tokio_postgres::Client,
    filename: &str,
    sql: &str,
) -> anyhow::Result<()> {
    client.batch_execute("BEGIN").await?;
    client.batch_execute(sql).await?;
    client
        .execute(
            "INSERT INTO dispatch_schema_migrations (filename, applied_at) VALUES ($1, $2)",
            &[
                &filename,
                &chrono::Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Millis, true),
            ],
        )
        .await?;
    client.batch_execute("COMMIT").await?;
    Ok(())
}

fn sorted_migration_filenames() -> anyhow::Result<Vec<String>> {
    let migrations_dir = assets_root().join("migrations");
    let mut entries = std::fs::read_dir(&migrations_dir)
        .with_context(|| format!("failed to read {migrations_dir}"))?
        .map(|entry| {
            entry
                .map(|entry| entry.file_name())
                .map(|name| name.to_string_lossy().into_owned())
        })
        .collect::<Result<Vec<_>, _>>()?;
    entries.retain(|entry| entry.ends_with(".sql"));
    entries.sort();
    Ok(entries)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sorts_known_migrations() {
        let entries = sorted_migration_filenames().unwrap();
        assert_eq!(entries, vec!["0001_init.sql", "0002_ledger_entries.sql"]);
    }
}
