#[derive(Clone, Default)]
pub struct SelectionState<T> {
    selected: Option<T>,
    hovered: Option<T>,
}

impl<T> SelectionState<T> {
    #[must_use]
    pub const fn new() -> Self {
        Self {
            selected: None,
            hovered: None,
        }
    }

    pub fn set_selected(&mut self, value: T) {
        self.selected = Some(value);
    }

    pub fn set_hovered(&mut self, value: T) {
        self.hovered = Some(value);
    }

    pub fn clear_selected(&mut self) {
        self.selected = None;
    }

    pub fn clear_hovered(&mut self) {
        self.hovered = None;
    }

    pub fn clear(&mut self) {
        self.selected = None;
        self.hovered = None;
    }

    #[must_use]
    pub const fn selected(&self) -> Option<&T> {
        self.selected.as_ref()
    }

    #[must_use]
    pub const fn hovered(&self) -> Option<&T> {
        self.hovered.as_ref()
    }

    #[must_use]
    pub fn active(&self) -> Option<&T> {
        self.selected.as_ref().or(self.hovered.as_ref())
    }
}

impl<T: PartialEq> SelectionState<T> {
    #[must_use]
    pub fn is_selected(&self, value: &T) -> bool {
        self.selected.as_ref() == Some(value)
    }

    #[must_use]
    pub fn is_hovered(&self, value: &T) -> bool {
        self.hovered.as_ref() == Some(value)
    }
}
