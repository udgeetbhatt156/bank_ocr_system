import { promises as fs } from "fs";
import path from "path";
import { NextResponse } from "next/server";

import { getAuthUserId } from "@/lib/auth-server";
import { getStatementFilePath } from "@/lib/statements";

type RouteContext = { params: Promise<{ id: string }> };

function contentTypeForFile(fileName: string) {
  const ext = path.extname(fileName).toLowerCase();
  switch (ext) {
    case ".pdf":
      return "application/pdf";
    case ".png":
      return "image/png";
    case ".jpg":
    case ".jpeg":
      return "image/jpeg";
    case ".gif":
      return "image/gif";
    case ".tiff":
    case ".tif":
      return "image/tiff";
    default:
      return "application/octet-stream";
  }
}

export async function GET(_request: Request, context: RouteContext) {
  const userId = await getAuthUserId();
  if (!userId) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { id } = await context.params;
  const fileInfo = await getStatementFilePath(id, userId);

  if (!fileInfo) {
    return NextResponse.json({ error: "Statement not found" }, { status: 404 });
  }

  try {
    const buffer = await fs.readFile(fileInfo.filePath);
    return new NextResponse(buffer, {
      headers: {
        "Content-Type": contentTypeForFile(fileInfo.fileName),
        "Content-Disposition": `inline; filename="${fileInfo.fileName}"`,
        "Cache-Control": "private, max-age=3600",
      },
    });
  } catch {
    return NextResponse.json({ error: "File not found on server" }, { status: 404 });
  }
}
