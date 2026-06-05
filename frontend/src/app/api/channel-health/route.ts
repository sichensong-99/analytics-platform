import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';

const METRICS_SERVICE_URL =
  process.env.METRICS_SERVICE_URL || 'http://localhost:8000';

// Server-side proxy for the public /metrics/channel-health endpoint.
// Forwards the ?minutes= lookback param.
export async function GET(req: NextRequest) {
  const cookieStore = await cookies();
  const token = cookieStore.get('auth-token')?.value;
  if (!token) {
    return NextResponse.json({ error: 'Not authenticated' }, { status: 401 });
  }

  const { searchParams } = new URL(req.url);
  const minutes = searchParams.get('minutes') ?? '30';
  const upstreamUrl = `${METRICS_SERVICE_URL}/metrics/channel-health?minutes=${encodeURIComponent(minutes)}`;
  try {
    const res = await fetch(upstreamUrl, {
      headers: { Authorization: `Bearer ${token}` },
      cache: 'no-store',
    });
    const text = await res.text();
    if (!text.trim()) {
      return NextResponse.json(
        { error: 'Metrics service returned empty response body', upstream_status: res.status, upstream_url: upstreamUrl },
        { status: res.ok ? 502 : res.status },
      );
    }
    let data: unknown;
    try {
      data = JSON.parse(text);
    } catch {
      return NextResponse.json(
        { error: 'Metrics service returned non-JSON response', upstream_status: res.status, upstream_url: upstreamUrl, body_preview: text.slice(0, 500) },
        { status: 502 },
      );
    }
    return NextResponse.json(data, { status: res.status });
  } catch (e) {
    return NextResponse.json(
      { error: e instanceof Error ? e.message : String(e), upstream_url: upstreamUrl },
      { status: 500 },
    );
  }
}