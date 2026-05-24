"use client";

import { useCallback } from "react";
import { useDropzone } from "react-dropzone";
import { motion, AnimatePresence } from "framer-motion";
import { toast } from "sonner";
import { useOcrStore } from "@/store/ocr-store";
import {
  CloudUpload,
  FileText,
  X,
  FileImage,
  HardDrive,
  AlertCircle,
  CheckCircle2,
  Loader2,
  XCircle,
  Copy,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

function formatFileSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function getFileIcon(name: string) {
  const ext = name.split(".").pop()?.toLowerCase();
  if (ext === "pdf") return <FileText className="h-5 w-5 text-red-500" />;
  if (["png", "jpg", "jpeg"].includes(ext || ""))
    return <FileImage className="h-5 w-5 text-blue-500" />;
  return <HardDrive className="h-5 w-5 text-muted-foreground" />;
}

const STATUS_CONFIG = {
  pending: {
    row: "hover:bg-muted",
    badge: null,
  },
  uploading: {
    row: "bg-primary/5",
    badge: null,
  },
  success: {
    row: "bg-[var(--credit)]/5",
    badge: null,
  },
  error: {
    row: "bg-[var(--debit)]/5",
    badge: null,
  },
  duplicate: {
    row: "bg-amber-500/5 border border-amber-500/20",
    badge: "Already uploaded",
  },
} as const;

export function UploadDropzone() {
  const { files, addFiles, removeFile, isProcessing } = useOcrStore();

  const onDrop = useCallback(
    (accepted: File[]) => {
      if (!accepted.length) return;
      const { duplicates } = addFiles(accepted);

      if (duplicates.length > 0 && duplicates.length === accepted.length) {
        // All files were duplicates
        toast.warning(
          duplicates.length === 1
            ? `"${duplicates[0]}" has already been uploaded.`
            : `${duplicates.length} files have already been uploaded.`,
          { description: "Remove the duplicate entries or clear all to re-upload." }
        );
      } else if (duplicates.length > 0) {
        // Mixed: some new, some duplicate
        toast.warning(
          `${duplicates.length} duplicate${duplicates.length > 1 ? "s" : ""} skipped`,
          {
            description: duplicates.join(", "),
          }
        );
      }
    },
    [addFiles]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "application/pdf": [".pdf"],
      "image/png": [".png"],
      "image/jpeg": [".jpg", ".jpeg"],
    },
    multiple: true,
    disabled: isProcessing,
  });

  const pendingCount = files.filter((f) => f.status === "pending").length;
  const duplicateCount = files.filter((f) => f.status === "duplicate").length;

  return (
    <div className="space-y-4">
      {/* Dropzone area */}
      <div
        {...getRootProps()}
        className={cn(
          "group relative cursor-pointer rounded-2xl border-2 border-dashed p-10 text-center transition-all duration-300",
          isDragActive
            ? "border-primary bg-primary/5 scale-[1.01]"
            : "border-border bg-card hover:border-primary/50 hover:bg-primary/[0.02]",
          isProcessing && "pointer-events-none opacity-60"
        )}
      >
        <input {...getInputProps()} />

        <motion.div
          animate={isDragActive ? { scale: 1.08, y: -4 } : { scale: 1, y: 0 }}
          transition={{ type: "spring", bounce: 0.3 }}
          className="flex flex-col items-center"
        >
          <div
            className={cn(
              "mb-4 flex h-16 w-16 items-center justify-center rounded-2xl transition-colors duration-300",
              isDragActive
                ? "bg-primary/15 text-primary"
                : "bg-muted text-muted-foreground group-hover:bg-primary/10 group-hover:text-primary"
            )}
          >
            <CloudUpload className="h-8 w-8" />
          </div>
          <h3 className="text-base font-semibold text-foreground">
            {isDragActive ? "Drop your files here" : "Upload Bank Statements"}
          </h3>
          <p className="mt-1.5 max-w-sm text-sm text-muted-foreground">
            Drag and drop your PDF or image files here, or{" "}
            <span className="font-medium text-primary">browse files</span>
          </p>
          <p className="mt-2 text-xs text-muted-foreground/70">
            Supports PDF, PNG, JPG • Multiple files allowed • Duplicates are blocked
          </p>
        </motion.div>
      </div>

      {/* File list */}
      <AnimatePresence>
        {files.length > 0 && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="space-y-2 overflow-hidden"
          >
            {/* Header row */}
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-foreground">
                {files.length} file{files.length > 1 ? "s" : ""} selected
                {duplicateCount > 0 && (
                  <span className="ml-2 text-xs font-normal text-amber-500">
                    ({duplicateCount} duplicate{duplicateCount > 1 ? "s" : ""} blocked)
                  </span>
                )}
              </p>
              <p className="text-xs text-muted-foreground">
                {formatFileSize(
                  files
                    .filter((f) => f.status !== "duplicate")
                    .reduce((sum, f) => sum + f.file.size, 0)
                )}{" "}
                to process
              </p>
            </div>

            {/* Duplicate warning banner */}
            {duplicateCount > 0 && (
              <motion.div
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex items-start gap-2.5 rounded-xl border border-amber-500/30 bg-amber-500/8 px-3.5 py-2.5"
              >
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
                <div className="text-xs text-amber-700 dark:text-amber-400">
                  <span className="font-semibold">
                    {duplicateCount} duplicate file{duplicateCount > 1 ? "s" : ""} detected.
                  </span>{" "}
                  These statements have already been uploaded and will be skipped.
                  Remove them or click the × to dismiss.
                </div>
              </motion.div>
            )}

            {/* File rows */}
            <div className="max-h-72 space-y-1.5 overflow-y-auto rounded-xl border border-border bg-card p-2">
              {files.map((f) => {
                const cfg = STATUS_CONFIG[f.status];
                return (
                  <motion.div
                    key={f.id}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: 10 }}
                    className={cn(
                      "flex items-center justify-between rounded-lg px-3 py-2.5 transition-colors",
                      cfg.row
                    )}
                  >
                    {/* Left: icon + name */}
                    <div className="flex items-center gap-3 min-w-0">
                      {f.status === "duplicate"
                        ? <Copy className="h-5 w-5 shrink-0 text-amber-500" />
                        : getFileIcon(f.file.name)
                      }
                      <div className="min-w-0">
                        <p className={cn(
                          "truncate text-sm font-medium",
                          f.status === "duplicate"
                            ? "text-amber-600 dark:text-amber-400"
                            : "text-foreground"
                        )}>
                          {f.file.name}
                        </p>
                        <div className="flex items-center gap-1.5">
                          <p className="text-xs text-muted-foreground">
                            {formatFileSize(f.file.size)}
                          </p>
                          {f.status === "duplicate" && (
                            <span className="rounded-full bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-600 dark:text-amber-400">
                              Already uploaded
                            </span>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Right: status indicator */}
                    <div className="flex items-center gap-2 shrink-0 ml-2">
                      {f.status === "uploading" && (
                        <Loader2 className="h-4 w-4 animate-spin text-primary" />
                      )}
                      {f.status === "success" && (
                        <CheckCircle2 className="h-4 w-4 text-[var(--credit)]" />
                      )}
                      {f.status === "error" && (
                        <span className="flex items-center gap-1 text-xs font-medium text-[var(--debit)]">
                          <XCircle className="h-3.5 w-3.5" /> Failed
                        </span>
                      )}
                      {(f.status === "pending" || f.status === "duplicate") && (
                        <Button
                          variant="ghost"
                          size="icon"
                          className={cn(
                            "h-7 w-7",
                            f.status === "duplicate"
                              ? "text-amber-500 hover:text-amber-700 hover:bg-amber-500/10"
                              : "text-muted-foreground hover:text-destructive"
                          )}
                          onClick={(e) => {
                            e.stopPropagation();
                            removeFile(f.id);
                          }}
                        >
                          <X className="h-3.5 w-3.5" />
                        </Button>
                      )}
                    </div>
                  </motion.div>
                );
              })}
            </div>

            {/* Quick action: remove all duplicates */}
            {duplicateCount > 0 && !isProcessing && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="flex justify-end"
              >
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 gap-1.5 text-xs text-amber-600 hover:bg-amber-500/10 hover:text-amber-700 dark:text-amber-400"
                  onClick={() => {
                    const { files: currentFiles } = useOcrStore.getState();
                    currentFiles
                      .filter((f) => f.status === "duplicate")
                      .forEach((f) => removeFile(f.id));
                  }}
                >
                  <X className="h-3 w-3" />
                  Remove all duplicates
                </Button>
              </motion.div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
