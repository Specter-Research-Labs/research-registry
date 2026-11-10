use clap::{Args, CommandFactory, FromArgMatches, Parser, Subcommand, ValueEnum};
use serde::Serialize;

use crate::{
    brand, dispatch, doc, exec, registry_sync, release, report, site, surface, tokens, updates,
};

#[derive(Debug, Parser)]
#[command(
    name = "spctr",
    about = "Portable Specter Labs CLI",
    version,
    disable_help_subcommand = true
)]
struct Cli {
    #[arg(long, global = true, help = "Emit structured JSON to stdout")]
    json: bool,
    #[command(subcommand)]
    command: CommandGroup,
}

#[derive(Debug, Subcommand)]
enum CommandGroup {
    Surface {
        #[command(subcommand)]
        command: SurfaceCommand,
    },
    Exec {
        #[command(subcommand)]
        command: ExecCommand,
    },
    Registry {
        #[command(subcommand)]
        command: RegistryCommand,
    },
    Site {
        #[command(subcommand)]
        command: SiteCommand,
    },
    Tokens {
        #[command(subcommand)]
        command: TokensCommand,
    },
    #[command(about = "Render report sources to self-contained HTML pages")]
    Doc {
        #[command(subcommand)]
        command: DocCommand,
    },
    Updates {
        #[command(subcommand)]
        command: Box<UpdatesCommand>,
    },
    Dispatch {
        #[command(subcommand)]
        command: DispatchCommand,
    },
    Release {
        #[command(subcommand)]
        command: ReleaseCommand,
    },
    #[command(about = "Print systems status report for Specter infrastructure")]
    Report {
        #[arg(
            long,
            help = "Render from a cached JSON file instead of collecting live data"
        )]
        from_cache: Option<String>,
    },
}

#[derive(Debug, Subcommand)]
enum SurfaceCommand {
    Checkpoint {
        #[arg(default_value = "all")]
        surface: String,
    },
    Status {
        #[arg(default_value = "all")]
        surface: String,
    },
    Refresh {
        surface: String,
        #[arg(
            long,
            help = "Release identifier written into exported surface manifests"
        )]
        release_id: Option<String>,
        #[arg(long, help = "Refresh derived site data into this directory")]
        site_data_root: Option<String>,
    },
    Sync {
        #[arg(default_value = "all")]
        surface: String,
    },
}

#[derive(Debug, Subcommand)]
enum ExecCommand {
    #[command(about = "Run a manifest-declared action and write its evidence card")]
    Run {
        #[arg(
            long,
            help = "Project slug; defaults to the manifest discovered from cwd"
        )]
        project: Option<String>,
        #[arg(help = "Manifest exec action name")]
        action: String,
    },
}

#[derive(Debug, Subcommand)]
enum RegistryCommand {
    #[command(about = "Fail if series or cabinet doc identifiers would change")]
    Check,
    #[command(about = "Assign missing series and cabinet doc identifiers")]
    Sync,
}

