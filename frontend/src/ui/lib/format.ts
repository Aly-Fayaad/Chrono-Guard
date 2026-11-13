/** Formatted deviation score, e.g. "+12.8σ". */
export function fmtSigma(z: number): string {
  return `${z >= 0 ? "+" : "−"}${Math.abs(z).toFixed(1)}σ`;
}

/** Boolean-attr for signed mono numbers. */
export function fmtNum(v: number): string {
  return v.toLocaleString("en-US", { maximumFractionDigits: 2 });
}
