import { cookies } from "next/headers";

import { prisma } from "@/lib/prisma";
import { verifyToken } from "@/lib/jwt";

export type AuthUser = {
  id: string;
  email: string;
  name: string | null;
};

export async function getAuthUser(): Promise<AuthUser | null> {
  const cookieStore = await cookies();
  const token = cookieStore.get("bankocr_session")?.value;
  if (!token) return null;

  try {
    const payload = await verifyToken(token);
    const userId = String(payload.sub || "");
    if (!userId) return null;

    const user = await prisma.user.findUnique({
      where: { id: userId },
      select: { id: true, email: true, name: true },
    });
    return user;
  } catch {
    return null;
  }
}

export async function requireAuthUser(): Promise<AuthUser> {
  const user = await getAuthUser();
  if (!user) {
    throw new Error("UNAUTHORIZED");
  }
  return user;
}
