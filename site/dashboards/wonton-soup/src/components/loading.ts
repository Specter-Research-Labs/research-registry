const ROOT_ID = "boot-overlay";

function buildOverlay(): HTMLDivElement {
  const root = document.createElement("div");
  root.id = ROOT_ID;
  root.className = "boot-overlay";

  const card = document.createElement("div");
  card.className = "boot-card";

  const eyebrow = document.createElement("p");
  eyebrow.className = "boot-eyebrow";
  eyebrow.textContent = "Wonton Soup";

  const title = document.createElement("h1");
  title.className = "boot-title";
  title.textContent = "Loading";

  const message = document.createElement("p");
  message.className = "boot-message";

  card.append(eyebrow, title, message);
  root.appendChild(card);
  document.body.prepend(root);
  return root;
}

function ensureRoot(): HTMLDivElement {
  return (document.getElementById(ROOT_ID) as HTMLDivElement) ?? buildOverlay();
}

export function showLoading(message: string): void {
  const root = ensureRoot();
  root.hidden = false;
  delete root.dataset.state;
  const msg = root.querySelector(".boot-message");
  if (msg) msg.textContent = message;
}

export function hideLoading(): void {
  const root = document.getElementById(ROOT_ID);
  if (root) root.hidden = true;
}

export function showError(title: string, message: string, detail?: string): void {
  const root = ensureRoot();
  root.hidden = false;
  root.dataset.state = "error";

  const titleEl = root.querySelector(".boot-title");
  const msgEl = root.querySelector(".boot-message");
  if (titleEl) titleEl.textContent = title;
  if (msgEl) msgEl.textContent = message;

  if (detail) {
    let detailEl = root.querySelector(".boot-detail") as HTMLPreElement | null;
    if (!detailEl) {
      detailEl = document.createElement("pre");
      detailEl.className = "boot-detail";
      root.querySelector(".boot-card")?.appendChild(detailEl);
    }
    detailEl.textContent = detail;
  }
}
