import { Prisma } from "@prisma/client";
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
};

function safeFileName(name: string) {
  return name.replace(/[^a-zA-Z0-9_.-]/g, "-");
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
    const parsed = new Date(`${monthDay[1]} ${monthDay[2]}, ${monthDay[3] || new Date().getFullYear()}`);
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
  const num = typeof value === "number" ? value : Number(String(value).replace(/,/g, ""));
  if (Number.isNaN(num)) return null;
  return new Prisma.Decimal(num);
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
  const accountNumber = doc.account_number?.trim() || `account-${userId.slice(0, 8)}`;
  const bankName = doc.bank_name?.trim() || "Unknown Bank";

  const existingAccount = await prisma.bankAccount.findFirst({
    where: { userId, accountNumber },
  });

  const account = existingAccount
    ? await prisma.bankAccount.update({
        where: { id: existingAccount.id },
        data: {
          bankName,
          ...(doc.customer_number != null
            ? { customerNumber: doc.customer_number }
            : {}),
        },
      })
    : await prisma.bankAccount.create({
        data: {
          userId,
          accountNumber,
          bankName,
          customerNumber: doc.customer_number ?? null,
        },
      });

  const existing = await prisma.statement.findFirst({
    where: {
      fileName: doc.filename,
      account: { userId },
    },
    select: { id: true, filePath: true },
  });

  const statementFields = {
    fileName: doc.filename,
    processedAt: new Date(),
    status: doc.transactions.length > 0 ? "processed" : "failed",
    confidence: doc.confidence ?? null,
    pdfType: doc.pdf_type ?? null,
    bankName: doc.bank_name ?? null,
    accountNumber: doc.account_number ?? null,
    customerNumber: doc.customer_number ?? null,
    currentBalance: decimalOrNull(doc.current_balance),
    rawData: {
      raw_text: doc.raw_text ?? "",
      warnings: doc.warnings ?? [],
    },
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

  await prisma.transaction.deleteMany({ where: { statementId: statement.id } });

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
        reference: t.reference,
        sourceLine: t.source_line ?? "",
      })),
    });
  }

  return statement.id;
}

type StatementWithRelations = Prisma.StatementGetPayload<{
  include: {
    transactions: { orderBy: { date: "asc" } };
    account: true;
  };
}>;

export function statementToDocumentResult(
  statement: StatementWithRelations
): DocumentResult {
  return {
    id: statement.id,
    filename: statement.fileName,
    fileUrl: `/api/statements/${statement.id}/file`,
    raw_text:
      typeof statement.rawData === "object" &&
      statement.rawData !== null &&
      "raw_text" in statement.rawData
        ? String((statement.rawData as { raw_text?: string }).raw_text ?? "")
        : "",
    bank_name: statement.bankName,
    account_number: statement.accountNumber ?? statement.account.accountNumber,
    customer_number:
      statement.customerNumber ?? statement.account.customerNumber,
    current_balance: statement.currentBalance
      ? Number(statement.currentBalance)
      : null,
    transactions: statement.transactions.map((t) => ({
      date: formatDateForClient(t.date),
      description: t.description,
      debit: t.debit ? Number(t.debit) : null,
      credit: t.credit ? Number(t.credit) : null,
      balance: t.balance ? Number(t.balance) : null,
      reference: t.reference,
      source_line: t.sourceLine ?? "",
    })),
  };
}

export async function fetchUserDocuments(userId: string): Promise<DocumentResult[]> {
  const statements = await prisma.statement.findMany({
    where: { account: { userId } },
    include: {
      transactions: { orderBy: { date: "asc" } },
      account: true,
    },
    orderBy: { uploadedAt: "desc" },
  });

  return statements.map(statementToDocumentResult);
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

  return statements.map((s) => {
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
      bankName: s.bankName ?? s.account.bankName,
      accountNumber: s.accountNumber ?? s.account.accountNumber,
      customerNumber: s.customerNumber ?? s.account.customerNumber,
      currentBalance: s.currentBalance ? Number(s.currentBalance) : null,
      transactionCount: s.transactions.length,
      totalCredits,
      totalDebits,
      fileUrl: `/api/statements/${s.id}/file`,
    };
  });
}
