import { cn } from "@/lib/utils";
import {
  formatOcrAccuracyLabel,
  getOcrAccuracyPercent,
  getOcrAccuracyTone,
  OCR_ACCURACY_STYLES,
} from "@/lib/ocr-confidence";

type AccuracyBadgeProps = {
  confidence: number | null | undefined;
  className?: string;
  showCheck?: boolean;
};

export function AccuracyBadge({
  confidence,
  className,
  showCheck = false,
}: AccuracyBadgeProps) {
  const pct = getOcrAccuracyPercent(confidence);
  const label = formatOcrAccuracyLabel(confidence);
  const tone = getOcrAccuracyTone(confidence);

  if (pct == null || !label) {
    return (
      <span
        className={cn(
          "shrink-0 rounded-lg border px-2.5 py-1 text-xs font-semibold",
          OCR_ACCURACY_STYLES.unknown,
          className
        )}
      >
        N/A
      </span>
    );
  }

  return (
    <span
      className={cn(
        "shrink-0 rounded-lg border px-2.5 py-1 text-xs font-semibold tabular-nums",
        OCR_ACCURACY_STYLES[tone],
        className
      )}
      title={`OCR extraction accuracy: ${pct}%`}
    >
      {showCheck ? ` ${pct}%` : `${pct}% accurate`}
    </span>
  );
}
