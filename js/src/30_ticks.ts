// Presentation-only value formatting. Canonical axis/colorbar tick positions
// and labels are resolved by Rust through XYTK/XYTO (M2 #869).

export function fmtNumberSpec(v, format) {
  if (typeof format !== "string" || !Number.isFinite(Number(v))) return null;
  const match = format.match(/^([^,.%]*)(,)?\.([0-9]+)(f?)(%?)([^,.%]*)$/);
  if (!match) return null;
  const [, prefix, group, digitsText, f, pct, suffix] = match;
  if (!f && !pct && (prefix || suffix)) return null;
  const digits = Number(digitsText);
  const percent = pct === "%";
  const value = percent ? Number(v) * 100 : Number(v);
  const rendered = group
    ? value.toLocaleString(undefined, {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    })
    : value.toFixed(digits);
  return `${prefix}${rendered}${percent ? "%" : ""}${suffix}`;
}

export function fmtCategory(v, categories) {
  const i = Math.round(v);
  return i >= 0 && i < categories.length ? String(categories[i]) : "";
}

// Presentation-only angular readout for hover/a11y text. This deliberately
// accepts a value that has already been selected by the renderer; it owns no
// tick ladder, window filtering, label admission, or axis cache policy.
export function fmtAngle(v, unit, format?: any) {
  const authored = fmtNumberSpec(v, format);
  if (authored !== null) return authored;
  const value = Number(v);
  if (!Number.isFinite(value)) return String(v);
  if (unit === "degrees") return `${fmtValue(value)}°`;
  if (Math.abs(value) < 1e-12) return "0";
  const fraction = value / Math.PI;
  for (const denominator of [1, 2, 3, 4, 6, 8, 12]) {
    const nearest = Math.round(fraction * denominator);
    // Hover values are decoded offset-f32 (§4/§16); this tolerance recognizes
    // that representation of an exact pi fraction without selecting ticks.
    if (nearest !== 0 && Math.abs(fraction * denominator - nearest) < 1e-6) {
      const numerator = Math.abs(nearest) === 1 ? "" : String(Math.abs(nearest));
      const body = `${nearest < 0 ? "-" : ""}${numerator}π`;
      return denominator === 1 ? body : `${body}/${denominator}`;
    }
  }
  return fmtValue(value);
}

export function fmtValue(v, kind?: any) {
  if (kind === "time_ms") {
    const d = new Date(v);
    return d.toISOString().replace("T", " ").replace(".000Z", "Z");
  }
  if (typeof v === "string") return v;
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v);
  if (n === 0) return "0";
  const av = Math.abs(n);
  if (av >= 1e6 || av < 1e-4) return n.toExponential(3);
  return (Math.round(n * 1e4) / 1e4).toString();
}