#[derive(Debug, Subcommand)]
enum SiteCommand {
    Build {
        #[arg(long)]
        write: bool,
    },
    Blog {
        #[arg(long)]
        write: bool,
        /// Render one article under the unpublished review surface.
        #[arg(long, requires = "write")]
        preview: Option<String>,
    },
    Cabinet {
        #[arg(long)]
        write: bool,
    },
    Provenance {
        #[arg(
            long,
            help = "Git ref or commit to diff against. Defaults to origin/main, then main."
        )]
        base_ref: Option<String>,
    },
    Portal {
        #[arg(long, default_value = "/srv/www/releases")]
        release_root: String,
    },
    #[command(about = "Build the site and write the exact public file set that publish uploads")]
    Stage {
        #[arg(long, help = "New or existing directory to receive the staged site")]
        output: camino::Utf8PathBuf,
    },
    Publish {
        #[arg(long, help = "Release identifier; defaults to git HEAD")]
        release_id: Option<String>,
    },
    #[command(about = "Build, archive, and publish the Lenia compendium surface")]
    PublishLeniaCompendium {
        #[arg(long, help = "Release identifier")]
        release_id: String,
        #[arg(
            long,
            help = "Compendium output root; defaults to dossiers/lenia-swarm/artifacts/compendium"
        )]
        output: Option<camino::Utf8PathBuf>,
        #[arg(
            last = true,
            help = "Extra arguments forwarded to `LeniaCLI compendium publish` after `--`"
        )]
        passthrough: Vec<String>,
    },
    #[command(about = "Refresh, archive, and publish the Wonton site dashboard surface")]
    PublishWontonDashboard {
        #[arg(long, help = "Release identifier; defaults to git HEAD")]
        release_id: Option<String>,
        #[arg(
            long,
            help = "Dashboard data root; defaults to site/dashboards/wonton-soup/data"
        )]
        site_data_root: Option<camino::Utf8PathBuf>,
    },
    #[command(about = "Sync the records corpus to the public releases host")]
    PushRecords {
        #[arg(long, help = "Local records-bureau directory to sync")]
        source: String,
    },
}

#[derive(Clone, Debug, ValueEnum)]
pub enum TokenTarget {
    Css,
    #[value(name = "typst-fm")]
    TypstFm,
    Email,
}

#[derive(Debug, Subcommand)]
enum DocCommand {
    /// Render <dir>/report.md for the review app (<dir>/report.html) or for the
    /// site (site/<published path>/index.html). Site documents that link to each
    /// other's sections can be built together in one batch.
    Build {
        #[arg(required = true)]
        dirs: Vec<camino::Utf8PathBuf>,
        #[arg(long, value_enum, default_value_t = doc::Target::Lab)]
        target: doc::Target,
        #[arg(long)]
        out: Option<camino::Utf8PathBuf>,
    },
}

#[derive(Debug, Subcommand)]
pub enum TokensCommand {
    Generate {
        #[arg(long)]
        target: Option<TokenTarget>,
    },
    Check,
}

#[derive(Clone, Debug, ValueEnum)]
enum UpdateKindArg {
    Window,
    Main,
}

impl From<UpdateKindArg> for updates::UpdateKind {
    fn from(value: UpdateKindArg) -> Self {
        match value {
            UpdateKindArg::Window => Self::Window,
            UpdateKindArg::Main => Self::Main,
        }
    }
}

#[derive(Debug, Args)]
struct UpdateApproveArgs {
    #[arg(
        long,
        help = "Repository root; defaults to the nearest ancestor with site/updates/entries"
    )]
    repo_root: Option<camino::Utf8PathBuf>,
    #[arg(
        long,
        value_enum,
        default_value = "window",
        help = "Archive entry kind to materialize"
    )]
    kind: UpdateKindArg,
    #[arg(long, help = "Entry date; defaults to the window end date")]
    date: Option<String>,
    #[arg(
        long,
        help = "ISO 8601 publication timestamp; defaults to the dispatch ledger timestamp"
    )]
    published_at: Option<String>,
    #[arg(
        long,
        help = "Window start date (YYYY-MM-DD); optional if the draft includes a Window line"
    )]
    window_start: Option<String>,
    #[arg(
        long,
        help = "Window end date (YYYY-MM-DD); optional if the draft includes a Window line"
    )]
    window_end: Option<String>,
    #[arg(long, help = "Override the rendered entry label")]
    label: Option<String>,
    #[arg(
        long,
        help = "Override the topic stored in the update feed and Zulip ledger post"
    )]
    topic: Option<String>,
    #[arg(long, help = "Override the entry id / JSON filename stem")]
    id: Option<String>,
    #[arg(
        long,
        help = "Main update number; auto-increments from existing archive entries when kind=main"
    )]
    series_number: Option<u32>,
    #[arg(
        long,
        help = "Path to the approved rollup draft; if omitted, read from stdin"
    )]
    body_file: Option<camino::Utf8PathBuf>,
    #[arg(long, help = "Overwrite an existing entry with the same id")]
    force: bool,
    #[arg(
        long,
        help = "Dispatch base URL; defaults to SPECTER_DISPATCH_URL or DISPATCH_PUBLIC_URL"
    )]
    dispatch_url: Option<String>,
    #[arg(
        long,
        help = "Dispatch shared secret; defaults to SPECTER_DISPATCH_SHARED_SECRET or RUNNER_SHARED_SECRET"
    )]
    dispatch_secret: Option<String>,
    #[arg(long, help = "Optional requestor email recorded in the ledger entry")]
    requested_by_email: Option<String>,
    #[arg(long, help = "Optional requestor name recorded in the ledger entry")]
    requested_by_name: Option<String>,
    #[arg(long, help = "Print render status from the archive builder")]
    report: bool,
}

