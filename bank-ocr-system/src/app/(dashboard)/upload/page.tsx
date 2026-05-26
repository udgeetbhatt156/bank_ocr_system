"use client";

import { toast } from "sonner";
import { motion } from "framer-motion";
import { useRouter } from "next/navigation";
import { useOcrStore } from "@/store/ocr-store";
import { UploadDropzone } from "@/components/upload-dropzone";
import { ProcessingStatus } from "@/components/processing-status";
import { StatementPreview } from "@/components/statement-preview";
import { Button } from "@/components/ui/button";
import { Loader2, Rocket, Trash2, ArrowRight } from "lucide-react";

export default function UploadPage() {
  const { files, isProcessing, processFiles, clearFiles, clearResults, documents } =
    useOcrStore();
  const router = useRouter();

  const pendingCount   = files.filter((f) => f.status === "pending").length;
  const duplicateCount = files.filter((f) => f.status === "duplicate").length;
  const hasResults = documents.length > 0;

  const handleProcess = async () => {
    if (!pendingCount) {
      if (duplicateCount > 0) {
        toast.warning("All selected files are duplicates — nothing to process.", {
          description: "Remove the duplicate entries or clear all to start fresh.",
        });
      } else {
        toast.warning("No pending files to process");
      }
      return;
    }
    try {
      await processFiles();
      toast.success(
        `${pendingCount} statement${pendingCount !== 1 ? "s" : ""} processed successfully!`
      );
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to process statements"
      );
    }
  };

  return (
    <div className="mx-auto max-w-6xl space-y-4">
      {/* Page header */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <h2 className="text-xl font-bold text-foreground">
          Upload Bank Statements
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Upload PDF or image files of bank statements for OCR extraction. Supports
          batch processing of multiple files.
        </p>
      </motion.div>

      {/* Dropzone */}
      <UploadDropzone />

      {/* Action buttons */}
      {files.length > 0 && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="flex flex-wrap items-center justify-between gap-3"
        >
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              clearFiles();
              clearResults();
            }}
            disabled={isProcessing}
            className="gap-2"
          >
            <Trash2 className="h-3.5 w-3.5" />
            Clear All
          </Button>

          <div className="flex items-center gap-3">
            {hasResults && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => router.push("/transactions")}
                className="gap-2"
              >
                View Transactions <ArrowRight className="h-3.5 w-3.5" />
              </Button>
            )}
            <Button
              onClick={handleProcess}
              disabled={isProcessing || pendingCount === 0}
              className="gap-2"
              size="lg"
            >
              {isProcessing ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Processing...
                </>
              ) : (
                <>
                  <Rocket className="h-4 w-4" />
                  Process {pendingCount} Statement{pendingCount !== 1 ? "s" : ""}
                </>
              )}
            </Button>
          </div>
        </motion.div>
      )}

      {/* Statement Preview — renders uploaded documents with scan animation */}
      <StatementPreview />

      {/* Processing status */}
      <ProcessingStatus />

      {/* Quick results preview */}
      {hasResults && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="rounded-2xl border border-border bg-card p-5 shadow-sm"
        >
          <h3 className="text-sm font-semibold text-foreground">
            Quick Preview
          </h3>
          <p className="mt-1 text-xs text-muted-foreground">
            Extracted from {documents.length} document
            {documents.length !== 1 ? "s" : ""}
          </p>

          <div className="mt-4 space-y-3">
            {documents.map((doc) => (
              <div
                key={doc.filename}
                className="flex items-center justify-between rounded-xl bg-muted/50 px-4 py-3"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-foreground">
                    {doc.filename}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {doc.transactions.length} transactions found
                  </p>
                </div>
                <span className="shrink-0 rounded-lg bg-[var(--credit)]/10 px-2.5 py-1 text-xs font-semibold text-[var(--credit)]">
                  ✓ Extracted
                </span>
              </div>
            ))}
          </div>

          <Button
            onClick={() => router.push("/transactions")}
            className="mt-4 w-full gap-2"
          >
            View All Transactions <ArrowRight className="h-4 w-4" />
          </Button>
        </motion.div>
      )}
    </div>
  );
}
