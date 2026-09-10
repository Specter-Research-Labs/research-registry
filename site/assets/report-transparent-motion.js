// Native RGBA renders, encoded as animated WebP for browser transparency.
const motionPreference = matchMedia('(prefers-reduced-motion: reduce)');
document.querySelectorAll('.report-motion-frame').forEach(frame => {
  const image = frame.querySelector('.report-transparent-motion');
  const button = frame.querySelector('.report-motion-toggle');
  let playing = false;
  function setPlaying(next) {
    playing = next;
    if (playing) {
      image.src = image.dataset.motion;
    } else {
      // Capture the displayed frame so pausing does not jump to a different body.
      const canvas = document.createElement('canvas');
      canvas.width = image.naturalWidth || 512;
      canvas.height = image.naturalHeight || 512;
      try { canvas.getContext('2d').drawImage(image, 0, 0); image.src = canvas.toDataURL(); }
      catch { image.src = image.dataset.still; }
    }
    button.textContent = playing ? 'Pause motion' : 'Play motion';
    button.setAttribute('aria-pressed', String(playing));
  }
  image.addEventListener('error', () => {
    if (playing) { playing = false; image.src = image.dataset.still; button.textContent = 'Retry motion'; button.setAttribute('aria-pressed', 'false'); }
  });
  button.addEventListener('click', () => setPlaying(!playing));
  if (!motionPreference.matches && frame.dataset.motionAutoplay !== 'false') setPlaying(true);
  motionPreference.addEventListener('change', () => { if (motionPreference.matches && playing) setPlaying(false); });
});
