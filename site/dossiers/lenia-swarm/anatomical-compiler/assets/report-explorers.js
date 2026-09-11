"use strict";
const time = document.getElementById("orbium-time");
time.addEventListener("change", () => {
  const step = time.value;
  for (const [id, family, label] of [["orbium-native-frame", "target", "Native"], ["orbium-fitted-frame", "still", "Recovered"]]) {
    const frame = document.getElementById(id);
    frame.src = `assets/orbium-${family}-${step}.png`;
    frame.alt = `${label} Orbium at step ${step}`;
  }
  document.getElementById("orbium-time-note").textContent = step === "600"
    ? "Step 600 is the only field scored by this search."
    : step === "1200"
      ? "600 steps beyond the search horizon, the recovered body remains coherent. This continuation was not scored."
      : "This earlier frame was not scored. The search used only the field at step 600.";
});
