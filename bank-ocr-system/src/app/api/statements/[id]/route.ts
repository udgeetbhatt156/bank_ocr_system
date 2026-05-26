import { NextResponse } from "next/server";

import { getAuthUser } from "@/lib/auth-server";
import {
  getStatementForUser,
  statementToDocumentResult,
} from "@/lib/statements";

type RouteContext = { params: Promise<{ id: string }> };

export async function GET(_request: Request, context: RouteContext) {
  const user = await getAuthUser();
  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { id } = await context.params;
  const statement = await getStatementForUser(id, user.id);

  if (!statement) {
    return NextResponse.json({ error: "Statement not found" }, { status: 404 });
  }

  return NextResponse.json({
    document: statementToDocumentResult(statement),
  });
}

export async function DELETE(_request: Request, context: RouteContext) {
  const user = await getAuthUser();
  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { id } = await context.params;
  const statement = await getStatementForUser(id, user.id);

  if (!statement) {
    return NextResponse.json({ error: "Statement not found" }, { status: 404 });
  }

  const { prisma } = await import("@/lib/prisma");
  await prisma.statement.delete({ where: { id: statement.id } });

  try {
    const { promises: fs } = await import("fs");
    await fs.unlink(statement.filePath);
  } catch {
    /* ignore */
  }

  return NextResponse.json({ success: true });
}