#[derive(Debug, Subcommand)]
enum UpdatesCommand {
    #[command(
        about = "Post an approved update draft to the dispatch ledger and archive the same entry locally"
    )]
    Approve(UpdateApproveArgs),
}

#[derive(Debug, Subcommand)]
pub enum DispatchCommand {
    #[command(about = "Serve the Specter dispatch control plane")]
    Serve,
    #[command(about = "Apply dispatch database migrations")]
    Migrate,
}

#[derive(Debug, Subcommand)]
enum ReleaseCommand {
    #[command(about = "Evaluate manifest-declared release gates")]
    Gate {
        #[arg(help = "Optional project slug")]
        project: Option<String>,
    },
    #[command(about = "Run the full source-available release audit")]
    Audit,
    #[command(about = "Build a source bundle for a release surface")]
    Bundle {
        #[arg(help = "Project slug")]
        project: String,
        #[arg(help = "Source bundle surface name")]
        surface: String,
        #[arg(long, help = "Release identifier")]
        release_id: String,
        #[arg(long, help = "Output directory")]
        output: Option<String>,
    },
    #[command(about = "Build and archive a public Typst field manual PDF release")]
    PublishTypstPdf {
        #[arg(long, help = "Input .typ document")]
        input: camino::Utf8PathBuf,
        #[arg(long, help = "Release identifier")]
        release_id: String,
        #[arg(long, help = "Overwrite an existing archived release")]
        overwrite_release: bool,
    },
}

fn cli_command() -> clap::Command {
    Cli::command()
        .before_help(brand::COMPACT_LOGO)
        .long_version(brand::LONG_VERSION)
}

pub fn run() -> anyhow::Result<()> {
    let matches = cli_command().get_matches();
    let cli = Cli::from_arg_matches(&matches).unwrap_or_else(|error| error.exit());
    match cli.command {
        CommandGroup::Surface { command } => dispatch_surface(command, cli.json),
        CommandGroup::Exec { command } => dispatch_exec(command, cli.json),
        CommandGroup::Registry { command } => dispatch_registry(command, cli.json),
        CommandGroup::Site { command } => dispatch_site(command),
        CommandGroup::Tokens { command } => dispatch_tokens(command),
        CommandGroup::Doc { command } => dispatch_doc(command),
        CommandGroup::Updates { command } => dispatch_updates(*command, cli.json),
        CommandGroup::Dispatch { command } => dispatch_dispatch(command),
        CommandGroup::Release { command } => dispatch_release(command, cli.json),
        CommandGroup::Report { from_cache } => dispatch_report(from_cache, cli.json),
    }
}

fn dispatch_surface(command: SurfaceCommand, json: bool) -> anyhow::Result<()> {
    match command {
        SurfaceCommand::Checkpoint { surface } => surface::checkpoint(&surface, json),
        SurfaceCommand::Status { surface } => surface::status(&surface, json),
        SurfaceCommand::Refresh {
            surface,
            release_id,
            site_data_root,
        } => {
            if site_data_root.is_some() {
                crate::lake::refresh_surface(
                    &surface,
                    site_data_root.as_deref(),
                    release_id.as_deref(),
                )
            } else {
                if release_id.is_some() {
                    anyhow::bail!("--release-id requires --site-data-root");
                }
                surface::refresh(&surface, json)
            }
        }
        SurfaceCommand::Sync { surface } => surface::sync(&surface, json),
    }
}

