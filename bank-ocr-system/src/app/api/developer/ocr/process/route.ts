import axios from "axios";
import FormData from "form-data";
import { NextResponse } from "next/server";

import { signToken } from "@/lib/jwt";
import type { OcrDocumentPayload } from "@/lib/statements";

//Config
const PYTHON_OCR_URL =
  process.env.PYTHON_OCR_URL?.replace(/\/$/, "") || "http://localhost:8000";

const ALLOWED_DEVELOPER_EMAIL = process.env.PW_USER_EMAIL?.trim() || "developer@example.com";
const ALLOWED_DEVELOPER_APP = process.env.PW_APPLICATION?.trim() || "ocr_process_api";
const ALLOWED_PASSKEY = process.env.PW_PASSKEY?.trim();

// Helpers

/** Validates required headers. Returns an error string or null if all good. */
function validateHeaders(
  appName: string | null,
  email: string | null,
  passKey: string | null
): string | null {
  if (!appName || !email) {
    return "Missing required headers: X-PW-Application, X-PW-UserEmail";
  }

  if (email.toLowerCase() !== ALLOWED_DEVELOPER_EMAIL.toLowerCase()) {
    return "This endpoint is restricted to a specific developer email.";
  }

  if (appName !== ALLOWED_DEVELOPER_APP) {
    return "Invalid Application Name provided.";
  }

  if (ALLOWED_PASSKEY && passKey !== ALLOWED_PASSKEY) {
    return "Invalid PassKey provided.";
  }

  return null;
}

/** Reads files from a FormData object and builds the upstream form without disk I/O. */
async function buildUpstreamForm(
  formData: FormData
): Promise<FormData> {
  const files = formData.getAll("files");
  const upstreamForm = new FormData();

  for (const file of files) {
    if (!(file instanceof File)) continue;

    const fileName = file.name || `document-${Date.now()}.bin`;
    const buffer = Buffer.from(await file.arrayBuffer());

    // Pass buffer directly — no need for disk I/O
    upstreamForm.append("files", buffer, { filename: fileName });
  }

  const bankHint = formData.get("bank_hint") as string | null;
  if (bankHint) {
    upstreamForm.append("bank_hint", bankHint);
  }

  return upstreamForm;
}

// Route handler 

export async function POST(request: Request) {
  const appName = request.headers.get("X-PW-Application");
  const email = request.headers.get("X-PW-UserEmail");
  const passkey = request.headers.get("X-PW-PassKey")
  const headerError = validateHeaders(appName, email, passkey);
  if (headerError) {
    return NextResponse.json({ error: `Unauthorized. ${headerError}` }, { status: 401 });
  }

  const formData = await request.formData();
  if (!formData.getAll("files").length) {
    return NextResponse.json({ error: "No files uploaded." }, { status: 400 });
  }

  try {
    const upstreamForm = await buildUpstreamForm(formData);

    const token = await signToken({
      sub: "developer_api_user_ocr",
      email: email!,
      name: appName!,
      passKey: passkey!,
    });

    const response = await axios.post(
      `${PYTHON_OCR_URL}/api/ocr/process-with-duplicate-check`,
      upstreamForm,
      {
        headers: {
          ...upstreamForm.getHeaders(),
          "X-PW-AccessToken": token,
          "X-PW-Application": appName!,
          "X-PW-UserEmail": email!,
          "X-PW-PassKey": passkey!,
        },
      }
    );

    const ocrData = response.data as {
      status: string;
      documents: OcrDocumentPayload[];
    };

    return NextResponse.json({
      status: "success",
      documents: ocrData.documents,
    });
  } catch (error) {
    console.error("[Developer OCR] Error:", error);

    if (axios.isAxiosError(error)) {
      if (error.code === "ECONNREFUSED") {
        return NextResponse.json(
          {
            error: "OCR service unavailable",
            detail: `Cannot connect to ${PYTHON_OCR_URL}`,
          },
          { status: 503 }
        );
      }
      return NextResponse.json(
        {
          error: "OCR service error",
          detail: error.response?.data ?? error.message,
        },
        { status: 502 }
      );
    }

    return NextResponse.json(
      {
        error: "Failed to process statements",
        detail: error instanceof Error ? error.message : "Unknown error",
      },
      { status: 500 }
    );
  }
}
