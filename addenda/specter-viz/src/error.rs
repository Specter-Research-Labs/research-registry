use core::fmt;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RenderError {
    widget: &'static str,
    message: String,
}

impl RenderError {
    #[must_use]
    pub fn new(widget: &'static str, message: impl Into<String>) -> Self {
        Self {
            widget,
            message: message.into(),
        }
    }

    #[must_use]
    pub const fn widget(&self) -> &'static str {
        self.widget
    }

    #[must_use]
    pub fn message(&self) -> &str {
        &self.message
    }
}

impl fmt::Display for RenderError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}: {}", self.widget, self.message)
    }
}

impl std::error::Error for RenderError {}