fn print_json_pretty(value: &impl Serialize) -> anyhow::Result<()> {
    println!("{}", serde_json::to_string_pretty(value)?);
    Ok(())
}

fn print_exec_header(project: &str, kind: &str, action: &str, ok: bool) {
    let status = if ok { "ok" } else { "FAILED" };
    println!("{project} [{kind}] action={action} {status}");
}

fn exec_output_status(output: &exec::ExecValidatedOutput) -> &'static str {
    if output.matches.is_empty() {
        if output.required {
            "missing"
        } else {
            "optional-missing"
        }
    } else {
        "ok"
    }
}

fn print_exec_outputs(outputs: &[exec::ExecValidatedOutput]) {
    for output in outputs {
        println!(
            "  [{}] {} -> {}",
            exec_output_status(output),
            output.name,
            output.path
        );
        for matched in &output.matches {
            println!("    match: {matched}");
        }
    }
}

fn print_exec_run_report(report: &exec::ExecRunReport) {
    print_exec_header(&report.project, &report.kind, &report.action, report.ok);
    if let Some(exit_code) = report.exit_code {
        println!("exit_code: {exit_code}");
    }
    if report.timed_out {
        println!("timed_out: true");
    }
    if let Some(card_path) = &report.card_path {
        println!("evidence_card: {card_path}");
    }
    if let Some(error) = &report.error {
        println!("error: {error}");
    }
    print_exec_outputs(&report.outputs);
}

fn print_release_plan_summary(plan: &release::ReleasePlan) {
    println!(
        "{} [{}] license={} stage={} surfaces={}",
        plan.slug,
        plan.kind,
        plan.license,
        plan.stage,
        plan.surfaces.len()
    );
}

fn dispatch_exec(command: ExecCommand, json: bool) -> anyhow::Result<()> {
    let repo_root = crate::manifest::repo_root()?;
    match command {
        ExecCommand::Run { project, action } => {
            let report = exec::run(&repo_root, project.as_deref(), &action)?;
            if json {
                print_json_pretty(&report)?;
            } else {
                print_exec_run_report(&report);
            }
            if report.ok {
                Ok(())
            } else {
                Err(anyhow::anyhow!(
                    "exec action '{}' failed or produced incomplete outputs",
                    report.action
                ))
            }
        }
    }
}

fn dispatch_registry(command: RegistryCommand, json: bool) -> anyhow::Result<()> {
    let repo_root = crate::manifest::repo_root()?;
    match command {
        RegistryCommand::Check => {
            let report = registry_sync::plan(&repo_root)?;
            if json {
                println!("{}", serde_json::to_string_pretty(&report)?);
                if report.is_clean() {
                    Ok(())
                } else {
                    Err(anyhow::anyhow!(report.drift_message()))
                }
            } else if report.is_clean() {
                eprintln!("registry: ok");
                Ok(())
            } else {
                Err(anyhow::anyhow!(report.drift_message()))
            }
        }
        RegistryCommand::Sync => {
            let report = registry_sync::sync(&repo_root)?;
            if json {
                println!("{}", serde_json::to_string_pretty(&report)?);
            } else if report.is_clean() {
                eprintln!("registry: no changes");
            } else {
                for assignment in &report.series_assignments {
                    eprintln!(
                        "registry: assigned {} to {} {}",
                        assignment.series_id, assignment.kind, assignment.slug
                    );
                }
                for assignment in &report.doc_assignments {
                    eprintln!(
                        "registry: assigned {} to {}/{}",
                        assignment.doc_id, assignment.project_slug, assignment.doc_slug
                    );
                }
            }
            Ok(())
        }
    }
}

