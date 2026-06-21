// Shared civic color ramp. Used by both the choropleth map and the comparison
// chart so the two views encode value with the same colors.

// Null geographies (no value for the active metric) render in this neutral grey.
export const NULL_COLOR = "#d8dee6";
// Flat fill used when every geography shares one value (e.g. CMA-level CMHC data).
export const FLAT_COLOR = "#68b7aa";
// 3-stop ramp: pale green -> teal -> rust, interpolated across the value range.
export const RAMP = ["#f1f7f0", "#68b7aa", "#a64822"];

export function mixHex(a: string, b: string, t: number): string {
  const parse = (hex: string): [number, number, number] => [
    parseInt(hex.slice(1, 3), 16),
    parseInt(hex.slice(3, 5), 16),
    parseInt(hex.slice(5, 7), 16)
  ];
  const [ar, ag, ab] = parse(a);
  const [br, bg, bb] = parse(b);
  const channel = (x: number, y: number) => Math.round(x + (y - x) * t);
  const toHex = (n: number) => n.toString(16).padStart(2, "0");
  return `#${toHex(channel(ar, br))}${toHex(channel(ag, bg))}${toHex(channel(ab, bb))}`;
}

/** Sample the 3-color ramp at fraction t in [0, 1]. */
export function rampColorAt(t: number): string {
  const clamped = Math.min(1, Math.max(0, t));
  const scaled = clamped * (RAMP.length - 1);
  const lower = Math.floor(scaled);
  const upper = Math.min(RAMP.length - 1, lower + 1);
  const frac = scaled - lower;
  return mixHex(RAMP[lower], RAMP[upper], frac);
}

/** Color for a value given the domain [min, max]. Falls back to the flat color
 * when the domain has no spread (a single value across all areas). */
export function rampColorForValue(value: number, min: number, max: number): string {
  if (!Number.isFinite(value)) return NULL_COLOR;
  if (max <= min) return FLAT_COLOR;
  return rampColorAt((value - min) / (max - min));
}
