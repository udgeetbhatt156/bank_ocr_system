/** US dollar formatting for bank statement amounts */
export function formatUSD(
  value: number | null | undefined,
  options?: { minimumFractionDigits?: number; maximumFractionDigits?: number }
): string {
  if (value === null || value === undefined) return "—";
  const num = Number(value);
  if (isNaN(num)) return "—";

  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: options?.minimumFractionDigits ?? 2,
    maximumFractionDigits: options?.maximumFractionDigits ?? 2,
  }).format(num);
}
