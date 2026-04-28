pub mod brand;
pub mod ci;
pub mod cli;
pub mod config;
pub mod design_tokens;
pub mod design_tokens_css;
pub mod design_tokens_email;
pub mod design_tokens_typst;
pub mod dispatch;
pub mod drivers;
pub mod exec;
pub mod graph;
pub mod lake;
pub mod manifest;
pub mod markdown;
pub mod registry;
pub mod registry_sync;
pub mod release;
pub mod report;
pub mod series;
pub mod site;
pub mod surface;
pub mod sync;
pub mod tokens;
pub mod updates;
pub mod updates_archive;
pub mod workspace;

use std::process::ExitCode;

pub fn main() -> ExitCode {
    match cli::run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("{error:#}");
            ExitCode::FAILURE
        }
    }
}
