import { NextResponse } from 'next/server';
import { cookies } from 'next/headers';

const METRICS_SERVICE_URL =
  process.env.METRICS_SERVICE_URL || 'http://localhost:8000';

// Server-side proxy for the public /lineage endpoint.
export async function GET() {
  const cookieStore = await cookies();
  const token = cookieStore.get('auth-token')?.value;
  if (!token) {
    return NextResponse.json({ error: 'Not authenticated' }, { status: 401 });
  }

  const upstreamUrl = `${METRICS_SERVICE_URL}/lineage`;
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