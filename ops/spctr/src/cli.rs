use clap::{Args, CommandFactory, FromArgMatches, Parser, Subcommand, ValueEnum};
use serde::Serialize;

use crate::{
    brand, ci, dispatch, exec, graph, registry, registry_sync, release, report, site, surface,
    sync, tokens, updates, workspace,
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
    Ci {
        #[command(subcommand)]
        command: CiCommand,
    },
    Exec {
        #[command(subcommand)]
        command: ExecCommand,
    },
    Graph {
        #[command(subcommand)]
        command: GraphCommand,
    },
    Registry {
        #[command(subcommand)]
        command: RegistryCommand,
    },
    Series {
        #[command(subcommand)]
        command: SeriesCommand,
    },
    Site {
        #[command(subcommand)]
        command: SiteCommand,
    },
    Tokens {
        #[command(subcommand)]
        command: TokensCommand,
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
    Workspace {
        #[command(subcommand)]
        command: WorkspaceCommand,
    },
    #[command(about = "Print systems status report for Specter infrastructure")]
    Report {
        #[arg(long, help = "Output HTML <pre> page instead of ASCII")]
        html: bool,
        #[arg(
            long,
            help = "Render from a cached JSON file instead of collecting live data"
        )]
        from_cache: Option<String>,
    },
    Completions {
        #[arg(value_enum)]
        shell: clap_complete::Shell,
    },
    #[command(about = "Push all local experiment data to the server")]
    Sync,
    #[command(about = "Run all site validation checks in one pass")]
    Validate,
}

#[derive(Debug, Subcommand)]
enum SurfaceCommand {
    #[command(about = "List manifest-declared surfaces")]
    List,
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
    Promote {
        surface: String,
    },
    Pull {
        surface: String,
    },
}

#[derive(Debug, Subcommand)]
enum ExecCommand {
    #[command(about = "Print the execution plan for a manifest-declared action")]
    Plan {
        #[arg(
            long,
            help = "Project slug; defaults to the manifest discovered from cwd"
        )]
        project: Option<String>,
        #[arg(help = "Manifest exec action name")]
        action: String,
    },
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
    #[command(about = "Validate declared outputs for a manifest-declared action")]
    Validate {
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
enum CiCommand {
    #[command(about = "Print the CI lanes derived from manifest-declared exec actions")]
    Plan {
        #[arg(
            long,
            help = "Project slug; defaults to the manifest discovered from cwd"
        )]
        project: Option<String>,
        #[arg(
            long,
            value_enum,
            default_value_t = CiFormat::Plan,
            help = "Output format"
        )]
        format: CiFormat,
    },
    #[command(about = "Check or write generated GitHub workflows for manifest CI lanes")]
    Sync {
        #[arg(
            long,
            help = "Project slug; defaults to every manifest with [spctr.ci]"
        )]
        project: Option<String>,
        #[arg(
            long,
            help = "Write generated workflows instead of only checking for drift"
        )]
        write: bool,
    },
}

#[derive(Debug, Subcommand)]
enum GraphCommand {
    #[command(
        about = "Compile a manifest-native graph from manifests, docs, evidence, and updates"
    )]
    Build {
        #[arg(
            long,
            help = "Project slug; defaults to every valid manifest in the repo"
        )]
        project: Option<String>,
        #[arg(long, help = "Write the graph JSON to this path")]
        output: Option<camino::Utf8PathBuf>,
    },
}

#[derive(Clone, Debug, ValueEnum)]
enum ProjectKind {
    Dossier,
    Addendum,
}

#[derive(Clone, Debug, ValueEnum, PartialEq, Eq)]
enum CiFormat {
    Plan,
    Github,
}

