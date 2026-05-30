/** Normalize OCR confidence (0–1 float or 0–100) to a display percentage. */
export function getOcrAccuracyPercent(
  confidence: number | null | undefined
): number | null {
  if (confidence == null || Number.isNaN(confidence)) return null;
  if (confidence <= 1) return Math.round(confidence * 100);
  return Math.round(Math.min(confidence, 100));
}

export function formatOcrAccuracyLabel(
  confidence: number | null | undefined
): string | null {
  const pct = getOcrAccuracyPercent(confidence);
  if (pct == null) return null;
  return `${pct}% accurate`;
}

export function getOcrAccuracyTone(
  confidence: number | null | undefined
): "high" | "medium" | "low" | "unknown" {
  const pct = getOcrAccuracyPercent(confidence);
  if (pct == null) return "unknown";
  if (pct >= 90) return "high";
  if (pct >= 70) return "medium";
  return "low";
}

export const OCR_ACCURACY_STYLES = {
  high: "bg-[var(--credit)]/10 text-[var(--credit)] border-[var(--credit)]/20",
  medium: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20",
  low: "bg-[var(--debit)]/10 text-[var(--debit)] border-[var(--debit)]/20",
  unknown: "bg-muted text-muted-foreground border-border",
} as const;
