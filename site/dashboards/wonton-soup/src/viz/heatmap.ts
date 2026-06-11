import { scaleOrdinal } from "d3-scale";
import { select } from "d3-selection";

export interface HeatmapCell {
  row: string;
  col: string;
  value: number | null;
  category: string;
}

export interface HeatmapOpts {
  container: HTMLElement;
  cells: HeatmapCell[];
  rows: string[];
  cols: string[];
  colorMap: Record<string, string>;
  onCellClick?: (row: string, col: string) => void;
  cellSize?: number;
}

export function renderHeatmap(opts: HeatmapOpts): void {
  const { container, cells, rows, cols, colorMap, onCellClick, cellSize = 22 } = opts;

  const labelWidth = Math.max(160, Math.min(300, longest(rows) * 8 + 24));
  const labelHeight = Math.max(150, Math.min(200, longest(cols) * 6.5 + 42));
  const width = labelWidth + cols.length * cellSize;
  const height = labelHeight + rows.length * cellSize;
  const rowMaxChars = Math.max(14, Math.floor((labelWidth - 18) / 8));
  const colMaxChars = Math.max(16, Math.floor((labelHeight - 28) / 5.5));

  container.replaceChildren();

  const svg = select(container)
    .append("svg")
    .attr("width", width)
    .attr("height", height)
    .attr("viewBox", `0 0 ${width} ${height}`);

  const cellLookup = new Map<string, HeatmapCell>();
  for (const c of cells) {
    cellLookup.set(`${c.row}::${c.col}`, c);
  }

  const categories = Object.keys(colorMap);
  const colorScale = scaleOrdinal<string>().domain(categories).range(categories.map((c) => colorMap[c]));

  svg
    .selectAll(".hm-col-label")
    .data(cols)
    .enter()
    .append("text")
    .attr("class", "rescue-axis-label")
    .attr("x", (_d, i) => labelWidth + i * cellSize + cellSize / 2)
    .attr("y", labelHeight - 10)
    .attr("text-anchor", "start")
    .attr("dominant-baseline", "middle")
    .attr("transform", (_d, i) => {
      const x = labelWidth + i * cellSize + cellSize / 2;
      return `rotate(-90, ${x}, ${labelHeight - 10})`;
    })
    .text((d) => truncate(d, colMaxChars))
    .append("title")
    .text((d) => d);

  svg
    .selectAll(".hm-row-label")
    .data(rows)
    .enter()
    .append("text")
    .attr("class", "rescue-axis-label")
    .attr("x", labelWidth - 6)
    .attr("y", (_d, i) => labelHeight + i * cellSize + cellSize / 2)
    .attr("text-anchor", "end")
    .attr("dominant-baseline", "middle")
    .text((d) => truncate(d, rowMaxChars))
    .append("title")
    .text((d) => d);

  const cellGroup = svg.append("g").attr("transform", `translate(${labelWidth}, ${labelHeight})`);

  for (let ri = 0; ri < rows.length; ri++) {
    for (let ci = 0; ci < cols.length; ci++) {
      const cell = cellLookup.get(`${rows[ri]}::${cols[ci]}`);
      const cat = cell?.category ?? "no-data";

      const rect = cellGroup
        .append("rect")
        .attr("class", `rescue-cell ${cat}`)
        .attr("x", ci * cellSize + 1)
        .attr("y", ri * cellSize + 1)
        .attr("width", cellSize - 2)
        .attr("height", cellSize - 2)
        .attr("rx", 3)
        .attr("fill", colorScale(cat) ?? "#e8eaed");

      if (onCellClick) {
        rect.style("cursor", "pointer").on("click", () => {
          onCellClick(rows[ri], cols[ci]);
        });
      }

      rect
        .append("title")
        .text(`${rows[ri]} x ${cols[ci]}: ${cat}`);
    }
  }
}

function longest(values: string[]): number {
  return values.reduce((max, value) => Math.max(max, value.length), 0);
}

function truncate(s: string, max: number): string {
  return s.length > max ? s.slice(0, max - 1) + "\u2026" : s;
}
