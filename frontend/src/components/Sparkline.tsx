interface SparklineProps {
  values: number[];
  label: string;
  width?: number;
  height?: number;
}

// A dependency-free inline trend line. Animation-free and compositor-light: it is
// just two SVG paths plus the latest-point marker.
export function Sparkline({ values, label, width = 116, height = 34 }: SparklineProps) {
  if (values.length < 2) {
    return <span className="spark-empty" role="img" aria-label={`${label}: not enough data`} />;
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const stepX = width / (values.length - 1);
  const yFor = (v: number) => height - 3 - ((v - min) / span) * (height - 6);

  const coords = values.map((v, i) => [i * stepX, yFor(v)] as const);
  const line = coords
    .map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`)
    .join(" ");
  const area = `${line} L${width.toFixed(1)} ${height} L0 ${height} Z`;
  const [lastX, lastY] = coords[coords.length - 1];

  return (
    <svg
      className="spark"
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`${label} trend over ${values.length} readings, low ${Math.round(min)}, high ${Math.round(max)}`}
    >
      <path className="spark-area" d={area} />
      <path className="spark-line" d={line} />
      <circle className="spark-dot" cx={lastX} cy={lastY} r={2.6} />
    </svg>
  );
}
