import { create } from "zustand";
import {
  apiUploadStatements,
  type DocumentResult,
  type TransactionRecord,
} from "@/lib/api";

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

  /* results */
  documents: DocumentResult[];
  activeTab: string;

  /* actions */
  addFiles: (newFiles: File[]) => { added: string[]; duplicates: string[] };
  removeFile: (id: string) => void;
  clearFiles: () => void;
  processFiles: () => Promise<void>;
  clearResults: () => void;
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
  documents: [],
  activeTab: "overview",

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
    if (!pending.length) return;

    set((s) => ({
      isProcessing: true,
      uploadProgress: 0,
      files: s.files.map((f) =>
        f.status === "pending" ? { ...f, status: "uploading" as const } : f
      ),
    }));

    try {
      const raw = pending.map((f) => f.file);
      const result = await apiUploadStatements(raw, (pct) =>
        set({ uploadProgress: pct })
      );

      set((s) => ({
        isProcessing: false,
        uploadProgress: 100,
        // Deduplicate: replace existing doc with same filename, append new ones
        documents: (() => {
          const existing = [...s.documents];
          for (const incoming of result.documents) {
            const idx = existing.findIndex((d) => d.filename === incoming.filename);
            if (idx !== -1) {
              existing[idx] = incoming;
            } else {
              existing.push(incoming);
            }
          }
          return existing;
        })(),
        files: s.files.map((f) =>
          f.status === "uploading" ? { ...f, status: "success" as const } : f
        ),
      }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Processing failed";
      set((s) => ({
        isProcessing: false,
        files: s.files.map((f) =>
          f.status === "uploading"
            ? { ...f, status: "error" as const, error: msg }
            : f
        ),
      }));
      throw err;
    }
  },

  clearResults: () => set({ documents: [], files: [], uploadProgress: 0 }),

  setActiveTab: (tab) => set({ activeTab: tab }),

  allTransactions: () => {
    const { documents } = get();
    return documents.flatMap((doc) =>
      doc.transactions.map((t) => ({ ...t, _filename: doc.filename }))
    );
  },

  summaryStats: () => {
    const { documents } = get();
    let totalCredits = 0;
    let totalDebits = 0;
    let totalTransactions = 0;

    for (const doc of documents) {
      for (const t of doc.transactions) {
        totalTransactions++;
        if (t.credit) totalCredits += Number(t.credit);
        if (t.debit) totalDebits += Number(t.debit);
      }
    }

    return {
      totalCredits,
      totalDebits,
      netFlow: totalCredits - totalDebits,
      totalTransactions,
      statementsProcessed: documents.length,
    };
  },
}));
