pub const COMPACT_LOGO: &str = include_str!("../../../site/assets/logo-witch-compact.ascii.txt");
pub const LONG_VERSION: &str = concat!(
    env!("CARGO_PKG_VERSION"),
    "\n\n",
    include_str!("../../../site/assets/logo-witch-compact.ascii.txt")
);
