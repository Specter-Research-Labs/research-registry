// Native RGBA renders, encoded as animated WebP for browser transparency.
export function updateMotionControl(button, playing, subject = 'replay') {
  button.dataset.playing = String(playing);
  button.setAttribute('aria-label', `${playing ? 'Pause' : 'Play'} ${subject}`);
  button.setAttribute('aria-pressed', String(playing));
}
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
    updateMotionControl(button, playing);
  }
  image.addEventListener('error', () => {
    if (playing) { playing = false; image.src = image.dataset.still; updateMotionControl(button, false); button.setAttribute('aria-label', 'Retry replay'); }
  });
  button.addEventListener('click', () => setPlaying(!playing));
  setPlaying(true);
});
