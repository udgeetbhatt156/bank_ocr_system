/* ─────────────────────────────────────────────
   Centralized API client for all frontend calls
   ───────────────────────────────────────────── */

const BASE = process.env.NEXT_PUBLIC_API_URL || "";

// ── Types ──

export interface User {
  id: string;
  email: string;
  name: string | null;
}

export interface TransactionRecord {
  date: string | null;
  description: string;
  debit: number | null;
  credit: number | null;
  balance: number | null;
  reference: string | null;
  source_line: string;
}

export interface DocumentResult {
  filename: string;
  raw_text: string;
  transactions: TransactionRecord[];
}

export interface ProcessResponse {
  status: string;
  documents: DocumentResult[];
}

// ── Helpers ──

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

// ── Auth ──

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

//OCR Processing 

const PYTHON_OCR_URL = process.env.NEXT_PUBLIC_PYTHON_OCR_URL || "http://localhost:8000";

export async function apiUploadStatements(
  files: File[],
  onProgress?: (pct: number) => void
): Promise<ProcessResponse> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const formData = new FormData();
    files.forEach((f) => formData.append("files", f));

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
          reject(new ApiError(data.detail || data.error || "Upload failed", xhr.status));
        }
      } catch {
        reject(new ApiError("Invalid server response", xhr.status));
      }
    });

    xhr.addEventListener("error", () =>
      reject(new ApiError("Network error", 0))
    );

    // Call Python backend directly
    xhr.open("POST", `${PYTHON_OCR_URL}/api/ocr/process`);
    xhr.send(formData);
  });
}
