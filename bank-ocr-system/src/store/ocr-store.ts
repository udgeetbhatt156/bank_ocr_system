import { create } from "zustand";
import {
  apiUploadStatements,
  apiFetchSavedStatements,
  apiFetchStatementList,
  type DocumentResult,
  type ProcessResponse,
  type StatementListItem,
  type TransactionRecord,
} from "@/lib/api";
import { sumTransactionTotals } from "@/lib/transaction-totals";

export interface UploadFile {
  id: string;
  file: File;
  status: "pending" | "uploading" | "success" | "error" | "duplicate";
  error?: string;
}

interface OcrState {
  /* upload */
  files: UploadFile[];
  uploadProgress: number;
  isProcessing: boolean;
  processingStartedAt: number | null;
  elapsedSeconds: number;
  estimatedSeconds: number | null;
  processingMessage: string | null;

  /* results */
  documents: DocumentResult[];
  statementList: StatementListItem[];
  statementListLoaded: boolean;
  activeTab: string;
  isHydrated: boolean;
  isHydrating: boolean;
  isLoadingStatementList: boolean;

  /* actions */
  addFiles: (newFiles: File[]) => { added: string[]; duplicates: string[] };
  removeFile: (id: string) => void;
  clearFiles: () => void;
  processFiles: () => Promise<ProcessResponse>;
  clearResults: () => void;
  hydrateFromServer: (force?: boolean) => Promise<void>;
  loadStatementList: (force?: boolean) => Promise<StatementListItem[]>;
  setActiveTab: (tab: string) => void;

  /* computed-like helpers */
  allTransactions: () => (TransactionRecord & { _filename: string })[];
  summaryStats: () => {
    totalCredits: number;
    totalDebits: number;
    netFlow: number;
    totalTransactions: number;
    statementsProcessed: number;
  };
}

let fileCounter = 0;

