/* Centralized API client for all frontend calls */

const BASE = process.env.NEXT_PUBLIC_API_URL || "";

// Types 

export interface User {
  id: string;
  email: string;
  name: string | null;
}

export type ColumnVisibility = {
  debit?: boolean;
  credit?: boolean;
};

export interface TransactionRecord {
  date: string | null;
  description: string;
  debit: number | null;
  credit: number | null;
  balance: number | null;
}

export interface DocumentResult {
  id?: string;
  filename: string;
  raw_text: string;
  fileUrl?: string;
  transactions: TransactionRecord[];
  bank_name?: string | null;
  account_number?: string | null;
  customer_name?: string | null;
  current_balance?: number | null;
  total_debits?: number;
  total_credits?: number;
  confidence?: number | null;
  pdf_type?: string | null;
}

export interface StatementListItem {
  id: string;
  fileName: string;
  uploadedAt: string;
  processedAt: string | null;
  status: string;
  bankName: string | null;
  accountNumber: string | null;
  customerNumber: string | null;
  currentBalance: number | null;
  transactionCount: number;
  totalCredits: number;
  totalDebits: number;
  fileUrl: string;
}

export interface ProcessResponse {
  status: string;
  documents: DocumentResult[];
  warnings?: string[];
  skippedDuplicates?: string[];
}

//Helpers

class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(
  url: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    credentials: "include",
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new ApiError(
      (data as Record<string, string>).error || `Request failed (${res.status})`,
      res.status
    );
  }
  return data as T;
}

//Auth

export async function apiLogin(email: string, password: string) {
  return request<{ user: User }>("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
}

export async function apiRegister(
  email: string,
  password: string,
  name?: string
) {
  return request<{ user: User }>("/api/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, name }),
  });
}

export async function apiLogout() {
  return request<{ success: boolean }>("/api/auth/logout", {
    method: "POST",
  });
}

export async function apiGetMe() {
  return request<{ user: User | null }>("/api/auth/me");
}

// OCR Processing (authenticated — saves to database)

export async function apiUploadStatements(
  files: File[],
  onProgress?: (pct: number) => void,
  bankHint?: string,
): Promise<ProcessResponse> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const formData = new FormData();
    files.forEach((f) => formData.append("files", f));

    // Append bank hint for manual bank selection (skip template auto-detect)
    if (bankHint && bankHint !== "all") {
      formData.append("bank_hint", bankHint);
    }

    xhr.upload.addEventListener("progress", (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    });

    xhr.addEventListener("load", () => {
      try {
        const data = JSON.parse(xhr.responseText);
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(data as ProcessResponse);
        } else {
          const detail =
            typeof data.detail === "string"
              ? data.detail
              : data.error || "Upload failed";
          reject(new ApiError(detail, xhr.status));
        }
      } catch {
        reject(new ApiError("Invalid server response", xhr.status));
      }
    });

    xhr.addEventListener("error", () =>
      reject(new ApiError("Network error", 0))
    );

    xhr.withCredentials = true;
    xhr.open("POST", `${BASE}/api/ocr/process`);
    xhr.send(formData);
  });
}

export async function apiFetchSavedStatements(): Promise<ProcessResponse> {
  return request<ProcessResponse>("/api/statements");
}

export async function apiFetchStatementList(): Promise<{
  statements: StatementListItem[];
}> {
  return request<{ statements: StatementListItem[] }>(
    "/api/statements?view=list"
  );
}

export async function apiFetchStatement(id: string): Promise<{
  document: DocumentResult;
}> {
  return request<{ document: DocumentResult }>(`/api/statements/${id}`);
}

export async function apiDeleteStatement(id: string): Promise<{ success: boolean }> {
  return request<{ success: boolean }>(`/api/statements/${id}`, {
    method: "DELETE",
  });
}