fn dispatch_site(command: SiteCommand) -> anyhow::Result<()> {
    match command {
        SiteCommand::Build { write } => {
            let repo_root = crate::manifest::repo_root()?;
            site::build(&repo_root, write)
        }
        SiteCommand::Blog { write, preview } => {
            let repo_root = crate::manifest::repo_root()?;
            if let Some(slug) = preview {
                return crate::site::blog::preview_blog(&repo_root, &slug);
            }
            crate::site::blog::build_blog(&repo_root, write)
        }
        SiteCommand::Cabinet { write } => {
            let repo_root = crate::manifest::repo_root()?;
            crate::site::cabinet::build_cabinet(&repo_root, write)
        }
        SiteCommand::Provenance { base_ref } => {
            let repo_root = crate::manifest::repo_root()?;
            crate::site::provenance::check_repo_from_git(&repo_root, base_ref.as_deref())
        }
        SiteCommand::Portal { release_root } => {
            crate::site::portal::render_portal(std::path::Path::new(&release_root))
        }
        SiteCommand::Stage { output } => {
            let repo_root = crate::manifest::repo_root()?;
            let output = if output.is_absolute() {
                output
            } else {
                repo_root.join(output)
            };
            crate::site::publish::stage_site(&repo_root, &output).map(|_| ())
        }
        SiteCommand::Publish { release_id } => {
            let repo_root = crate::manifest::repo_root()?;
            crate::site::publish::publish_site(&repo_root, release_id.as_deref())
        }
        SiteCommand::PublishLeniaCompendium {
            release_id,
            output,
            passthrough,
        } => {
            let repo_root = crate::manifest::repo_root()?;
            crate::site::publish::publish_lenia_compendium(
                &repo_root,
                &release_id,
                output.as_deref(),
                &passthrough,
            )
        }
        SiteCommand::PublishWontonDashboard {
            release_id,
            site_data_root,
        } => {
            let repo_root = crate::manifest::repo_root()?;
            crate::site::publish::publish_wonton_dashboard(
                &repo_root,
                release_id.as_deref(),
                site_data_root.as_deref(),
            )
        }
        SiteCommand::PushRecords { source } => {
            crate::site::publish::push_records(std::path::Path::new(&source))
        }
    }
}

fn dispatch_tokens(command: TokensCommand) -> anyhow::Result<()> {
    let repo_root = crate::manifest::repo_root()?;
    tokens::dispatch(&repo_root, command)
}

fn dispatch_doc(command: DocCommand) -> anyhow::Result<()> {
    let repo_root = crate::manifest::repo_root()?;
    match command {
        DocCommand::Build { dirs, target, out } => {
            doc::build(&repo_root, &dirs, target, out.as_deref()).map(|_| ())
        }
    }
}

fn dispatch_updates(command: UpdatesCommand, json: bool) -> anyhow::Result<()> {
    match command {
        UpdatesCommand::Approve(args) => updates::approve(updates::ApprovalOptions {
            draft: updates::DraftOptions {
                repo_root: args.repo_root,
                kind: args.kind.into(),
                date: args.date,
                published_at: args.published_at,
                window_start: args.window_start,
                window_end: args.window_end,
                label: args.label,
                topic: args.topic,
                entry_id: args.id,
                series_number: args.series_number,
                body_file: args.body_file,
                force: args.force,
                report: args.report,
                json,
            },
            dispatch_url: args.dispatch_url,
            dispatch_secret: args.dispatch_secret,
            requested_by_email: args.requested_by_email,
            requested_by_name: args.requested_by_name,
        }),
    }
}

fn dispatch_dispatch(command: DispatchCommand) -> anyhow::Result<()> {
    dispatch::run(command)
}

