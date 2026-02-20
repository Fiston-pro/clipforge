/**
 * POST /api/generate
 *
 * Proxy that forwards the script to the FastAPI backend and returns the jobId.
 * Keeping the backend URL server-side prevents CORS issues in the browser.
 */

import { NextRequest, NextResponse } from "next/server";

const raw = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
// Ensure the URL always has a protocol prefix so fetch() doesn't throw
const BACKEND_URL = raw.startsWith("http") ? raw : `https://${raw}`;

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    const upstream = await fetch(`${BACKEND_URL}/jobs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: body.text }),
    });

    const data = await upstream.json();
    return NextResponse.json(data, { status: upstream.status });
  } catch (err) {
    console.error("[/api/generate] Backend unreachable:", err);
    return NextResponse.json(
      { error: "Could not reach the backend. Is it running?" },
      { status: 502 }
    );
  }
}
