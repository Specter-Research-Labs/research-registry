use maud::{html, Markup};

pub fn link(href: &str, label: &str) -> Markup {
    if href.starts_with("http://") || href.starts_with("https://") {
        html! { a href=(href) target="_blank" rel="noopener noreferrer" { (label) } }
    } else {
        html! { a href=(href) { (label) } }
    }
}