fn dispatch_release(command: ReleaseCommand, json: bool) -> anyhow::Result<()> {
    let repo_root = crate::manifest::repo_root()?;
    match command {
        ReleaseCommand::Gate { project } => {
            let reports = release::gate(&repo_root, project.as_deref())?;
            let failures = reports.iter().filter(|report| !report.ok).count();
            if json {
                print_json_pretty(&reports)?;
            } else {
                for report in &reports {
                    let status = if report.ok { "ok" } else { "FAILED" };
                    println!(
                        "{} stage={} checks={} {}",
                        report.slug,
                        report.stage,
                        report.checks.len(),
                        status
                    );
                    for check in &report.checks {
                        let check_status = if check.ok { "ok" } else { "fail" };
                        println!("  [{}] {}: {}", check_status, check.name, check.detail);
                    }
                }
            }
            if failures == 0 {
                Ok(())
            } else {
                Err(anyhow::anyhow!(
                    "{} project(s) failed release gates",
                    failures
                ))
            }
        }
        ReleaseCommand::Audit => {
            let report = release::audit(&repo_root)?;
            if json {
                print_json_pretty(&report)?;
            } else {
                for plan in &report.plans {
                    print_release_plan_summary(plan);
                }
                println!("source-available release audit: ok");
            }
            Ok(())
        }
        ReleaseCommand::Bundle {
            project,
            surface,
            release_id,
            output,
        } => {
            let manifest = release::lookup_project(&repo_root, &project)?;
            let output_dir = output.as_deref().map(camino::Utf8Path::new);
            let archive = release::bundle_source_surface(
                &repo_root,
                &manifest,
                &surface,
                &release_id,
                output_dir,
            )?;
            if json {
                print_json_pretty(&serde_json::json!({
                    "project": project,
                    "surface": surface,
                    "release_id": release_id,
                    "archive": archive.as_str(),
                }))?;
            } else {
                println!("{archive}");
            }
            Ok(())
        }
        ReleaseCommand::PublishTypstPdf {
            input,
            release_id,
            overwrite_release,
        } => crate::site::publish::publish_typst_release(
            &repo_root,
            &input,
            &release_id,
            overwrite_release,
        ),
    }
}

