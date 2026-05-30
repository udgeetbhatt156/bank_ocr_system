import { NextResponse } from "next/server";

import { getAuthUserId } from "@/lib/auth-server";
import {
  fetchUserDocuments,
  fetchUserStatementList,
} from "@/lib/statements";

export async function GET(request: Request) {
  const userId = await getAuthUserId();
  if (!userId) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { searchParams } = new URL(request.url);
  const view = searchParams.get("view");

  if (view === "list") {
    const statements = await fetchUserStatementList(userId);
    return NextResponse.json(
      { statements },
      {
        headers: {
          "Cache-Control": "private, max-age=15, stale-while-revalidate=30",
        },
      }
    );
  }

  const documents = await fetchUserDocuments(userId);
  return NextResponse.json(
    { status: "success", documents },
    {
      headers: {
        "Cache-Control": "private, max-age=15, stale-while-revalidate=30",
      },
    }
  );
}
