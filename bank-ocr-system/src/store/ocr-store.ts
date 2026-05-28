import { create } from "zustand";
import {
  apiUploadStatements,
  apiFetchSavedStatements,
  type DocumentResult,
  type ProcessResponse,
  type TransactionRecord,
} from "@/lib/api";
import {
  classifyTransactionRevenue,
  getRevenueSnapshot,
} from "@/lib/revenue-filter";

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
  activeTab: string;
  isHydrated: boolean;
  isHydrating: boolean;

  /* actions */
  addFiles: (newFiles: File[]) => { added: string[]; duplicates: string[] };
  removeFile: (id: string) => void;
  clearFiles: () => void;
  processFiles: () => Promise<ProcessResponse>;
  clearResults: () => void;
  hydrateFromServer: (force?: boolean) => Promise<void>;
  setActiveTab: (tab: string) => void;

  /* computed-like helpers */
  allTransactions: () => (TransactionRecord & { _filename: string })[];
  summaryStats: () => {
    totalCredits: number;
    adjustedRevenue: number;
    revenueDeductions: number;
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
  activeTab: "overview",
  isHydrated: false,
  isHydrating: false,

  addFiles: (newFiles) => {
    const { files, documents } = get();

    // Build a set of names already in the queue OR already processed
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

      const notPersisted = result.documents.filter((d) => !d.id);
      set((s) => ({
        isProcessing: false,
        uploadProgress: 100,
        processingStartedAt: null,
        processingMessage: null,
        documents: mergeDocuments(s.documents, result.documents),
        isHydrated: true,
        files: s.files.map((f) =>
          f.status === "uploading" ? { ...f, status: "success" as const } : f
        ),
      }));

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
      files: [],
      uploadProgress: 0,
      processingStartedAt: null,
      elapsedSeconds: 0,
      estimatedSeconds: null,
      processingMessage: null,
    }),

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
    } catch {
      set({ isHydrated: true, isHydrating: false });
    }
  },

  setActiveTab: (tab) => set({ activeTab: tab }),

  allTransactions: () => {
    const { documents } = get();
    return documents.flatMap((doc) =>
      doc.transactions.map((t) => ({
        ...t,
        ...classifyTransactionRevenue(t),
        _filename: doc.filename,
      }))
    );
  },

  summaryStats: () => {
    const { documents } = get();
    const transactions = documents.flatMap((doc) => doc.transactions);
    const snapshot = getRevenueSnapshot(transactions);
    let totalTransactions = 0;

    for (const doc of documents) {
      totalTransactions += doc.transactions.length;
    }

    return {
      totalCredits: snapshot.rawCredits,
      adjustedRevenue: snapshot.adjustedRevenue,
      revenueDeductions: snapshot.revenueDeductions,
      totalDebits: snapshot.totalDebits,
      netFlow: snapshot.netFlow,
      totalTransactions,
      statementsProcessed: documents.length,
    };
  },
}));

function mergeDocuments(
  current: DocumentResult[],
  incoming: DocumentResult[]
): DocumentResult[] {
  const existing = [...current];
  for (const doc of incoming) {
    const idx = existing.findIndex(
      (d) =>
        (doc.id && d.id === doc.id) ||
        (!doc.id && d.filename === doc.filename)
    );
    if (idx !== -1) {
      existing[idx] = doc;
    } else {
      existing.push(doc);
    }
  }
  return existing;
}

function estimateProcessingSeconds(files: File[]) {
  const totalMb = files.reduce((sum, file) => sum + file.size / (1024 * 1024), 0);
  const base = files.length * 45;
  const sizeCost = totalMb * 35;
  return Math.max(60, Math.ceil(base + sizeCost));
}

function formatDuration(totalSeconds: number) {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes <= 0) return `${seconds}s`;
  if (seconds === 0) return `${minutes}m`;
  return `${minutes}m ${seconds}s`;
}