#[derive(Debug, Subcommand)]
enum SeriesCommand {
    #[command(about = "Assign a series number to a new project")]
    Assign {
        #[arg(long, value_enum)]
        r#type: ProjectKind,
        #[arg(long)]
        slug: String,
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
    #[command(about = "Materialize canonical project catalog, artifact, and health feeds")]
    ProjectFeeds {
        #[arg(long)]
        write: bool,
    },
    Blog {
        #[arg(long)]
        write: bool,
    },
    Pdf {
        #[arg(long)]
        all: bool,
        slug: Option<String>,
        #[arg(long)]
        output: Option<String>,
    },
    Tokens,
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
    #[command(about = "Push local site data mounts to the server")]
    PushData {
        #[arg(long)]
        project: Option<String>,
        #[arg(long)]
        name: Option<String>,
    },
    #[command(about = "Pull site data mounts from the server")]
    PullData {
        #[arg(long)]
        project: Option<String>,
        #[arg(long)]
        name: Option<String>,
        #[arg(long, help = "Deploy SSH host; defaults to SPECTER_DEPLOY_HOST")]
        host: Option<String>,
        #[arg(long, help = "Deploy SSH user; defaults to SPECTER_DEPLOY_USER")]
        user: Option<String>,
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
struct UpdateCreateArgs {
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
        help = "ISO 8601 publication timestamp; defaults to <date>T00:00:00Z"
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
    #[arg(long, help = "Override the topic stored in the update feed")]
    topic: Option<String>,
    #[arg(long, help = "Override the entry id / JSON filename stem")]
    id: Option<String>,
    #[arg(
        long,
        help = "Main update number; auto-increments from existing archive entries when kind=main"
    )]
    series_number: Option<u32>,
    #[arg(long, help = "Optional durable ledger entry id")]
    ledger_entry_id: Option<String>,
    #[arg(long, help = "Optional Zulip message id for the published ledger post")]
    zulip_message_id: Option<u64>,
    #[arg(
        long,
        help = "Path to the approved rollup draft; if omitted, read from stdin"
    )]
    body_file: Option<camino::Utf8PathBuf>,
    #[arg(long, help = "Overwrite an existing entry with the same id")]
    force: bool,
    #[arg(long, help = "Print render status from the archive builder")]
    report: bool,
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
        about = "Materialize an approved update draft into site/updates/entries and rerender the public archive"
    )]
    Create(UpdateCreateArgs),
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

#[derive(Debug, Args)]
struct WorkspaceInitArgs {
    #[arg(
        long,
        help = "Repository root; defaults to the current git top-level checkout"
    )]
    repo_root: Option<camino::Utf8PathBuf>,
    #[arg(long, help = "Override the generated sibling repo path")]
    generated_root: Option<camino::Utf8PathBuf>,
    #[arg(long, help = "Override the records-bureau sibling repo path")]
    records_bureau_root: Option<camino::Utf8PathBuf>,
}

#[derive(Debug, Subcommand)]
enum WorkspaceCommand {
    #[command(about = "Create local sibling repos for generated outputs and records")]
    Init(WorkspaceInitArgs),
}

#[derive(Debug, Subcommand)]
enum ReleaseCommand {
    #[command(about = "Validate public release manifests and tracked-file guardrails")]
    Validate {
        #[arg(help = "Optional project slug")]
        project: Option<String>,
    },
    #[command(about = "Evaluate manifest-declared release gates")]
    Gate {
        #[arg(help = "Optional project slug")]
        project: Option<String>,
    },
    #[command(about = "Run the full source-available release audit")]
    Audit,
    #[command(about = "Print the public release plan for a project")]
    Plan {
        #[arg(help = "Project slug")]
        project: String,
    },
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
    #[command(about = "Materialize a package surface for publishing")]
    Package {
        #[arg(help = "Project slug")]
        project: String,
        #[arg(help = "Package surface name")]
        surface: String,
        #[arg(long, help = "Output directory")]
        output: String,
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
        CommandGroup::Ci { command } => dispatch_ci(command, cli.json),
        CommandGroup::Exec { command } => dispatch_exec(command, cli.json),
        CommandGroup::Graph { command } => dispatch_graph(command, cli.json),
        CommandGroup::Registry { command } => dispatch_registry(command, cli.json),
        CommandGroup::Series { command } => dispatch_series(command, cli.json),
        CommandGroup::Site { command } => dispatch_site(command),
        CommandGroup::Tokens { command } => dispatch_tokens(command),
        CommandGroup::Updates { command } => dispatch_updates(*command, cli.json),
        CommandGroup::Dispatch { command } => dispatch_dispatch(command),
        CommandGroup::Release { command } => dispatch_release(command, cli.json),
        CommandGroup::Workspace { command } => dispatch_workspace(command, cli.json),
        CommandGroup::Report { html, from_cache } => dispatch_report(html, from_cache, cli.json),
        CommandGroup::Completions { shell } => {
            let mut cmd = cli_command();
            clap_complete::generate(shell, &mut cmd, "spctr", &mut std::io::stdout());
            Ok(())
        }
        CommandGroup::Sync => sync::sync(cli.json),
        CommandGroup::Validate => run_validate(),
    }
}

