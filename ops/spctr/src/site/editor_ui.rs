pub fn javascript(nonce: &str) -> String {
    javascript_template().replace("__SPCTR_EDITOR_NONCE__", nonce)
}

fn javascript_template() -> &'static str {
    r#"(() => {
  'use strict';

  const SOURCE = 'data-spctr-source';
  const VALUE = 'data-spctr-value';
  const LABEL = 'data-spctr-label';
  const SAVE_ENDPOINT = '/__spctr/save';
  const RESOLVE_ENDPOINT = '/__spctr/resolve';
  const SESSION_NONCE = '__SPCTR_EDITOR_NONCE__';
  const editingClass = 'spctr-editing';

  const toggle = document.createElement('button');
  toggle.type = 'button';
  toggle.className = 'spctr-editor-toggle';
  toggle.setAttribute('aria-pressed', 'false');
  toggle.textContent = 'Edit page';
  document.body.append(toggle);

  const cssToggle = document.createElement('button');
  cssToggle.type = 'button';
  cssToggle.className = 'spctr-css-toggle';
  cssToggle.setAttribute('aria-pressed', 'false');
  cssToggle.textContent = 'Disable CSS';
  document.body.append(cssToggle);

  let disabledStyles = [];

  function setCssDisabled(disabled) {
    if (disabled) {
      disabledStyles = Array.from(document.querySelectorAll('link[rel~="stylesheet"], style'))
        .filter((element) => element.id !== 'spctr-editor-styles')
        .map((element) => ({ element, disabled: element.disabled }));
      disabledStyles.forEach(({ element }) => { element.disabled = true; });
    } else {
      disabledStyles.forEach(({ element, disabled: wasDisabled }) => {
        element.disabled = wasDisabled;
      });
      disabledStyles = [];
    }
    cssToggle.setAttribute('aria-pressed', String(disabled));
    cssToggle.textContent = disabled ? 'Enable CSS' : 'Disable CSS';
  }

  const status = document.createElement('p');
  status.className = 'spctr-editor-status';
  status.setAttribute('role', 'status');
  status.setAttribute('aria-live', 'polite');
  status.hidden = true;
  document.body.append(status);

  const dialog = document.createElement('dialog');
  dialog.className = 'spctr-editor-dialog';
  dialog.setAttribute('aria-labelledby', 'spctr-editor-title');
  dialog.innerHTML = `
    <form method="dialog">
      <h2 id="spctr-editor-title">Edit text</h2>
      <label for="spctr-editor-value">Text</label>
      <textarea id="spctr-editor-value" rows="7"></textarea>
      <p class="spctr-editor-error" role="alert" aria-live="polite"></p>
      <div class="spctr-editor-actions">
        <button type="button" data-action="cancel">Cancel</button>
        <button type="button" data-action="save">Save</button>
      </div>
    </form>`;
  document.body.append(dialog);

  const textarea = dialog.querySelector('textarea');
  const error = dialog.querySelector('.spctr-editor-error');
  const save = dialog.querySelector('[data-action="save"]');
  const cancel = dialog.querySelector('[data-action="cancel"]');
  let activeElement = null;
  let activeEdit = null;
  let resolving = false;

  function showStatus(message, isError = false) {
    status.textContent = message;
    status.classList.toggle('is-error', isError);
    status.hidden = !message;
  }

  function setEditing(enabled) {
    document.documentElement.classList.toggle(editingClass, enabled);
    toggle.setAttribute('aria-pressed', String(enabled));
    toggle.textContent = enabled ? 'Stop editing' : 'Edit page';
  }

  function openEditor(element, edit = null) {
    activeElement = element;
    activeEdit = edit || {
      source: element.getAttribute(SOURCE),
      value: element.getAttribute(VALUE),
      label: element.getAttribute(LABEL) || 'text'
    };
    showStatus('');
    error.textContent = '';
    dialog.querySelector('h2').textContent = `Edit ${activeEdit.label}`;
    textarea.value = activeEdit.value;
    save.disabled = true;
    dialog.showModal();
    textarea.focus();
    textarea.select();
  }

  function closeEditor() {
    if (dialog.open) dialog.close();
    activeElement = null;
    activeEdit = null;
    error.textContent = '';
  }

  function nearestTextElement(target) {
    let element = target instanceof Element ? target : target.parentElement;
    while (element && element !== document.body) {
      const value = element.innerText && element.innerText.trim();
      if (value) {
        const selection = window.getSelection();
        if (selection && selection.rangeCount > 0) {
          const selectedValue = selection.toString().trim();
          const range = selection.getRangeAt(0);
          if (selectedValue && element.contains(range.commonAncestorContainer)) {
            return { element, value: selectedValue };
          }
        }
        return { element, value };
      }
      element = element.parentElement;
    }
    return null;
  }

  async function resolveEditor(candidate) {
    if (resolving) return;
    resolving = true;
    showStatus('Finding source');

    try {
      const response = await fetch(RESOLVE_ENDPOINT, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json',
          'X-Spctr-Editor-Nonce': SESSION_NONCE
        },
        body: JSON.stringify({
          page: window.location.pathname,
          value: candidate.value,
          tagName: candidate.element.tagName.toLowerCase(),
          className: typeof candidate.element.className === 'string'
            ? candidate.element.className
            : ''
        })
      });

      if (!response.ok) {
        if (response.status === 422) {
          throw new Error('This text is read-only.');
        }
        const contentType = response.headers.get('content-type') || '';
        const message = contentType.includes('application/json')
          ? (await response.json()).error
          : await response.text();
        throw new Error(message || `Source lookup failed (${response.status})`);
      }

      const resolved = await response.json();
      if (!resolved || typeof resolved.source !== 'string' ||
          typeof resolved.value !== 'string' || typeof resolved.label !== 'string') {
        throw new Error('Source lookup returned an invalid response');
      }

      showStatus('');
      openEditor(candidate.element, resolved);
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : 'Source lookup failed';
      showStatus(message, true);
    } finally {
      resolving = false;
    }
  }

  async function saveEdit() {
    if (!activeElement || !activeEdit) return;
    const oldValue = activeEdit.value;
    if (textarea.value === oldValue) return;

    save.disabled = true;
    cancel.disabled = true;
    error.textContent = '';
    const previousLabel = save.textContent;
    save.textContent = 'Saving';

    try {
      const response = await fetch(SAVE_ENDPOINT, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json',
          'X-Spctr-Editor-Nonce': SESSION_NONCE
        },
        body: JSON.stringify({
          source: activeEdit.source,
          oldValue,
          newValue: textarea.value
        })
      });

      if (!response.ok) {
        const contentType = response.headers.get('content-type') || '';
        const message = contentType.includes('application/json')
          ? (await response.json()).error
          : await response.text();
        throw new Error(message || `Save failed (${response.status})`);
      }

      window.location.reload();
    } catch (cause) {
      error.textContent = cause instanceof Error ? cause.message : 'Save failed';
      save.disabled = textarea.value === oldValue;
      cancel.disabled = false;
      save.textContent = previousLabel;
      textarea.focus();
    }
  }

  toggle.addEventListener('click', () => {
    setEditing(!document.documentElement.classList.contains(editingClass));
    showStatus('');
  });

  cssToggle.addEventListener('click', () => {
    setCssDisabled(cssToggle.getAttribute('aria-pressed') !== 'true');
  });

  document.addEventListener('click', (event) => {
    if (!document.documentElement.classList.contains(editingClass)) return;
    if (dialog.contains(event.target) || toggle.contains(event.target) || status.contains(event.target)) return;
    const element = event.target.closest(`[${SOURCE}][${VALUE}]`);
    if (element) {
      event.preventDefault();
      event.stopPropagation();
      openEditor(element);
      return;
    }

    const candidate = nearestTextElement(event.target);
    if (candidate) {
      event.preventDefault();
      event.stopPropagation();
      resolveEditor(candidate);
    }
  }, true);

  cancel.addEventListener('click', closeEditor);
  save.addEventListener('click', saveEdit);
  textarea.addEventListener('input', () => {
    if (!activeElement) return;
    save.disabled = !activeEdit || textarea.value === activeEdit.value;
  });
  dialog.addEventListener('cancel', (event) => {
    event.preventDefault();
    closeEditor();
  });
  textarea.addEventListener('keydown', (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
      event.preventDefault();
      saveEdit();
    }
  });
})();"#
}

