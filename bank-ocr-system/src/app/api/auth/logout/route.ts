import { NextResponse } from "next/server";

import { isSecureRequest } from "@/lib/auth-cookies";

export async function POST(request: Request) {
  const response = NextResponse.json({ success: true });
  response.cookies.set({
    name: "bankocr_session",
    value: "",
    path: "/",
    maxAge: 0,
    httpOnly: true,
    sameSite: "lax",
    secure: isSecureRequest(request),
  });
  return response;
}