fn dispatch_surface(command: SurfaceCommand, json: bool) -> anyhow::Result<()> {
    match command {
        SurfaceCommand::List => surface::list(json),
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
        SurfaceCommand::Promote { surface } => surface::promote(&surface, json),
        SurfaceCommand::Pull { surface } => surface::pull(&surface, json),
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

fn print_exec_plan(plan: &exec::ExecPlan) {
    println!("{} [{}] action={}", plan.project, plan.kind, plan.action);
    println!("project_root: {}", plan.project_root);
    println!("workdir: {}", plan.workdir);
    if let Some(description) = &plan.description {
        println!("description: {description}");
    }
    if let Some(network) = &plan.network {
        println!("network: {network}");
    }
    if let Some(timeout_sec) = plan.timeout_sec {
        println!("timeout_sec: {timeout_sec}");
    }
    for command in &plan.commands {
        println!("command: {}", command.join(" "));
    }
    if !plan.requires.is_empty() {
        println!("requires: {}", plan.requires.join(", "));
    }
    for output in &plan.expected_outputs {
        println!("output: {} -> {}", output.name, output.path);
    }
}

fn print_exec_validation_report(report: &exec::ExecValidationReport) {
    print_exec_header(&report.project, &report.kind, &report.action, report.ok);
    print_exec_outputs(&report.outputs);
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
        ExecCommand::Plan { project, action } => {
            let manifest = exec::lookup_project(&repo_root, project.as_deref())?;
            let plan = exec::build_plan(&repo_root, &manifest, &action)?;
            if json {
                print_json_pretty(&plan)?;
            } else {
                print_exec_plan(&plan);
            }
            Ok(())
        }
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
        ExecCommand::Validate { project, action } => {
            let report = exec::validate(&repo_root, project.as_deref(), &action)?;
            if json {
                print_json_pretty(&report)?;
            } else {
                print_exec_validation_report(&report);
            }
            if report.ok {
                Ok(())
            } else {
                Err(anyhow::anyhow!(
                    "required outputs missing for exec action '{}'",
                    report.action
                ))
            }
        }
    }
}

fn dispatch_ci(command: CiCommand, json: bool) -> anyhow::Result<()> {
    let repo_root = crate::manifest::repo_root()?;
    match command {
        CiCommand::Plan { project, format } => match format {
            CiFormat::Plan => {
                let plan = ci::plan(&repo_root, project.as_deref())?;
                if json {
                    print_json_pretty(&plan)?;
                } else {
                    println!(
                        "{} runner={} lanes={}",
                        plan.slug,
                        plan.runner.as_deref().unwrap_or("default"),
                        plan.lanes.len()
                    );
                    for lane in &plan.lanes {
                        println!("lane: {} actions={}", lane.name, lane.actions.len());
                        for action in &lane.actions {
                            println!(
                                "  {} -> {} command(s)",
                                action.action,
                                action.commands.len()
                            );
                        }
                    }
                }
                Ok(())
            }
            CiFormat::Github => {
                let workflow = ci::github_plan(&repo_root, project.as_deref())?;
                if json {
                    print_json_pretty(&workflow)?;
                } else {
                    print!("{}", ci::render_github_workflow(&workflow));
                }
                Ok(())
            }
        },
        CiCommand::Sync { project, write } => {
            let report = ci::sync(&repo_root, project.as_deref(), write)?;
            if json {
                print_json_pretty(&report)?;
                if !write && !report.is_clean() {
                    return Err(anyhow::anyhow!(report.drift_message()));
                }
            } else if report.is_clean() {
                println!("ci workflows: in sync");
            } else if write {
                for entry in &report.entries {
                    println!("{} {}", entry.status, entry.workflow_path);
                }
            } else {
                return Err(anyhow::anyhow!(report.drift_message()));
            }
            Ok(())
        }
    }
}

fn dispatch_graph(command: GraphCommand, json: bool) -> anyhow::Result<()> {
    let repo_root = crate::manifest::repo_root()?;
    match command {
        GraphCommand::Build { project, output } => {
            let graph_artifact = graph::build(&repo_root, project.as_deref())?;
            if let Some(output) = output {
                let resolved = if output.is_absolute() {
                    output
                } else {
                    repo_root.join(output)
                };
                graph::write(&graph_artifact, &resolved)?;
                if json {
                    print_json_pretty(&graph_artifact)?;
                } else {
                    println!("graph: wrote {}", resolved);
                }
            } else {
                print_json_pretty(&graph_artifact)?;
            }
            Ok(())
        }
    }
}

fn dispatch_series(command: SeriesCommand, json: bool) -> anyhow::Result<()> {
    match command {
        SeriesCommand::Assign { r#type, slug } => {
            let repo_root = crate::manifest::repo_root()?;
            let kind = match r#type {
                ProjectKind::Dossier => "dossier",
                ProjectKind::Addendum => "addendum",
            };
            registry::series_assign(&repo_root, kind, &slug, json)
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
        SiteCommand::ProjectFeeds { write } => {
            let repo_root = crate::manifest::repo_root()?;
            site::export_project_feeds(&repo_root, write)
        }
        SiteCommand::Blog { write } => {
            let repo_root = crate::manifest::repo_root()?;
            crate::site::blog::build_blog(&repo_root, write)
        }
        SiteCommand::Pdf { all, slug, output } => {
            let repo_root = crate::manifest::repo_root()?;
            if all {
                return crate::site::pdf::build_all_pdfs(&repo_root);
            }
            let slug = slug.ok_or_else(|| anyhow::anyhow!("provide a blog slug or --all"))?;
            let pdf = crate::site::pdf::build_pdf(&repo_root, &slug)?;
            if let Some(dest) = output {
                std::fs::copy(&pdf, &dest)?;
                eprintln!("copied to {dest}");
            }
            Ok(())
        }
        SiteCommand::Tokens => {
            let repo_root = crate::manifest::repo_root()?;
            crate::site::tokens::check_tokens(&repo_root)
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
        SiteCommand::PushData { project, name } => {
            let repo_root = crate::manifest::repo_root()?;
            crate::site::data::push_data(&repo_root, project.as_deref(), name.as_deref())
        }
        SiteCommand::PullData {
            project,
            name,
            host,
            user,
        } => {
            let repo_root = crate::manifest::repo_root()?;
            crate::site::data::pull_data(
                &repo_root,
                project.as_deref(),
                name.as_deref(),
                host.as_deref(),
                user.as_deref(),
            )
        }
    }
}

fn dispatch_tokens(command: TokensCommand) -> anyhow::Result<()> {
    let repo_root = crate::manifest::repo_root()?;
    tokens::dispatch(&repo_root, command)
}

fn dispatch_updates(command: UpdatesCommand, json: bool) -> anyhow::Result<()> {
    match command {
        UpdatesCommand::Create(args) => updates::create(updates::CreateOptions {
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
            ledger_entry_id: args.ledger_entry_id,
            zulip_message_id: args.zulip_message_id,
            body_file: args.body_file,
            force: args.force,
            report: args.report,
            json,
        }),
        UpdatesCommand::Approve(args) => updates::approve(updates::ApprovalOptions {
            create: updates::CreateOptions {
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
                ledger_entry_id: None,
                zulip_message_id: None,
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

fn dispatch_workspace(command: WorkspaceCommand, json: bool) -> anyhow::Result<()> {
    match command {
        WorkspaceCommand::Init(args) => workspace::init(
            workspace::InitOptions {
                repo_root: args.repo_root,
                generated_root: args.generated_root,
                records_bureau_root: args.records_bureau_root,
            },
            json,
        ),
    }
}

fn dispatch_release(command: ReleaseCommand, json: bool) -> anyhow::Result<()> {
    let repo_root = crate::manifest::repo_root()?;
    match command {
        ReleaseCommand::Validate { project } => {
            let plans = release::validate(&repo_root, project.as_deref())?;
            if json {
                print_json_pretty(&plans)?;
            } else {
                for plan in &plans {
                    print_release_plan_summary(plan);
                }
            }
            Ok(())
        }
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
        ReleaseCommand::Plan { project } => {
            let manifest = release::lookup_project(&repo_root, &project)?;
            let plan = release::build_plan(&manifest);
            print_json_pretty(&plan)
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
        ReleaseCommand::Package {
            project,
            surface,
            output,
        } => {
            let manifest = release::lookup_project(&repo_root, &project)?;
            let materialized = release::materialize_package_surface(
                &repo_root,
                &manifest,
                &surface,
                camino::Utf8Path::new(&output),
            )?;
            if json {
                print_json_pretty(&serde_json::json!({
                    "project": project,
                    "surface": surface,
                    "output": materialized.as_str(),
                }))?;
            } else {
                println!("{materialized}");
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

fn dispatch_report(html: bool, from_cache: Option<String>, json: bool) -> anyhow::Result<()> {
    let data = match from_cache {
        Some(path) => report::collect_from_cache(&path)?,
        None => {
            let config = crate::config::load_report_config()?;
            report::collect(&config)?
        }
    };
    if json {
        println!("{}", serde_json::to_string_pretty(&data)?);
    } else if html {
        print!("{}", report::format_html(&data));
    } else {
        print!("{}", report::format_ascii(&data));
    }
    Ok(())
}

fn run_validate() -> anyhow::Result<()> {
    let repo_root = crate::manifest::repo_root()?;
    let checks: Vec<(&str, anyhow::Result<()>)> = vec![
        ("registry", registry_sync::ensure_clean(&repo_root)),
        ("site build", site::build(&repo_root, false)),
        ("blog", crate::site::blog::build_blog(&repo_root, false)),
        (
            "cabinet",
            crate::site::cabinet::build_cabinet(&repo_root, false),
        ),
        ("tokens", crate::site::tokens::check_tokens(&repo_root)),
    ];
    let mut failures = Vec::new();
    for (label, result) in checks {
        match result {
            Ok(()) => eprintln!("{label}: ok"),
            Err(error) => {
                eprintln!("{label}: FAILED");
                failures.push(format!("{label}: {error:#}"));
            }
        }
    }
    if failures.is_empty() {
        Ok(())
    } else {
        Err(anyhow::anyhow!(
            "{} validation failure(s):\n{}",
            failures.len(),
            failures.join("\n")
        ))
    }
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
    fn parse_exec_plan() {
        let cli =
            Cli::try_parse_from(["spctr", "exec", "plan", "--project", "alpha", "smoke"]).unwrap();
        match cli.command {
            CommandGroup::Exec {
                command: ExecCommand::Plan { project, action },
            } => {
                assert_eq!(project.as_deref(), Some("alpha"));
                assert_eq!(action, "smoke");
            }
            other => panic!("unexpected command: {other:?}"),
        }
    }

    #[test]
    fn parse_exec_validate() {
        let cli = Cli::try_parse_from(["spctr", "exec", "validate", "--project", "alpha", "smoke"])
            .unwrap();
        match cli.command {
            CommandGroup::Exec {
                command: ExecCommand::Validate { project, action },
            } => {
                assert_eq!(project.as_deref(), Some("alpha"));
                assert_eq!(action, "smoke");
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
    fn parse_graph_build() {
        let cli = Cli::try_parse_from([
            "spctr",
            "graph",
            "build",
            "--project",
            "alpha",
            "--output",
            "tmp/graph.json",
        ])
        .unwrap();
        match cli.command {
            CommandGroup::Graph {
                command: GraphCommand::Build { project, output },
            } => {
                assert_eq!(project.as_deref(), Some("alpha"));
                assert_eq!(
                    output.as_deref().map(camino::Utf8Path::as_str),
                    Some("tmp/graph.json")
                );
            }
            other => panic!("unexpected command: {other:?}"),
        }
    }

    #[test]
    fn parse_ci_plan() {
        let cli = Cli::try_parse_from(["spctr", "ci", "plan", "--project", "alpha"]).unwrap();
        match cli.command {
            CommandGroup::Ci {
                command: CiCommand::Plan { project, format },
            } => {
                assert_eq!(project.as_deref(), Some("alpha"));
                assert_eq!(format, CiFormat::Plan);
            }
            other => panic!("unexpected command: {other:?}"),
        }
    }

    #[test]
    fn parse_ci_plan_github_format() {
        let cli = Cli::try_parse_from(["spctr", "ci", "plan", "--format", "github"]).unwrap();
        match cli.command {
            CommandGroup::Ci {
                command: CiCommand::Plan { project, format },
            } => {
                assert_eq!(project, None);
                assert_eq!(format, CiFormat::Github);
            }
            other => panic!("unexpected command: {other:?}"),
        }
    }

    #[test]
    fn parse_ci_sync() {
        let cli =
            Cli::try_parse_from(["spctr", "ci", "sync", "--project", "alpha", "--write"]).unwrap();
        match cli.command {
            CommandGroup::Ci {
                command: CiCommand::Sync { project, write },
            } => {
                assert_eq!(project.as_deref(), Some("alpha"));
                assert!(write);
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

    #[test]
    fn parse_site_project_feeds() {
        let cli = Cli::try_parse_from(["spctr", "site", "project-feeds", "--write"]).unwrap();
        match cli.command {
            CommandGroup::Site {
                command: SiteCommand::ProjectFeeds { write },
            } => {
                assert!(write);
            }
            other => panic!("unexpected command: {other:?}"),
        }
    }
}
