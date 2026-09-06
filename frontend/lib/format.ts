export function formatCurrency(value: number | null | undefined): string {
  if (value === null || value === undefined) return "--";
  const sign = value < 0 ? "-" : "";
  return `${sign}\u20B9${Math.abs(value).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

export function formatPct(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined) return "--";
  return `${value.toFixed(digits)}%`;
}

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return "--";
  try { return new Date(iso).toLocaleTimeString("en-IN", { hour12: false }); } catch { return iso; }
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "--";
  try { return new Date(iso).toLocaleString("en-IN"); } catch { return iso; }
}
