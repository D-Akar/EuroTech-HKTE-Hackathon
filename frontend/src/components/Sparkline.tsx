interface SparklineProps {
  values: number[];
  label: string;
  width?: number; // plotting width, excluding the tick-label gutter
  height?: number;
}

const GUTTER = 30; // room on the right for the min/max tick labels

// Compact axis tick: 18195 -> "18k", 2459 -> "2.5k", 55 -> "55", 7.3 -> "7.3".
function fmtTick(v: number): string {
  if (Math.abs(v) >= 1000) {
    const k = v / 1000;
    return `${k >= 10 ? Math.round(k) : Math.round(k * 10) / 10}k`;
  }
  return `${Math.round(v * 10) / 10}`;
}

// A dependency-free inline trend line with a light y-scale. Animation-free and
// compositor-light: three faint gridlines (min/mid/max), the line + fill, the
// latest-point marker, and two numeric ticks aligned to the min and max lines.
export function Sparkline({ values, label, width = 112, height = 40 }: SparklineProps) {
  const totalW = width + GUTTER;
  if (values.length < 2) {
    return <span className="spark-empty" role="img" aria-label={`${label}: not enough data`} />;
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const padY = 5;
  const stepX = width / (values.length - 1);
  const yFor = (v: number) => height - padY - ((v - min) / span) * (height - padY * 2);

  const coords = values.map((v, i) => [i * stepX, yFor(v)] as const);
  const line = coords
    .map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`)
    .join(" ");
  const area = `${line} L${width.toFixed(1)} ${height} L0 ${height} Z`;
  const [lastX, lastY] = coords[coords.length - 1];
  const yMax = yFor(max);
  const yMin = yFor(min);
  const yMid = yFor((max + min) / 2);

  return (
    <svg
      className="spark"
      width={totalW}
      height={height}
      viewBox={`0 0 ${totalW} ${height}`}
      role="img"
      aria-label={`${label} trend over ${values.length} readings, low ${Math.round(min)}, high ${Math.round(max)}`}
    >
      <line className="spark-grid" x1="0" y1={yMax} x2={width} y2={yMax} />
      <line className="spark-grid spark-grid-mid" x1="0" y1={yMid} x2={width} y2={yMid} />
      <line className="spark-grid" x1="0" y1={yMin} x2={width} y2={yMin} />
      <path className="spark-area" d={area} />
      <path className="spark-line" d={line} />
      <circle className="spark-dot" cx={lastX} cy={lastY} r={2.6} />
      <text className="spark-tick" x={width + 4} y={yMax} dy="0.32em">
        {fmtTick(max)}
      </text>
      <text className="spark-tick" x={width + 4} y={yMin} dy="0.32em">
        {fmtTick(min)}
      </text>
    </svg>
  );
}
