import fs from "fs";
import { promises as fsPromises } from "fs";
import path from "path";
import axios from "axios";
import FormData from "form-data";
import { NextResponse } from "next/server";

import { requireAuthUser } from "@/lib/auth-server";
import { persistOcrDocument, statementToDocumentResult } from "@/lib/statements";
import { prisma } from "@/lib/prisma";
import type { OcrDocumentPayload } from "@/lib/statements";

const TEMP_DIR = path.join(process.cwd(), "tmp");
const PYTHON_OCR_URL =
  process.env.PYTHON_OCR_URL?.replace(/\/$/, "") || "http://localhost:8000";

async function writeTempFile(name: string, buffer: Buffer) {
  await fsPromises.mkdir(TEMP_DIR, { recursive: true });
  const safeName = `${Date.now()}-${name.replace(/[^a-zA-Z0-9_.-]/g, "-")}`;
  const filePath = path.join(TEMP_DIR, safeName);
  await fsPromises.writeFile(filePath, buffer);
  return filePath;
}

function resolveFileBuffer(
  doc: OcrDocumentPayload,
  fileBuffers: { name: string; buffer: Buffer }[],
  index: number
): Buffer | undefined {
  const exact = fileBuffers.find((f) => f.name === doc.filename);
  if (exact) return exact.buffer;

  const normalized = doc.filename.toLowerCase();
  const caseInsensitive = fileBuffers.find(
    (f) => f.name.toLowerCase() === normalized
  );
  if (caseInsensitive) return caseInsensitive.buffer;

  return fileBuffers[index]?.buffer;
}

export async function POST(request: Request) {
  let user;
  try {
    user = await requireAuthUser();
  } catch {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const formData = await request.formData();
  const files = formData.getAll("files");
  const tempPaths: string[] = [];
  const fileBuffers: { name: string; buffer: Buffer }[] = [];

  if (!files.length) {
    return NextResponse.json({ error: "No files uploaded." }, { status: 400 });
  }

  const upstreamForm = new FormData();

  try {
    for (const file of files) {
      if (!(file instanceof File)) continue;
      const fileName = file.name || `document-${Date.now()}.bin`;
      const buffer = Buffer.from(await file.arrayBuffer());
      fileBuffers.push({ name: fileName, buffer });
      const filePath = await writeTempFile(fileName, buffer);
      tempPaths.push(filePath);
      upstreamForm.append("files", fs.createReadStream(filePath), fileName);
    }

    const response = await axios.post(
      `${PYTHON_OCR_URL}/api/ocr/process`,
      upstreamForm,
      {
        headers: upstreamForm.getHeaders(),
        timeout: 1200_000,
      }
    );

    const ocrData = response.data as {
      status: string;
      documents: OcrDocumentPayload[];
    };

    const savedDocuments = [];
    const persistErrors: string[] = [];
    const skippedDuplicates: string[] = [];
    const rejectedStatements: string[] = [];

    for (let i = 0; i < ocrData.documents.length; i++) {
      const doc = ocrData.documents[i];
      if (doc.rejected || doc.is_altered) {
        const reasons = doc.alteration_reasons?.length
          ? ` Reasons: ${doc.alteration_reasons.join("; ")}`
          : "";
        rejectedStatements.push(
          `${doc.filename}: ${doc.rejection_reason || "Statement rejected."}${reasons}`
        );
        continue;
      }

      const buffer = resolveFileBuffer(doc, fileBuffers, i);

      if (!buffer) {
        persistErrors.push(`${doc.filename}: original file buffer not found`);
        continue;
      }

      try {
        const { statementId, skippedDuplicate, duplicateOf } =
          await persistOcrDocument(user.id, doc, buffer);

        if (skippedDuplicate) {
          skippedDuplicates.push(
            `${doc.filename}: already saved as "${duplicateOf}"`
          );
        }

        const statement = await prisma.statement.findFirst({
          where: { id: statementId, account: { userId: user.id } },
          include: {
            transactions: { orderBy: { date: "asc" } },
            account: true,
          },
        });

        if (!statement) {
          throw new Error("Statement saved but could not be loaded");
        }

        if (!skippedDuplicate) {
          savedDocuments.push(
            statementToDocumentResult(statement, { includeRawText: true })
          );
        }
      } catch (persistErr) {
        const msg =
          persistErr instanceof Error ? persistErr.message : String(persistErr);
        console.error("[OCR Process] DB save failed for", doc.filename, persistErr);
        persistErrors.push(`${doc.filename}: ${msg}`);
      }
    }

    if (
      !savedDocuments.length &&
      (persistErrors.length || rejectedStatements.length) &&
      !skippedDuplicates.length
    ) {
      return NextResponse.json(
        {
          error: rejectedStatements.length
            ? "One or more statements were rejected"
            : "Failed to save statements to database",
          detail: [...rejectedStatements, ...persistErrors].join("; "),
        },
        { status: rejectedStatements.length ? 422 : 500 }
      );
    }

    const warnings = [
      ...rejectedStatements,
      ...persistErrors,
      ...skippedDuplicates,
    ].filter(Boolean);

    return NextResponse.json({
      status: "success",
      documents: savedDocuments,
      warnings: warnings.length ? warnings : undefined,
      skippedDuplicates: skippedDuplicates.length ? skippedDuplicates : undefined,
    });
  } catch (error) {
    console.error("[OCR Process] Error:", error);

    if (axios.isAxiosError(error)) {
      if (error.code === "ECONNREFUSED") {
        return NextResponse.json(
          {
            error: "Python OCR service is not running",
            detail: `Cannot connect to ${PYTHON_OCR_URL}. Start: cd backend-python && python -m uvicorn app.main:app --reload --port 8000`,
          },
          { status: 503 }
        );
      }
      return NextResponse.json(
        {
          error: "OCR service failed",
          detail: error.response?.data ?? error.message,
        },
        { status: 502 }
      );
    }

    return NextResponse.json(
      {
        error: "Failed to process statements",
        detail: error instanceof Error ? error.message : "unknown",
      },
      { status: 500 }
    );
  } finally {
    await Promise.all(
      tempPaths.map(async (filePath) => {
        try {
          await fsPromises.unlink(filePath);
        } catch {
          /* ignore */
        }
      })
    );
  }
}
