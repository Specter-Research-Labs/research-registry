for (const study of document.querySelectorAll('[data-tactic-study]')) {
  for (const button of study.querySelectorAll('[data-tactic]')) {
    button.addEventListener('click', () => {
      const blocked = button.dataset.tactic === 'blocked';
      study.classList.toggle('is-blocked', blocked);
      for (const control of study.querySelectorAll('[data-tactic]')) control.setAttribute('aria-pressed', String(control === button));
      study.querySelector('.tactic-count').textContent = button.dataset.result;
    });
  }
}
const descriptions = {
  drive: 'Apply a temporary driving force. Record how the bodies move and how their local material properties change.',
  release: 'Remove the driving force. Measure what persists, comparing the memory rule with memory-free and damping-only controls.',
  damage: 'Disturb the imprinted assembly and let it continue. Measure recovery and whether the earlier imprint helps or hinders the response.'
};
for (const study of document.querySelectorAll('[data-material-study]')) {
  for (const button of study.querySelectorAll('button[data-stage]')) {
    button.addEventListener('click', () => {
      study.dataset.stage = button.dataset.stage;
      study.querySelector('.material-reading').textContent = descriptions[button.dataset.stage];
      for (const control of study.querySelectorAll('button[data-stage]')) control.setAttribute('aria-pressed', String(control === button));
    });
  }
}