pub fn stylesheet() -> &'static str {
    r#".spctr-editor-toggle,
.spctr-css-toggle {
  position: fixed;
  z-index: 2147483646;
  right: 1rem;
  bottom: 1rem;
  padding: 0.55rem 0.8rem;
  border: 1px solid #4a5568;
  border-radius: 0.35rem;
  background: #fff;
  color: #1a202c;
  box-shadow: 0 0.2rem 0.8rem rgb(0 0 0 / 18%);
  font: 600 0.875rem/1.2 system-ui, sans-serif;
  cursor: pointer;
}

.spctr-css-toggle {
  right: 7.75rem;
}

.spctr-editor-toggle:focus-visible,
.spctr-css-toggle:focus-visible,
.spctr-editor-dialog button:focus-visible,
.spctr-editor-dialog textarea:focus-visible {
  outline: 3px solid #2563eb;
  outline-offset: 2px;
}

.spctr-editor-status {
  position: fixed;
  z-index: 2147483646;
  right: 1rem;
  bottom: 3.9rem;
  max-width: min(24rem, calc(100vw - 2rem));
  margin: 0;
  padding: 0.5rem 0.7rem;
  border: 1px solid #94a3b8;
  border-radius: 0.35rem;
  background: #fff;
  color: #334155;
  box-shadow: 0 0.2rem 0.8rem rgb(0 0 0 / 18%);
  font: 500 0.8125rem/1.35 system-ui, sans-serif;
}

