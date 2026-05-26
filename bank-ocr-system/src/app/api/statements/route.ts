import { NextResponse } from "next/server";

import { getAuthUser } from "@/lib/auth-server";
import {
  fetchUserDocuments,
  fetchUserStatementList,
} from "@/lib/statements";

export async function GET(request: Request) {
  const user = await getAuthUser();
  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { searchParams } = new URL(request.url);
  const view = searchParams.get("view");

  if (view === "list") {
    const statements = await fetchUserStatementList(user.id);
    return NextResponse.json({ statements });
  }

  const documents = await fetchUserDocuments(user.id);
  return NextResponse.json({ status: "success", documents });
}