fn dispatch_report(from_cache: Option<String>, json: bool) -> anyhow::Result<()> {
    let data = match from_cache {
        Some(path) => report::collect_from_cache(&path)?,
        None => {
            let config = crate::config::load_report_config()?;
            report::collect(&config)?
        }
    };
    if json {
        println!("{}", serde_json::to_string_pretty(&data)?);
    } else {
        print!("{}", report::format_ascii(&data));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_lenia_publish_passthrough() {
        let cli = Cli::try_parse_from([
            "spctr",
            "site",
            "publish-lenia-compendium",
            "--release-id",
            "demo-1",
            "--",
            "--limit",
            "25",
            "--include-replay",
        ])
        .unwrap();
        match cli.command {
            CommandGroup::Site {
                command:
                    SiteCommand::PublishLeniaCompendium {
                        release_id,
                        output,
                        passthrough,
                    },
            } => {
                assert_eq!(release_id, "demo-1");
                assert!(output.is_none());
                assert_eq!(passthrough, ["--limit", "25", "--include-replay"]);
            }
            other => panic!("unexpected command: {other:?}"),
        }
    }

    #[test]
    fn parse_wonton_dashboard_publish() {
        let cli = Cli::try_parse_from([
            "spctr",
            "site",
            "publish-wonton-dashboard",
            "--release-id",
            "demo-2",
            "--site-data-root",
            "tmp/wonton",
        ])
        .unwrap();
        match cli.command {
            CommandGroup::Site {
                command:
                    SiteCommand::PublishWontonDashboard {
                        release_id,
                        site_data_root,
                    },
            } => {
                assert_eq!(release_id.as_deref(), Some("demo-2"));
                assert_eq!(
                    site_data_root.as_deref().map(camino::Utf8Path::as_str),
                    Some("tmp/wonton")
                );
            }
            other => panic!("unexpected command: {other:?}"),
        }
    }

    #[test]
    fn parse_surface_refresh_site_data() {
        let cli = Cli::try_parse_from([
            "spctr",
            "surface",
            "refresh",
            "wonton-lake",
            "--site-data-root",
            "/srv/www/site/data/wonton-soup",
        ])
        .unwrap();
        match cli.command {
            CommandGroup::Surface {
                command:
                    SurfaceCommand::Refresh {
                        surface,
                        release_id,
                        site_data_root,
                    },
            } => {
                assert_eq!(surface, "wonton-lake");
                assert!(release_id.is_none());
                assert_eq!(
                    site_data_root.as_deref(),
                    Some("/srv/www/site/data/wonton-soup")
                );
            }
            other => panic!("unexpected command: {other:?}"),
        }
    }

    #[test]
    fn parse_typst_release_publish() {
        let cli = Cli::try_parse_from([
            "spctr",
            "release",
            "publish-typst-pdf",
            "--input",
            "addenda/typst-field-manual/paper-example.typ",
            "--release-id",
            "demo-3",
            "--overwrite-release",
        ])
        .unwrap();
        match cli.command {
            CommandGroup::Release {
                command:
                    ReleaseCommand::PublishTypstPdf {
                        input,
                        release_id,
                        overwrite_release,
                    },
            } => {
                assert_eq!(
                    input.as_str(),
                    "addenda/typst-field-manual/paper-example.typ"
                );
                assert_eq!(release_id, "demo-3");
                assert!(overwrite_release);
            }
            other => panic!("unexpected command: {other:?}"),
        }
    }

    #[test]
    fn parse_exec_run() {
        let cli =
            Cli::try_parse_from(["spctr", "exec", "run", "--project", "alpha", "smoke"]).unwrap();
        match cli.command {
            CommandGroup::Exec {
                command: ExecCommand::Run { project, action },
            } => {
                assert_eq!(project.as_deref(), Some("alpha"));
                assert_eq!(action, "smoke");
            }
            other => panic!("unexpected command: {other:?}"),
        }
    }

    #[test]
    fn parse_release_gate() {
        let cli = Cli::try_parse_from(["spctr", "release", "gate", "alpha"]).unwrap();
        match cli.command {
            CommandGroup::Release {
                command: ReleaseCommand::Gate { project },
            } => {
                assert_eq!(project.as_deref(), Some("alpha"));
            }
            other => panic!("unexpected command: {other:?}"),
        }
    }

    #[test]
    fn parse_registry_check() {
        let cli = Cli::try_parse_from(["spctr", "registry", "check"]).unwrap();
        match cli.command {
            CommandGroup::Registry {
                command: RegistryCommand::Check,
            } => {}
            other => panic!("unexpected command: {other:?}"),
        }
    }

    #[test]
    fn long_version_uses_branded_block() {
        let rendered = cli_command().render_long_version().to_string();
        assert!(rendered.contains(env!("CARGO_PKG_VERSION")));
        assert!(rendered.contains(".-#@-. .::."));
    }

    #[test]
    fn help_includes_compact_logo() {
        let rendered = cli_command().render_help().to_string();
        assert!(rendered.contains(".-#@-. .::."));
    }
}

#[cfg(test)]
mod dispatch_command_tests {
    use super::*;

    #[test]
    fn parse_dispatch_serve() {
        let cli = Cli::try_parse_from(["spctr", "dispatch", "serve"]).unwrap();
        match cli.command {
            CommandGroup::Dispatch {
                command: DispatchCommand::Serve,
            } => {}
            other => panic!("unexpected command: {other:?}"),
        }
    }

    #[test]
    fn parse_dispatch_migrate() {
        let cli = Cli::try_parse_from(["spctr", "dispatch", "migrate"]).unwrap();
        match cli.command {
            CommandGroup::Dispatch {
                command: DispatchCommand::Migrate,
            } => {}
            other => panic!("unexpected command: {other:?}"),
        }
    }
}
