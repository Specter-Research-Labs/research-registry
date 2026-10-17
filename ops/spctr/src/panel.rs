use std::fmt::Write as _;

const NAME_W: usize = 16;
pub(crate) const DATA_W: usize = 42;
// total inner = NAME_W + 3 (` | `) + DATA_W = 61; outer = 61 + 4 (`| ` + ` |`) = 65

pub(crate) fn bar_graph(pct: u8, width: usize) -> String {
    let filled = (usize::from(pct) * width) / 100;
    let mut bar = String::with_capacity(width * 3);
    for _ in 0..filled {
        bar.push('\u{2588}');
    }
    for _ in filled..width {
        bar.push('\u{2591}');
    }
    bar
}

pub(crate) fn header_top(buf: &mut String) {
    let inner = NAME_W + 3 + DATA_W;
    let _ = write!(buf, "\u{250c}");
    for _ in 0..inner + 2 {
        let _ = write!(buf, "\u{252c}");
    }
    let _ = writeln!(buf, "\u{2510}");
    let _ = write!(buf, "\u{251c}");
    for _ in 0..inner + 2 {
        let _ = write!(buf, "\u{2534}");
    }
    let _ = writeln!(buf, "\u{2524}");
}

pub(crate) fn centered(buf: &mut String, text: &str) {
    let inner = NAME_W + 3 + DATA_W + 2;
    let pad_left = (inner.saturating_sub(text.len())) / 2;
    let pad_right = inner.saturating_sub(text.len()).saturating_sub(pad_left);
    let _ = writeln!(
        buf,
        "\u{2502}{:pad_left$}{text}{:pad_right$}\u{2502}",
        "", "",
    );
}

fn divider(buf: &mut String, left: char, mid: char, right: char) {
    let _ = write!(buf, "{left}");
    for _ in 0..NAME_W + 2 {
        let _ = write!(buf, "\u{2500}");
    }
    let _ = write!(buf, "{mid}");
    for _ in 0..DATA_W + 2 {
        let _ = write!(buf, "\u{2500}");
    }
    let _ = writeln!(buf, "{right}");
}

pub(crate) fn divider_top(buf: &mut String) {
    divider(buf, '\u{251c}', '\u{252c}', '\u{2524}');
}

pub(crate) fn divider_mid(buf: &mut String) {
    divider(buf, '\u{251c}', '\u{253c}', '\u{2524}');
}

pub(crate) fn divider_bot(buf: &mut String) {
    divider(buf, '\u{2514}', '\u{2534}', '\u{2518}');
}

fn truncate_chars(s: &str, max: usize) -> String {
    let char_count = s.chars().count();
    if char_count <= max {
        return s.to_owned();
    }
    let mut out: String = s.chars().take(max - 3).collect();
    out.push_str("...");
    out
}

pub(crate) fn row(buf: &mut String, name: &str, data: &str) {
    let display_name = truncate_chars(name, NAME_W);
    let display_data = truncate_chars(data, DATA_W);
    let _ = writeln!(
        buf,
        "\u{2502} {:<NAME_W$} \u{2502} {:<DATA_W$} \u{2502}",
        display_name, display_data
    );
}
