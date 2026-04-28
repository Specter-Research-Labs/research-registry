use camino::Utf8PathBuf;

use crate::cli::DispatchCommand;

pub mod client;
pub mod commands;
pub mod env;
pub mod github;
pub mod ledger;
pub mod migrate;
pub mod pg;
pub mod results;
pub mod server;
pub mod status;
pub mod store;
pub mod surfaces;
pub mod types;
pub mod zulip;

pub fn run(command: DispatchCommand) -> anyhow::Result<()> {
    let runtime = tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .build()
        .map_err(|error| anyhow::anyhow!("failed to build tokio runtime: {error}"))?;
    match command {
        DispatchCommand::Serve => runtime.block_on(server::serve()),
        DispatchCommand::Migrate => runtime.block_on(migrate::run()),
    }
}

pub fn assets_root() -> Utf8PathBuf {
    Utf8PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("dispatch")
}
