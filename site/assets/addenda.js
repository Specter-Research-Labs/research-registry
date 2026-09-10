const cutButton = document.querySelector('[data-cut-toggle]');
cutButton?.addEventListener('click', () => {
  const connectivity = cutButton.getAttribute('aria-pressed') !== 'true';
  cutButton.setAttribute('aria-pressed', String(connectivity));
  cutButton.textContent = connectivity ? 'Show decomposition ranking' : 'Compare connectivity ranking';
  document.querySelector('[data-cut-count]').textContent = connectivity ? 'Rank 12' : 'Rank 1';
  document.querySelector('[data-cut-label]').textContent = connectivity ? 'Connectivity ranking · cut 10 first' : 'Decomposition ranking · cut 16 first';
  const x = connectivity ? 264 : 414;
  document.querySelector('[data-cut-marker]').setAttribute('d', `M${x} 115L${x} 145`);
});
const costInput = document.querySelector('#k-cost');
costInput?.addEventListener('input', () => {
  const cost = Number(costInput.value);
  document.querySelector('[data-policy-cost]').textContent = cost;
  document.querySelector('[data-policy-bar]').style.width = `${cost}%`;
  document.querySelector('[data-k-result]').textContent = `K = ${Math.log10(100 / cost).toFixed(2)}`;
});
