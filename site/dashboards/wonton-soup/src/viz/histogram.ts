import { scaleLinear, scaleBand } from "d3-scale";
import { select } from "d3-selection";
import { axisBottom, axisLeft } from "d3-axis";

export interface HistogramOpts {
  container: HTMLElement;
  values: number[];
  bins?: number;
  label?: string;
  color?: string;
  width?: number;
  height?: number;
}

export function renderHistogram(opts: HistogramOpts): void {
  const {
    container,
    values,
    bins = 20,
    label = "",
    color = "#4a8a61",
    width = 300,
    height = 180,
  } = opts;

  if (values.length === 0) {
    container.replaceChildren();
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No data";
    container.appendChild(empty);
    return;
  }

  const margin = { top: 10, right: 10, bottom: 30, left: 40 };
  const innerW = width - margin.left - margin.right;
  const innerH = height - margin.top - margin.bottom;

  const nums = values.map(Number);
  const min = Math.min(...nums);
  const max = Math.max(...nums);
  const range = max - min || 1;
  const binWidth = range / bins;

  const buckets: number[] = new Array(bins).fill(0);
  for (const v of nums) {
    const idx = Math.min(Math.floor((v - min) / binWidth), bins - 1);
    buckets[idx]++;
  }

  const binLabels = buckets.map((_, i) => (min + i * binWidth).toFixed(2));

  container.replaceChildren();

  const svg = select(container)
    .append("svg")
    .attr("width", width)
    .attr("height", height)
    .attr("viewBox", `0 0 ${width} ${height}`);

  const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

  const x = scaleBand<string>().domain(binLabels).range([0, innerW]).padding(0.08);
  const y = scaleLinear().domain([0, Math.max(...buckets)]).nice().range([innerH, 0]);

  g.append("g")
    .attr("transform", `translate(0,${innerH})`)
    .call(axisBottom(x).tickValues(binLabels.filter((_, i) => i % Math.max(1, Math.floor(bins / 5)) === 0)))
    .selectAll("text")
    .attr("font-size", "0.58rem")
    .attr("fill", "rgba(11,14,20,0.48)");

  g.append("g")
    .call(axisLeft(y).ticks(4))
    .selectAll("text")
    .attr("font-size", "0.58rem")
    .attr("fill", "rgba(11,14,20,0.48)");

  g.selectAll(".bar")
    .data(buckets)
    .enter()
    .append("rect")
    .attr("x", (_d, i) => x(binLabels[i])!)
    .attr("y", (d) => y(d))
    .attr("width", x.bandwidth())
    .attr("height", (d) => innerH - y(d))
    .attr("fill", color)
    .attr("rx", 2);

  if (label) {
    svg
      .append("text")
      .attr("x", width / 2)
      .attr("y", height - 4)
      .attr("text-anchor", "middle")
      .attr("font-size", "0.62rem")
      .attr("fill", "rgba(11,14,20,0.42)")
      .text(label);
  }
}
