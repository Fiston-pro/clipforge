/**
 * GET /api/status/[jobId]
 *
 * Proxy that polls the FastAPI backend for job status.
 * Also rewrites the relative video URL (e.g. "/videos/abc.mp4") into a
 * fully-qualified backend URL so the browser can load the video directly.
 */

import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ jobId: string }> }
) {
  try {
    const { jobId } = await params;

    const upstream = await fetch(`${BACKEND_URL}/jobs/${jobId}`, {
      // Don't cache status responses — we need fresh data on every poll
      cache: "no-store",
    });

    const data = await upstream.json();

    // Rewrite relative video URL → absolute backend URL
    if (data.url && !data.url.startsWith("http")) {
      data.url = `${BACKEND_URL}${data.url}`;
    }

    return NextResponse.json(data, { status: upstream.status });
  } catch (err) {
    console.error("[/api/status] Backend unreachable:", err);
    return NextResponse.json(
      { error: "Could not reach the backend." },
      { status: 502 }
    );
  }
}
