import { NextResponse } from "next/server";

import { getAuthUserId } from "@/lib/auth-server";
import {
  deleteStatementForUser,
  formatStatementDetail,
  getStatementForUser,
} from "@/lib/statements";

type RouteContext = { params: Promise<{ id: string }> };

export async function GET(_request: Request, context: RouteContext) {
  const userId = await getAuthUserId();
  if (!userId) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { id } = await context.params;
  const statement = await getStatementForUser(id, userId);

  if (!statement) {
    return NextResponse.json({ error: "Statement not found" }, { status: 404 });
  }

  return NextResponse.json({
    document: formatStatementDetail(statement),
  });
}

export async function DELETE(_request: Request, context: RouteContext) {
  const userId = await getAuthUserId();
  if (!userId) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { id } = await context.params;
  const deleted = await deleteStatementForUser(id, userId);

  if (!deleted) {
    return NextResponse.json({ error: "Statement not found" }, { status: 404 });
  }

  return NextResponse.json({ success: true });
}