.spctr-editor-status.is-error {
  border-color: #b91c1c;
  color: #b91c1c;
}

.spctr-editing [data-spctr-source][data-spctr-value] {
  cursor: text;
  outline: 1px dashed rgb(37 99 235 / 55%);
  outline-offset: 0.2rem;
}

.spctr-editing [data-spctr-source][data-spctr-value]:hover {
  outline: 2px solid #2563eb;
  background: rgb(37 99 235 / 8%);
}

.spctr-editor-dialog {
  width: min(36rem, calc(100vw - 2rem));
  margin: auto;
  padding: 1rem;
  border: 1px solid #cbd5e1;
  border-radius: 0.5rem;
  color: #1a202c;
  background: #fff;
  box-shadow: 0 1rem 3rem rgb(0 0 0 / 25%);
  font: 400 1rem/1.4 system-ui, sans-serif;
}

.spctr-editor-dialog::backdrop {
  background: rgb(15 23 42 / 45%);
}

.spctr-editor-dialog h2 {
  margin: 0 0 0.75rem;
  font-size: 1rem;
}

.spctr-editor-dialog label {
  display: block;
  margin-bottom: 0.3rem;
  font-weight: 600;
}

.spctr-editor-dialog textarea {
  box-sizing: border-box;
  width: 100%;
  resize: vertical;
  padding: 0.6rem;
  border: 1px solid #94a3b8;
  border-radius: 0.3rem;
  color: inherit;
  background: inherit;
  font: inherit;
}

.spctr-editor-error {
  min-height: 1.4em;
  margin: 0.5rem 0;
  color: #b91c1c;
}

.spctr-editor-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}

.spctr-editor-actions button {
  padding: 0.45rem 0.75rem;
  border: 1px solid #64748b;
  border-radius: 0.3rem;
  background: #f8fafc;
  color: #1e293b;
  font: inherit;
  cursor: pointer;
}

.spctr-editor-actions [data-action="save"] {
  border-color: #1d4ed8;
  background: #2563eb;
  color: #fff;
}

.spctr-editor-actions button:disabled {
  cursor: wait;
  opacity: 0.65;
}"#
}

#[cfg(test)]
mod tests {
    use super::{javascript, stylesheet};

    #[test]
    fn javascript_posts_source_and_value_to_save_endpoint() {
        let script = javascript("nonce");
        assert!(script.contains("const SAVE_ENDPOINT = '/__spctr/save'"));
        assert!(script.contains("fetch(SAVE_ENDPOINT"));
        assert!(script.contains("source: activeEdit.source"));
        assert!(script.contains("oldValue,"));
        assert!(script.contains("newValue: textarea.value"));
    }

    #[test]
    fn javascript_resolves_unannotated_text_by_page_and_value() {
        let script = javascript("nonce");
        assert!(script.contains("const RESOLVE_ENDPOINT = '/__spctr/resolve'"));
        assert!(script.contains("fetch(RESOLVE_ENDPOINT"));
        assert!(script.contains("page: window.location.pathname"));
        assert!(script.contains("value: candidate.value"));
        assert!(script.contains("openEditor(candidate.element, resolved)"));
        assert!(script.contains("tagName: candidate.element.tagName.toLowerCase()"));
    }

    #[test]
    fn selected_text_is_used_only_when_contained_by_candidate() {
        let script = javascript("nonce");
        assert!(script.contains("const selectedValue = selection.toString().trim()"));
        assert!(script.contains("element.contains(range.commonAncestorContainer)"));
        assert!(script.contains("return { element, value: selectedValue }"));
    }

    #[test]
    fn unresolved_text_is_reported_as_read_only() {
        let script = javascript("nonce");
        assert!(script.contains("response.status === 422"));
        assert!(script.contains("This text is read-only."));
    }

    #[test]
    fn authored_selector_requires_both_attributes() {
        let selector = "[data-spctr-source][data-spctr-value]";
        assert!(javascript("nonce").contains("`[${SOURCE}][${VALUE}]`"));
        assert!(stylesheet().contains(selector));
    }

    #[test]
    fn javascript_embeds_session_nonce_in_mutations() {
        let script = javascript("unique-session-nonce");
        assert!(script.contains("const SESSION_NONCE = 'unique-session-nonce'"));
        assert!(script.contains("'X-Spctr-Editor-Nonce': SESSION_NONCE"));
    }

    #[test]
    fn css_toggle_preserves_editor_styles_and_restores_page_styles() {
        let script = javascript("nonce");
        assert!(script.contains("cssToggle.textContent = 'Disable CSS'"));
        assert!(script.contains("element.id !== 'spctr-editor-styles'"));
        assert!(script.contains("element.disabled = wasDisabled"));
        assert!(stylesheet().contains(".spctr-css-toggle"));
    }
}