export const useOcrStore = create<OcrState>((set, get) => ({
  files: [],
  uploadProgress: 0,
  isProcessing: false,
  processingStartedAt: null,
  elapsedSeconds: 0,
  estimatedSeconds: null,
  processingMessage: null,
  documents: [],
  statementList: [],
  statementListLoaded: false,
  activeTab: "overview",
  isHydrated: false,
  isHydrating: false,
  isLoadingStatementList: false,

  addFiles: (newFiles) => {
    const { files, documents } = get();

    const existingNames = new Set<string>([
      ...files.map((f) => f.file.name.toLowerCase()),
      ...documents.map((d) => d.filename.toLowerCase()),
    ]);

    const added: string[] = [];
    const duplicates: string[] = [];
    const entries: UploadFile[] = [];

    for (const file of newFiles) {
      const nameLower = file.name.toLowerCase();
      if (existingNames.has(nameLower)) {
        duplicates.push(file.name);
        // Still add to list but mark as duplicate so user can see it
        entries.push({
          id: `file-${++fileCounter}`,
          file,
          status: "duplicate" as const,
        });
      } else {
        added.push(file.name);
        existingNames.add(nameLower); // prevent duplicates within the same drop
        entries.push({
          id: `file-${++fileCounter}`,
          file,
          status: "pending" as const,
        });
      }
    }

    set((s) => ({ files: [...s.files, ...entries] }));
    return { added, duplicates };
  },

  removeFile: (id) => {
    set((s) => ({ files: s.files.filter((f) => f.id !== id) }));
  },

  clearFiles: () => set({ files: [], uploadProgress: 0 }),

  processFiles: async () => {
    const { files } = get();
    // Only process pending files — skip duplicates
    const pending = files.filter((f) => f.status === "pending");
    if (!pending.length) {
      return { status: "success", documents: get().documents };
    }

    const startedAt = Date.now();
    const estimatedSeconds = estimateProcessingSeconds(pending.map((f) => f.file));
    let timer: ReturnType<typeof setInterval> | null = null;

    set((s) => ({
      isProcessing: true,
      uploadProgress: 0,
      processingStartedAt: startedAt,
      elapsedSeconds: 0,
      estimatedSeconds,
      processingMessage: null,
      files: s.files.map((f) =>
        f.status === "pending" ? { ...f, status: "uploading" as const } : f
      ),
    }));

    try {
      timer = setInterval(() => {
        const elapsedSeconds = Math.floor((Date.now() - startedAt) / 1000);
        set({
          elapsedSeconds,
          processingMessage:
            elapsedSeconds >= 180
              ? `Extraction is taking longer than usual. Estimated total time is ${formatDuration(
                  estimatedSeconds
                )}; elapsed ${formatDuration(elapsedSeconds)}. Please wait.`
              : null,
        });
      }, 1000);

      const raw = pending.map((f) => f.file);
      const result = await apiUploadStatements(raw, (pct) =>
        set({ uploadProgress: pct })
      );

      set((s) => ({
        isProcessing: false,
        uploadProgress: 100,
        processingStartedAt: null,
        processingMessage: null,
        isHydrated: false,
        files: s.files.map((f) =>
          f.status === "uploading" ? { ...f, status: "success" as const } : f
        ),
      }));

      // Always reload from DB — single source of truth, prevents duplicate entries
      await get().hydrateFromServer(true);
      return result;
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Processing failed";
      set((s) => ({
        isProcessing: false,
        processingStartedAt: null,
        processingMessage: null,
        files: s.files.map((f) =>
          f.status === "uploading"
            ? { ...f, status: "error" as const, error: msg }
            : f
        ),
      }));
      throw err;
    } finally {
      if (timer) clearInterval(timer);
    }
  },

  clearResults: () =>
    set({
      documents: [],
      statementList: [],
      statementListLoaded: false,
      files: [],
      uploadProgress: 0,
      processingStartedAt: null,
      elapsedSeconds: 0,
      estimatedSeconds: null,
      processingMessage: null,
    }),

  loadStatementList: async (force = false) => {
    const { statementListLoaded, isLoadingStatementList } = get();
    if (!force && (statementListLoaded || isLoadingStatementList)) {
      return get().statementList;
    }

    set({ isLoadingStatementList: true });
    try {
      const { statements } = await apiFetchStatementList();
      set({
        statementList: statements,
        statementListLoaded: true,
        isLoadingStatementList: false,
      });
      return statements;
    } catch {
      set({ isLoadingStatementList: false });
      return get().statementList;
    }
  },

  hydrateFromServer: async (force = false) => {
    const { isHydrated, isHydrating } = get();
    if (!force && (isHydrated || isHydrating)) return;

    set({ isHydrating: true });
    try {
      const result = await apiFetchSavedStatements();
      set({
        documents: result.documents,
        isHydrated: true,
        isHydrating: false,
      });
      void get().loadStatementList(true);
    } catch {
      set({ isHydrated: true, isHydrating: false });
    }
  },

  setActiveTab: (tab) => set({ activeTab: tab }),

  allTransactions: () => {
    const { documents } = get();
    return documents.flatMap((doc) =>
      doc.transactions
        .filter((t) => Number(t.credit || 0) > 0 || Number(t.debit || 0) > 0)
        .map((t) => ({
          ...t,
          _filename: doc.filename,
        }))
    );
  },

  summaryStats: () => {
    const { documents } = get();
    const transactions = documents
      .flatMap((doc) => doc.transactions)
      .filter((t) => Number(t.credit || 0) > 0 || Number(t.debit || 0) > 0);
    const totals = sumTransactionTotals(transactions);
    let totalTransactions = 0;

    for (const doc of documents) {
      totalTransactions += doc.transactions.length;
    }

    return {
      totalCredits: totals.totalCredits,
      totalDebits: totals.totalDebits,
      netFlow: totals.netFlow,
      totalTransactions,
      statementsProcessed: documents.length,
    };
  },
}));

function estimateProcessingSeconds(files: File[]) {
  const totalMb = files.reduce((sum, file) => sum + file.size / (1024 * 1024), 0);
  const base = files.length * 30;
  const sizeCost = totalMb * 20;
  return Math.max(45, Math.ceil(base + sizeCost));
}

function formatDuration(totalSeconds: number) {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes <= 0) return `${seconds}s`;
  if (seconds === 0) return `${minutes}m`;
  return `${minutes}m ${seconds}s`;
}
