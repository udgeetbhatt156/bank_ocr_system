"use client";

import { motion } from "framer-motion";
import { useOcrStore } from "@/store/ocr-store";
import { Progress } from "@/components/ui/progress";
import { CheckCircle2, Loader2, AlertCircle, Clock } from "lucide-react";

export function ProcessingStatus() {
  const { files, uploadProgress, isProcessing } = useOcrStore();

  if (files.length === 0) return null;

  const total = files.length;
  const done = files.filter((f) => f.status === "success").length;
  const failed = files.filter((f) => f.status === "error").length;
  const processing = files.filter((f) => f.status === "uploading").length;
  const pending = files.filter((f) => f.status === "pending").length;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-2xl border border-border bg-card p-5 shadow-sm"
    >
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-foreground">
          Processing Status
        </h3>
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          {done > 0 && (
            <span className="flex items-center gap-1 text-[var(--credit)]">
              <CheckCircle2 className="h-3.5 w-3.5" /> {done} done
            </span>
          )}
          {processing > 0 && (
            <span className="flex items-center gap-1 text-primary">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> {processing}{" "}
              processing
            </span>
          )}
          {failed > 0 && (
            <span className="flex items-center gap-1 text-[var(--debit)]">
              <AlertCircle className="h-3.5 w-3.5" /> {failed} failed
            </span>
          )}
          {pending > 0 && (
            <span className="flex items-center gap-1">
              <Clock className="h-3.5 w-3.5" /> {pending} pending
            </span>
          )}
        </div>
      </div>

      {/* Overall progress bar */}
      {isProcessing && (
        <div className="space-y-1.5">
          <Progress value={uploadProgress} className="h-2" />
          <p className="text-right text-xs text-muted-foreground">
            {uploadProgress}% uploaded
          </p>
        </div>
      )}

      {/* Completion summary */}
      {!isProcessing && done > 0 && (
        <div className="flex items-center gap-2 rounded-xl bg-[var(--credit)]/5 px-4 py-3">
          <CheckCircle2 className="h-5 w-5 text-[var(--credit)]" />
          <div>
            <p className="text-sm font-medium text-foreground">
              Processing Complete
            </p>
            <p className="text-xs text-muted-foreground">
              {done} of {total} statements processed successfully
              {failed > 0 && `, ${failed} failed`}
            </p>
          </div>
        </div>
      )}
    </motion.div>
  );
}
