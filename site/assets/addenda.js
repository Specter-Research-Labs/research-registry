const costInput = document.querySelector('#k-cost');
costInput?.addEventListener('input', () => {
  const cost = Number(costInput.value);
  document.querySelector('[data-policy-cost]').textContent = cost;
  document.querySelector('[data-policy-bar]').style.width = `${cost}%`;
  document.querySelector('[data-k-result]').textContent = `K = ${Math.log10(100 / cost).toFixed(2)}`;
});
