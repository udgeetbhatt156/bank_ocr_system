"use client";

import { useCallback, useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import { format } from "date-fns";
import {
  apiDeleteStatement,
  apiFetchStatement,
  apiFetchStatementList,
  type DocumentResult,
  type StatementListItem,
} from "@/lib/api";
import { useOcrStore } from "@/store/ocr-store";
import { formatUSD } from "@/lib/currency";
import { StatementDetailView } from "@/components/statement-detail-view";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  FileText,
  ExternalLink,
  RefreshCw,
  History,
  Upload,
  Trash2,
  Loader2,
} from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";

export default function HistoryPage() {
  const pathname = usePathname();
  const [statements, setStatements] = useState<StatementListItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedDoc, setSelectedDoc] = useState<DocumentResult | null>(null);
  const [isLoadingList, setIsLoadingList] = useState(true);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const loadList = useCallback(async () => {
    setIsLoadingList(true);
    try {
      const { statements: list } = await apiFetchStatementList();
      setStatements(list);
      // setSelectedId((prev) => prev ?? list[0]?.id ?? null);
      if (selectedId && !list.some((item) => item.id === selectedId)) {
        setSelectedId(null);
      }
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to load statement history"
      );
    } finally {
      setIsLoadingList(false);
    }
  }, []);

  useEffect(() => {
    if (pathname === "/history") {
      loadList();
    }
  }, [pathname, loadList]);

  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible" && pathname === "/history") {
        loadList();
      }
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [pathname, loadList]);

  useEffect(() => {
    if (!selectedId) {
      setSelectedDoc(null);
      return;
    }

    let cancelled = false;
    setIsLoadingDetail(true);

    apiFetchStatement(selectedId)
      .then(({ document }) => {
        if (!cancelled) setSelectedDoc(document);
      })
      .catch((err) => {
        if (!cancelled) {
          toast.error(
            err instanceof Error ? err.message : "Failed to load statement"
          );
          setSelectedDoc(null);
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoadingDetail(false);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  const selectedMeta = statements.find((s) => s.id === selectedId);

  const handleDelete = async (id: string, fileName: string) => {
    const confirmed = window.confirm(
      `Delete "${fileName}"?\n\nThis will permanently remove the statement and all its transactions.`
    );
    if (!confirmed) return;

    setDeletingId(id);
    try {
      await apiDeleteStatement(id);

      setStatements((prev) => {
        const next = prev.filter((s) => s.id !== id);
        if (selectedId === id) {
          setSelectedId(next[0]?.id ?? null);
          setSelectedDoc(null);
        }
        return next;
      });

      useOcrStore.setState((state) => ({
        documents: state.documents.filter((d) => d.id !== id),
      }));

      toast.success("Statement deleted");
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to delete statement"
      );
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="mx-auto max-w-8xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-foreground">Statement History</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            View saved bank statements and their extracted transactions.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={loadList} className="gap-2">
            <RefreshCw className="h-4 w-4" />
            Refresh
          </Button>
          <Link href="/upload">
            <Button size="sm" className="gap-2">
              <Upload className="h-4 w-4" />
              Upload New
            </Button>
          </Link>
        </div>
      </div>

      {isLoadingList ? (
        <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
          <Skeleton className="h-96 rounded-2xl" />
          <Skeleton className="h-96 rounded-2xl" />
        </div>
      ) : statements.length === 0 ? (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border bg-card/50 py-20 text-center"
        >
          <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10">
            <History className="h-7 w-7 text-primary" />
          </div>
          <h3 className="text-lg font-semibold">No saved statements yet</h3>
          <p className="mt-1 max-w-md text-sm text-muted-foreground">
            Upload and process bank statements to save them here. Your data will
            persist across sessions.
          </p>
          <Link href="/upload">
            <Button className="mt-5 gap-2">
              <Upload className="h-4 w-4" />
              Upload Statements
            </Button>
          </Link>
        </motion.div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
          {/* Statement list */}
          <div className="space-y-2 rounded-2xl border border-border bg-card p-3">
            <p className="px-2 py-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              {statements.length} statement{statements.length !== 1 ? "s" : ""}
            </p>
            <div className="max-h-[calc(100vh-220px)] space-y-2 overflow-y-auto pr-1">
              {statements.map((item) => {
                const active = item.id === selectedId;
                const isDeleting = deletingId === item.id;
                return (
                  <div
                    key={item.id}
                    className={`flex items-start gap-1 rounded-xl border p-1 transition-all ${active
                      ? "border-primary/40 bg-primary/5 shadow-sm"
                      : "border-transparent bg-muted/30 hover:bg-muted/50"
                      }`}
                  >
                    <button
                      type="button"
                      onClick={() => setSelectedId(item.id)}
                      className="min-w-0 flex-1 rounded-lg p-2 text-left"
                    >
                      <div className="flex items-start gap-2">
                        <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10">
                          <FileText className="h-4 w-4 text-primary" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium text-foreground">
                            {item.fileName}
                          </p>
                          <p className="mt-0.5 text-xs text-muted-foreground">
                            {format(new Date(item.uploadedAt), "MMM d, yyyy")}
                          </p>
                          <div className="mt-2 flex flex-wrap gap-1">
                            <Badge variant="secondary" className="text-[10px]">
                              {item.transactionCount} txns
                            </Badge>
                            {item.bankName && (
                              <Badge variant="outline" className="text-[10px]">
                                {item.bankName}
                              </Badge>
                            )}
                          </div>
                        </div>
                      </div>
                    </button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="mt-1 h-8 w-8 shrink-0 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                      disabled={isDeleting}
                      aria-label={`Delete ${item.fileName}`}
                      onClick={() => handleDelete(item.id, item.fileName)}
                    >
                      {isDeleting ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Trash2 className="h-4 w-4" />
                      )}
                    </Button>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Detail panel */}
          <div className="min-w-0 space-y-4">
            {selectedMeta && (
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-border bg-card px-4 py-3">
                <div>
                  <h3 className="font-semibold text-foreground">
                    {selectedMeta.fileName}
                  </h3>
                  <p className="text-xs text-muted-foreground">
                    Uploaded {format(new Date(selectedMeta.uploadedAt), "PPp")}
                    {selectedMeta.bankName ? ` · ${selectedMeta.bankName}` : ""}
                  </p>
                </div>
                <div className="flex gap-2">
                  {selectedMeta.fileUrl && (
                    <Button variant="outline" size="sm" className="gap-2" asChild>
                      <a
                        href={selectedMeta.fileUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        <ExternalLink className="h-4 w-4" />
                        View PDF
                      </a>
                    </Button>
                  )}
                  <Button
                    variant="outline"
                    size="sm"
                    className="gap-2 text-destructive hover:bg-destructive/10 hover:text-destructive"
                    disabled={deletingId === selectedMeta.id}
                    onClick={() =>
                      handleDelete(selectedMeta.id, selectedMeta.fileName)
                    }
                  >
                    {deletingId === selectedMeta.id ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Trash2 className="h-4 w-4" />
                    )}
                    Delete
                  </Button>
                </div>
              </div>
            )}

            {isLoadingDetail ? (
              <div className="space-y-4">
                <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                  {Array.from({ length: 4 }).map((_, i) => (
                    <Skeleton key={i} className="h-24 rounded-2xl" />
                  ))}
                </div>
                <Skeleton className="h-64 rounded-2xl" />
              </div>
            ) : selectedDoc ? (
              <StatementDetailView
                document={selectedDoc}
                subtitle={
                  selectedMeta?.accountNumber
                    ? `Account ${selectedMeta.accountNumber}`
                    : undefined
                }
              />
            ) : (
              <p className="text-sm text-muted-foreground">
                Select a statement to view transactions.
              </p>
            )}

            {selectedMeta && !isLoadingDetail && (
              <p className="text-xs text-muted-foreground">
                Credits {formatUSD(selectedMeta.totalCredits)} · Debits{" "}
                {formatUSD(selectedMeta.totalDebits)}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
