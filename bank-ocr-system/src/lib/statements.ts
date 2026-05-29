import path from "path";
import { promises as fs } from "fs";

import { prisma } from "@/lib/prisma";
import type { DocumentResult, TransactionRecord } from "@/lib/api";

export const UPLOADS_ROOT = path.join(process.cwd(), "uploads");

export type OcrDocumentPayload = {
  filename: string;
  transactions: TransactionRecord[];
  confidence?: number;
  pdf_type?: string;
  warnings?: string[];
  raw_text?: string | null;
  bank_name?: string | null;
  account_number?: string | null;
  customer_number?: string | null;
  current_balance?: number | null;
  raw_credits?: number;
  adjusted_revenue?: number;
  revenue_deductions?: number;
  total_debits?: number;
  // Duplicate detection fields
  file_hash?: string | null;
  content_hash?: string | null;
  fingerprint?: string | null;
  is_duplicate?: boolean;
  duplicate_type?: string | null;
  duplicate_of?: string | null;
  duplicate_confidence?: number | null;
  duplicate_message?: string | null;
};

/** OCR metadata stored in Statement.rawData (works even if Prisma client is stale) */
type StoredStatementMeta = {
  raw_text: string;
  warnings: string[];
  confidence?: number | null;
  pdf_type?: string | null;
  bank_name?: string | null;
  account_number?: string | null;
  customer_number?: string | null;
  current_balance?: number | null;
  raw_credits?: number | null;
  adjusted_revenue?: number | null;
  revenue_deductions?: number | null;
  total_debits?: number | null;
};

type StatementWithRelations = {
  id: string;
  fileName: string;
  filePath: string;
  uploadedAt: Date;
  processedAt: Date | null;
  status: string;
  rawData: unknown;
  account: {
    bankName: string;
    accountNumber: string;
    customerNumber?: string | null;
  };
  transactions: Array<{
    date: Date;
    description: string;
    debit: unknown;
    credit: unknown;
    balance: unknown;
    reference: string | null;
    sourceLine?: string | null;
  }>;
};

function safeFileName(name: string) {
  return name.replace(/[^a-zA-Z0-9_.-]/g, "-");
}

function buildRawData(doc: OcrDocumentPayload): StoredStatementMeta {
  return {
    raw_text: doc.raw_text ?? "",
    warnings: doc.warnings ?? [],
    confidence: doc.confidence ?? null,
    pdf_type: doc.pdf_type ?? null,
    bank_name: doc.bank_name ?? null,
    account_number: doc.account_number ?? null,
    customer_number: doc.customer_number ?? null,
    current_balance: doc.current_balance ?? null,
    raw_credits: doc.raw_credits ?? null,
    adjusted_revenue: doc.adjusted_revenue ?? null,
    revenue_deductions: doc.revenue_deductions ?? null,
    total_debits: doc.total_debits ?? null,
  };
}

function parseStoredMeta(
  rawData: unknown,
  account?: { bankName: string; accountNumber: string; customerNumber?: string | null }
) {
  const meta =
    rawData && typeof rawData === "object"
      ? (rawData as Partial<StoredStatementMeta>)
      : {};

  return {
    raw_text: meta.raw_text ?? "",
    bank_name: meta.bank_name ?? account?.bankName ?? null,
    account_number: meta.account_number ?? account?.accountNumber ?? null,
    customer_number: meta.customer_number ?? account?.customerNumber ?? null,
    current_balance:
      meta.current_balance != null ? Number(meta.current_balance) : null,
    confidence: meta.confidence ?? null,
    pdf_type: meta.pdf_type ?? null,
    raw_credits: meta.raw_credits != null ? Number(meta.raw_credits) : null,
    adjusted_revenue:
      meta.adjusted_revenue != null ? Number(meta.adjusted_revenue) : null,
    revenue_deductions:
      meta.revenue_deductions != null ? Number(meta.revenue_deductions) : null,
    total_debits: meta.total_debits != null ? Number(meta.total_debits) : null,
  };
}

