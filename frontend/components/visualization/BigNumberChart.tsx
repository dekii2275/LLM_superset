type BigNumberChartProps = {
  value: string;
};

export function BigNumberChart({ value }: BigNumberChartProps) {
  return (
    <div className="big-number-chart" aria-label={`Revenue: ${value}`}>
      <div className="big-number-topline"><span className="big-number-indicator" /> TOTAL REVENUE</div>
      <strong className="big-number-value">{value}</strong>
      <div className="big-number-footnote"><span className="positive-change">↗ 8.4%</span> vs. previous year <span className="mock-baseline">DEMO VALUE</span></div>
      <div className="big-number-sparkline" aria-hidden="true">
        <svg viewBox="0 0 360 62" preserveAspectRatio="none">
          <path d="M0 48 C30 41 40 50 68 37 S112 40 136 26 S181 39 206 20 S251 28 274 12 S324 18 360 4" />
          <path className="sparkline-fill" d="M0 48 C30 41 40 50 68 37 S112 40 136 26 S181 39 206 20 S251 28 274 12 S324 18 360 4 L360 62 L0 62Z" />
        </svg>
      </div>
    </div>
  );
}
