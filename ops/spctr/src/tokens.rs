use anyhow::Result;
use camino::Utf8Path;

use crate::cli::TokenTarget;
use crate::cli::TokensCommand;
use crate::{design_tokens, design_tokens_css, design_tokens_email, design_tokens_typst};

pub fn dispatch(repo_root: &Utf8Path, command: TokensCommand) -> Result<()> {
    let spec_dir = design_tokens::spec_dir(repo_root);

    match command {
        TokensCommand::Generate { target } => {
            let targets = match target {
                Some(t) => vec![t],
                None => vec![TokenTarget::Css, TokenTarget::TypstFm, TokenTarget::Email],
            };
            for t in targets {
                match t {
                    TokenTarget::Css => {
                        let tokens = design_tokens::load_spec(&spec_dir, "web")?;
                        let css = design_tokens_css::generate_css(&tokens)?;
                        let path = repo_root.join("site/tokens.css");
                        std::fs::write(&path, &css)?;
                        eprintln!("wrote {}", path);
                    }
                    TokenTarget::TypstFm => {
                        let fm = design_tokens::load_context_only(&spec_dir, "field-manual")?;
                        let paper = design_tokens::load_context_only(&spec_dir, "paper")?;
                        let typst = design_tokens_typst::generate_typst(&fm, &paper)?;
                        let path = repo_root.join("addenda/typst-field-manual/tokens.typ");
                        std::fs::write(&path, &typst)?;
                        eprintln!("wrote {}", path);
                    }
                    TokenTarget::Email => {
                        let tokens = design_tokens::load_spec(&spec_dir, "email")?;
                        let json = design_tokens_email::generate_email_json(&tokens)?;
                        let path = repo_root.join("ops/spctr/dispatch/tokens.json");
                        std::fs::write(&path, &json)?;
                        eprintln!("wrote {}", path);
                    }
                }
            }
            Ok(())
        }
        TokensCommand::Check => {
            let base_tokens = design_tokens::load_spec(&spec_dir, "web")?;
            design_tokens::validate_spec(&base_tokens)?;
            eprintln!("ok: design token spec is consistent");

            let css_tokens = design_tokens::load_spec(&spec_dir, "web")?;
            let expected_css = design_tokens_css::generate_css(&css_tokens)?;
            let css_path = repo_root.join("site/tokens.css");
            if css_path.is_file() {
                let on_disk = std::fs::read_to_string(&css_path)?;
                if on_disk != expected_css {
                    anyhow::bail!(
                        "site/tokens.css is stale; run `spctr tokens generate --target css`"
                    );
                }
                eprintln!("ok: site/tokens.css is fresh");
            }

            let fm = design_tokens::load_context_only(&spec_dir, "field-manual")?;
            let paper = design_tokens::load_context_only(&spec_dir, "paper")?;
            let expected_typst = design_tokens_typst::generate_typst(&fm, &paper)?;
            let typst_path = repo_root.join("addenda/typst-field-manual/tokens.typ");
            if typst_path.is_file() {
                let on_disk = std::fs::read_to_string(&typst_path)?;
                if on_disk != expected_typst {
                    anyhow::bail!(
                        "tokens.typ is stale; run `spctr tokens generate --target typst-fm`"
                    );
                }
                eprintln!("ok: tokens.typ is fresh");
            }

            crate::site::tokens::check_tokens(repo_root)?;

            Ok(())
        }
    }
}
