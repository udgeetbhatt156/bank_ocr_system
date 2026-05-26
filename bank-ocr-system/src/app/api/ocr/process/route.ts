import fs from "fs";
import { promises as fsPromises } from "fs";
import path from "path";
import axios from "axios";
import FormData from "form-data";
import { NextResponse } from "next/server";

const TEMP_DIR = path.join(process.cwd(), "tmp");
const PYTHON_OCR_URL = process.env.PYTHON_OCR_URL?.replace(/\/$/, "") || "http://localhost:8000";

async function writeTempFile(name: string, buffer: Buffer) {
  await fsPromises.mkdir(TEMP_DIR, { recursive: true });
  const safeName = `${Date.now()}-${name.replace(/[^a-zA-Z0-9_.-]/g, "-")}`;
  const filePath = path.join(TEMP_DIR, safeName);
  await fsPromises.writeFile(filePath, buffer);
  return filePath;
}

export async function POST(request: Request) {
  console.log("[OCR Proxy] Received request");
  console.log("[OCR Proxy] Python OCR URL:", PYTHON_OCR_URL);
  
  const formData = await request.formData();
  const files = formData.getAll("files");
  const tempPaths: string[] = [];

  if (!files.length) {
    console.log("[OCR Proxy] No files in request");
    return NextResponse.json({ error: "No files uploaded." }, { status: 400 });
  }

  console.log(`[OCR Proxy] Processing ${files.length} file(s)`);
  const upstreamForm = new FormData();

  try {
    for (const file of files) {
      if (!(file instanceof File)) continue;
      const fileName = file.name || `document-${Date.now()}.bin`;
      console.log(`[OCR Proxy] Writing temp file: ${fileName}`);
      const buffer = Buffer.from(await file.arrayBuffer());
      const filePath = await writeTempFile(fileName, buffer);
      tempPaths.push(filePath);
      upstreamForm.append("files", fs.createReadStream(filePath), fileName);
    }

    console.log(`[OCR Proxy] Forwarding to: ${PYTHON_OCR_URL}/api/ocr/process`);
    const response = await axios.post(`${PYTHON_OCR_URL}/api/ocr/process`, upstreamForm, {
      headers: upstreamForm.getHeaders(),
      timeout: 600_000,
    });

    console.log("[OCR Proxy] Success! Received response from Python service");
    return NextResponse.json(response.data);
  } catch (error) {
    console.error("[OCR Proxy] Error:", error);
    
    if (axios.isAxiosError(error)) {
      console.error("[OCR Proxy] Axios error details:", {
        message: error.message,
        code: error.code,
        response: error.response?.data,
        status: error.response?.status,
      });
      
      // Check if Python service is unreachable
      if (error.code === "ECONNREFUSED") {
        return NextResponse.json(
          {
            error: "Python OCR service is not running",
            detail: `Cannot connect to ${PYTHON_OCR_URL}. Please start the Python service with: cd backend-python && python -m uvicorn app.main:app --reload --port 8000`,
          },
          { status: 503 }
        );
      }
    }
    
    return NextResponse.json(
      {
        error: "Failed to forward file to OCR service.",
        detail: error instanceof Error ? error.message : "unknown",
      },
      { status: 502 }
    );
  } finally {
    await Promise.all(
      tempPaths.map(async (filePath) => {
        try {
          await fsPromises.unlink(filePath);
        } catch {
          /* ignore cleanup errors */
        }
      })
    );
  }
}