export function parseOcrDate(value: string | null | undefined): Date {
  if (!value) return new Date();

  const iso = new Date(value);
  if (!isNaN(iso.getTime())) return iso;

  const slash = value.match(/^(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{2,4})$/);
  if (slash) {
    const year =
      slash[3].length === 2
        ? 2000 + parseInt(slash[3], 10)
        : parseInt(slash[3], 10);
    return new Date(year, parseInt(slash[1], 10) - 1, parseInt(slash[2], 10));
  }

  const monthDay = value.match(/^([A-Za-z]{3})\s+(\d{1,2})(?:,?\s*(\d{4}))?$/);
  if (monthDay) {
    const parsed = new Date(
      `${monthDay[1]} ${monthDay[2]}, ${monthDay[3] || new Date().getFullYear()}`
    );
    if (!isNaN(parsed.getTime())) return parsed;
  }

  return new Date();
}

function formatDateForClient(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${m}/${d}/${y}`;
}

function decimalOrNull(value: number | string | null | undefined) {
  if (value === null || value === undefined || value === "") return null;
  const num =
    typeof value === "number"
      ? value
      : Number(String(value).replace(/,/g, ""));
  if (Number.isNaN(num)) return null;
  return num;
}

export async function saveUploadedFile(
  userId: string,
  statementId: string,
  fileName: string,
  buffer: Buffer
) {
  const dir = path.join(UPLOADS_ROOT, userId, statementId);
  await fs.mkdir(dir, { recursive: true });
  const filePath = path.join(dir, safeFileName(fileName));
  await fs.writeFile(filePath, buffer);
  return filePath;
}

export async function persistOcrDocument(
  userId: string,
  doc: OcrDocumentPayload,
  fileBuffer: Buffer
) {
  const accountNumber =
    doc.account_number?.trim() || `account-${userId.slice(0, 8)}`;
  const bankName = doc.bank_name?.trim() || "Unknown Bank";

  const existingAccount = await prisma.bankAccount.findFirst({
    where: { userId, accountNumber },
  });

  const account = existingAccount
    ? await prisma.bankAccount.update({
        where: { id: existingAccount.id },
        data: { bankName },
      })
    : await prisma.bankAccount.create({
        data: {
          userId,
          accountNumber,
          bankName,
        },
      });

  // Check for duplicate by file hash (if provided by OCR service)
  if ((doc as any).file_hash) {
    const duplicateByFileHash = await prisma.statement.findFirst({
      where: {
        fileHash: (doc as any).file_hash,
        accountId: account.id,
      },
      select: { id: true, fileName: true },
    });

    if (duplicateByFileHash) {
      throw new Error(
        `Duplicate file detected: This exact file was already uploaded as "${duplicateByFileHash.fileName}"`
      );
    }
  }

  // Check for duplicate by content hash (if provided by OCR service)
  if ((doc as any).content_hash) {
    const duplicateByContentHash = await prisma.statement.findFirst({
      where: {
        contentHash: (doc as any).content_hash,
        accountId: account.id,
      },
      select: { id: true, fileName: true },
    });

    if (duplicateByContentHash) {
      throw new Error(
        `Duplicate content detected: This statement content was already processed in "${duplicateByContentHash.fileName}"`
      );
    }
  }

  // Check for duplicate by filename (legacy check)
  const existing = await prisma.statement.findFirst({
    where: {
      fileName: doc.filename,
      account: { userId },
    },
    select: { id: true, filePath: true },
  });

  const statementFields = {
    fileName: doc.filename,
    fileHash: (doc as any).file_hash || null,
    contentHash: (doc as any).content_hash || null,
    processedAt: new Date(),
    status: doc.transactions.length > 0 ? "processed" : "failed",
    rawData: buildRawData(doc),
    accountId: account.id,
  };

  const statement = existing
    ? await prisma.statement.update({
        where: { id: existing.id },
        data: statementFields,
      })
    : await prisma.statement.create({
        data: {
          ...statementFields,
          filePath: "",
        },
      });

  const filePath = await saveUploadedFile(
    userId,
    statement.id,
    doc.filename,
    fileBuffer
  );

  if (existing?.filePath && existing.filePath !== filePath) {
    try {
      await fs.unlink(existing.filePath);
    } catch {
      /* ignore missing file */
    }
  }

  await prisma.statement.update({
    where: { id: statement.id },
    data: { filePath },
  });

  await prisma.transaction.deleteMany({
    where: { statementId: statement.id },
  });

  if (doc.transactions.length > 0) {
    await prisma.transaction.createMany({
      data: doc.transactions.map((t) => ({
        statementId: statement.id,
        accountId: account.id,
        date: parseOcrDate(t.date),
        description: t.description || "—",
        debit: decimalOrNull(t.debit),
        credit: decimalOrNull(t.credit),
        balance: decimalOrNull(t.balance),
        reference: t.reference || t.source_line || null,
      })),
    });
  }

  return statement.id;
}

export function statementToDocumentResult(
  statement: StatementWithRelations
): DocumentResult {
  const meta = parseStoredMeta(statement.rawData, statement.account);

  return {
    id: statement.id,
    filename: statement.fileName,
    fileUrl: `/api/statements/${statement.id}/file`,
    raw_text: meta.raw_text,
    bank_name: meta.bank_name,
    account_number: meta.account_number,
    customer_number: meta.customer_number,
    current_balance: meta.current_balance,
    raw_credits: meta.raw_credits ?? undefined,
    adjusted_revenue: meta.adjusted_revenue ?? undefined,
    revenue_deductions: meta.revenue_deductions ?? undefined,
    total_debits: meta.total_debits ?? undefined,
    transactions: statement.transactions.map((t) => ({
      date: formatDateForClient(t.date),
      description: t.description,
      debit: t.debit != null ? Number(t.debit) : null,
      credit: t.credit != null ? Number(t.credit) : null,
      balance: t.balance != null ? Number(t.balance) : null,
      reference: t.reference,
      source_line: t.sourceLine ?? t.reference ?? "",
    })),
  };
}

  // const statements = await prisma.statement.findMany({
  //   where: { account: { userId } },
  //   include: {
  //     transactions: { orderBy: { date: "asc" } },
  //     account: true,
  //   },
  //   orderBy: { uploadedAt: "desc" },
  // });
  export async function fetchUserDocuments(
  userId: string
): Promise<DocumentResult[]> {
  const statements = await prisma.statement.findMany({
    where: { account: { userId } },
    select: {
      id: true,
      fileName: true,
      uploadedAt: true,
      processedAt: true,
      status: true,
      rawData: true,
      account: {
        select: {
          bankName: true,
          accountNumber: true,
          customerNumber: true,
        },
      },
      _count: {
        select: {
          transactions: true,
        },
      },
    },
    orderBy: { uploadedAt: "desc" },
  });

  return statements.map((s) => statementToDocumentResult(s));
}

export async function getStatementForUser(statementId: string, userId: string) {
  return prisma.statement.findFirst({
    where: { id: statementId, account: { userId } },
    include: {
      transactions: { orderBy: { date: "asc" } },
      account: true,
    },
  });
}

export async function deleteStatementForUser(
  statementId: string,
  userId: string
): Promise<boolean> {
  const statement = await getStatementForUser(statementId, userId);
  if (!statement) return false;

  await prisma.statement.delete({ where: { id: statement.id } });

  try {
    await fs.unlink(statement.filePath);
  } catch {
    /* file may already be missing */
  }

  try {
    const uploadDir = path.dirname(statement.filePath);
    await fs.rm(uploadDir, { recursive: true, force: true });
  } catch {
    /* ignore directory cleanup errors */
  }

  return true;
}

export type StatementListItem = {
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
};

export async function fetchUserStatementList(
  userId: string
): Promise<StatementListItem[]> {
  const statements = await prisma.statement.findMany({
    where: { account: { userId } },
    include: {
      transactions: true,
      account: true,
    },
    orderBy: { uploadedAt: "desc" },
  });

  return statements.map((s: StatementWithRelations) => {
    const meta = parseStoredMeta(s.rawData, s.account);
    let totalCredits = 0;
    let totalDebits = 0;
    for (const t of s.transactions) {
      totalCredits += Number(t.credit || 0);
      totalDebits += Number(t.debit || 0);
    }

    return {
      id: s.id,
      fileName: s.fileName,
      uploadedAt: s.uploadedAt.toISOString(),
      processedAt: s.processedAt?.toISOString() ?? null,
      status: s.status,
      bankName: meta.bank_name,
      accountNumber: meta.account_number,
      customerNumber: meta.customer_number,
      currentBalance: meta.current_balance,
      transactionCount: s.transactions.length,
      totalCredits,
      totalDebits,
      fileUrl: `/api/statements/${s.id}/file`,
    };
  });
}
