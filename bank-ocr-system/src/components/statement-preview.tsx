"use client";

import { useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useOcrStore, type UploadFile } from "@/store/ocr-store";
import type { DocumentResult } from "@/lib/api";
import {
  FileText,
  Image as ImageIcon,
  ScanLine,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Eye,
  Table2,
  X,
  ZoomIn,
  ZoomOut,
  Maximize2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { formatUSD } from "@/lib/currency";

/* ═══════════════════════════════════════════
   SCAN OVERLAY — animated laser line
   ═══════════════════════════════════════════ */
function ScanOverlay() {
  return (
    <div className="pointer-events-none absolute inset-0 z-10 overflow-hidden rounded-xl">
      {/* Scanning laser line */}
      <motion.div
        className="absolute left-0 right-0 h-0.5"
        style={{
          background:
            "linear-gradient(90deg, transparent, rgba(99, 102, 241, 0.8), rgba(139, 92, 246, 0.8), transparent)",
          boxShadow: "0 0 20px rgba(99, 102, 241, 0.5), 0 0 60px rgba(99, 102, 241, 0.2)",
        }}
        animate={{
          top: ["0%", "100%", "0%"],
        }}
        transition={{
          duration: 3,
          repeat: Infinity,
          ease: "easeInOut",
        }}
      />

      {/* Scan region highlight */}
      <motion.div
        className="absolute inset-0 bg-gradient-to-b from-indigo-500/5 via-transparent to-violet-500/5"
        animate={{ opacity: [0.3, 0.6, 0.3] }}
        transition={{ duration: 2, repeat: Infinity }}
      />

      {/* Corner brackets */}
      <div className="absolute top-3 left-3 h-6 w-6 border-t-2 border-l-2 border-indigo-500/60 rounded-tl" />
      <div className="absolute top-3 right-3 h-6 w-6 border-t-2 border-r-2 border-indigo-500/60 rounded-tr" />
      <div className="absolute bottom-3 left-3 h-6 w-6 border-b-2 border-l-2 border-indigo-500/60 rounded-bl" />
      <div className="absolute bottom-3 right-3 h-6 w-6 border-b-2 border-r-2 border-indigo-500/60 rounded-br" />

      {/* Status badge */}
      <div className="absolute top-4 left-1/2 -translate-x-1/2 flex items-center gap-2 rounded-full bg-indigo-500/20 backdrop-blur-sm px-4 py-1.5 border border-indigo-500/30">
        <ScanLine className="h-3.5 w-3.5 text-indigo-400 animate-pulse" />
        <span className="text-xs font-semibold text-indigo-300">Scanning Document...</span>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════
   EXTRACTED DATA PANEL
   ═══════════════════════════════════════════ */
function ExtractedDataPanel({ doc }: { doc: DocumentResult }) {
  const txns = doc.transactions;
  const totalCredits = txns.reduce((sum, t) => sum + Number(t.credit || 0), 0);
  const totalDebits = txns.reduce((sum, t) => sum + Number(t.debit || 0), 0);

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="shrink-0 border-b border-border px-4 py-3 bg-card/50">
        <div className="flex items-center gap-2">
          <Table2 className="h-4 w-4 text-primary" />
          <h4 className="text-sm font-semibold text-foreground">Extracted Data</h4>
        </div>
        <p className="mt-1 text-xs text-muted-foreground">
          {txns.length} transactions found
        </p>
      </div>

      {/* Summary */}
      <div className="shrink-0 grid grid-cols-2 gap-2 p-3">
        <div className="rounded-lg bg-[var(--credit)]/5 px-3 py-2">
          <p className="text-[10px] font-medium uppercase tracking-wider text-[var(--credit)]">Credits</p>
          <p className="text-sm font-bold text-[var(--credit)]">
            {formatUSD(totalCredits, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
          </p>
        </div>
        <div className="rounded-lg bg-[var(--debit)]/5 px-3 py-2">
          <p className="text-[10px] font-medium uppercase tracking-wider text-[var(--debit)]">Debits</p>
          <p className="text-sm font-bold text-[var(--debit)]">
            {formatUSD(totalDebits, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
          </p>
        </div>
      </div>

      {/* Transaction list */}
      <div className="flex-1 overflow-y-auto px-3 pb-3">
        <div className="space-y-1">
          {txns.slice(0, 20).map((t, i) => (
            <div
              key={i}
              className="flex items-center justify-between rounded-lg px-3 py-2 text-xs hover:bg-muted/50 transition-colors"
            >
              <div className="min-w-0 flex-1 mr-3">
                <p className="truncate font-medium text-foreground">
                  {t.description || "—"}
                </p>
                <p className="text-muted-foreground">{t.date || "—"}</p>
              </div>
              <div className="shrink-0 text-right">
                {t.credit ? (
                  <span className="font-semibold text-[var(--credit)]">
                    +{formatUSD(Number(t.credit))}
                  </span>
                ) : t.debit ? (
                  <span className="font-semibold text-[var(--debit)]">
                    -{formatUSD(Number(t.debit))}
                  </span>
                ) : (
                  <span className="text-muted-foreground">—</span>
                )}
              </div>
            </div>
          ))}
          {txns.length > 20 && (
            <p className="text-center text-xs text-muted-foreground py-2">
              +{txns.length - 20} more transactions
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════
   FILE PREVIEW RENDERER
   ═══════════════════════════════════════════ */
function FilePreview({
  file,
  isProcessing,
  isProcessed,
  doc,
}: {
  file: UploadFile;
  isProcessing: boolean;
  isProcessed: boolean;
  doc?: DocumentResult;
}) {
  const [showData, setShowData] = useState(false);
  const [zoom, setZoom] = useState(1);
  const objectUrl = useMemo(() => URL.createObjectURL(file.file), [file.file]);
  const isPdf = file.file.name.toLowerCase().endsWith(".pdf");
  const isImage = /\.(png|jpg|jpeg|gif|webp)$/i.test(file.file.name);

  return (
    <div className="flex h-full flex-col">
      {/* Toolbar */}
      <div className="flex items-center justify-between border-b border-border px-4 py-2 bg-card/50 shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          {isPdf ? (
            <FileText className="h-4 w-4 text-red-500 shrink-0" />
          ) : (
            <ImageIcon className="h-4 w-4 text-blue-500 shrink-0" />
          )}
          <span className="text-sm font-medium text-foreground truncate">
            {file.file.name}
          </span>

          {/* Status badge */}
          {isProcessed && (
            <span className="flex items-center gap-1 rounded-full bg-[var(--credit)]/10 px-2 py-0.5 text-[10px] font-semibold text-[var(--credit)]">
              <CheckCircle2 className="h-3 w-3" /> Scanned
            </span>
          )}
          {isProcessing && (
            <span className="flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-semibold text-primary">
              <ScanLine className="h-3 w-3 animate-pulse" /> Processing
            </span>
          )}
        </div>

        <div className="flex items-center gap-1 shrink-0">
          {isImage && (
            <>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={() => setZoom(Math.max(0.5, zoom - 0.25))}
              >
                <ZoomOut className="h-3.5 w-3.5" />
              </Button>
              <span className="text-xs text-muted-foreground w-8 text-center">
                {Math.round(zoom * 100)}%
              </span>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={() => setZoom(Math.min(3, zoom + 0.25))}
              >
                <ZoomIn className="h-3.5 w-3.5" />
              </Button>
            </>
          )}
          {isProcessed && doc && (
            <Button
              variant={showData ? "default" : "ghost"}
              size="sm"
              className="ml-2 h-7 gap-1.5 text-xs"
              onClick={() => setShowData(!showData)}
            >
              {showData ? <Eye className="h-3 w-3" /> : <Table2 className="h-3 w-3" />}
              {showData ? "Preview" : "Data"}
            </Button>
          )}
        </div>
      </div>

      {/* Content Area */}
      <div className="relative flex-1 overflow-hidden">
        <AnimatePresence mode="wait">
          {showData && doc ? (
            <motion.div
              key="data"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              className="absolute inset-0 bg-card"
            >
              <ExtractedDataPanel doc={doc} />
            </motion.div>
          ) : (
            <motion.div
              key="preview"
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 20 }}
              className="absolute inset-0"
            >
              {/* Document preview */}
              <div className="relative h-full w-full overflow-auto bg-muted/20">
                {isPdf ? (
                  <iframe
                    src={`${objectUrl}#toolbar=0&navpanes=0`}
                    className="h-full w-full border-0"
                    title={`Preview of ${file.file.name}`}
                  />
                ) : isImage ? (
                  <div className="flex h-full items-center justify-center p-4">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={objectUrl}
                      alt={file.file.name}
                      className="max-h-full max-w-full object-contain transition-transform duration-200"
                      style={{ transform: `scale(${zoom})` }}
                    />
                  </div>
                ) : (
                  <div className="flex h-full items-center justify-center">
                    <p className="text-sm text-muted-foreground">
                      Preview not available for this file type
                    </p>
                  </div>
                )}

                {/* Scanning overlay */}
                {isProcessing && <ScanOverlay />}

                {/* Processed overlay badge */}
                {isProcessed && !showData && doc && (
                  <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-2 rounded-xl bg-card/90 backdrop-blur-sm px-4 py-2 border border-[var(--credit)]/20 shadow-lg">
                    <CheckCircle2 className="h-4 w-4 text-[var(--credit)]" />
                    <span className="text-sm font-semibold text-foreground">
                      {doc.transactions.length} transactions extracted
                    </span>
                  </div>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════
   MAIN COMPONENT
   ═══════════════════════════════════════════ */
export function StatementPreview() {
  const { files, documents, isProcessing } = useOcrStore();
  const [activeIndex, setActiveIndex] = useState(0);
  const [expanded, setExpanded] = useState(false);

  // Only show files that have been uploaded (not pending)
  const previewFiles = files.filter(
    (f) => f.status === "uploading" || f.status === "success" || f.status === "pending"
  );

  if (previewFiles.length === 0) return null;

  const activeFile = previewFiles[Math.min(activeIndex, previewFiles.length - 1)];
  if (!activeFile) return null;

  const matchedDoc = documents.find(
    (d) => d.filename.toLowerCase() === activeFile.file.name.toLowerCase()
  );
  const isFileProcessing = activeFile.status === "uploading";
  const isFileProcessed = activeFile.status === "success" && !!matchedDoc;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn(
        "rounded-2xl border border-border bg-card shadow-sm overflow-hidden transition-all duration-300",
        expanded ? "fixed inset-4 z-50" : "h-[420px]"
      )}
    >
      {/* Fullscreen backdrop */}
      {expanded && (
        <div
          className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm"
          onClick={() => setExpanded(false)}
        />
      )}

      <div
        className={cn(
          "flex flex-col h-full",
          expanded && "relative z-50"
        )}
      >
        {/* Tab bar for multiple files */}
        {previewFiles.length > 1 && (
          <div className="flex items-center gap-2 border-b border-border px-3 py-2 bg-muted/30 shrink-0 overflow-x-auto">
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 shrink-0"
              disabled={activeIndex === 0}
              onClick={() => setActiveIndex(Math.max(0, activeIndex - 1))}
            >
              <ChevronLeft className="h-3.5 w-3.5" />
            </Button>

            <div className="flex gap-1 min-w-0 overflow-x-auto">
              {previewFiles.map((f, i) => {
                const hasDoc = documents.some(
                  (d) => d.filename.toLowerCase() === f.file.name.toLowerCase()
                );
                return (
                  <button
                    key={f.id}
                    onClick={() => setActiveIndex(i)}
                    className={cn(
                      "flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium transition-colors whitespace-nowrap",
                      i === activeIndex
                        ? "bg-primary/10 text-primary"
                        : "text-muted-foreground hover:text-foreground hover:bg-muted"
                    )}
                  >
                    {f.status === "uploading" ? (
                      <ScanLine className="h-3 w-3 animate-pulse" />
                    ) : hasDoc ? (
                      <CheckCircle2 className="h-3 w-3 text-[var(--credit)]" />
                    ) : (
                      <FileText className="h-3 w-3" />
                    )}
                    <span className="max-w-[100px] truncate">{f.file.name}</span>
                  </button>
                );
              })}
            </div>

            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 shrink-0"
              disabled={activeIndex >= previewFiles.length - 1}
              onClick={() =>
                setActiveIndex(Math.min(previewFiles.length - 1, activeIndex + 1))
              }
            >
              <ChevronRight className="h-3.5 w-3.5" />
            </Button>

            <div className="ml-auto shrink-0">
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6"
                onClick={() => setExpanded(!expanded)}
              >
                {expanded ? (
                  <X className="h-3.5 w-3.5" />
                ) : (
                  <Maximize2 className="h-3.5 w-3.5" />
                )}
              </Button>
            </div>
          </div>
        )}

        {/* Preview */}
        <div className="flex-1 min-h-0">
          <AnimatePresence mode="wait">
            <motion.div
              key={activeFile.id}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="h-full"
            >
              <FilePreview
                file={activeFile}
                isProcessing={isFileProcessing}
                isProcessed={isFileProcessed}
                doc={matchedDoc}
              />
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </motion.div>
  );
}
