import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';

const METRICS_SERVICE_URL =
  process.env.METRICS_SERVICE_URL || 'http://localhost:8000';

// Whitelist of query params we forward to FastAPI.
// Adding a new optional filter for a future metric only requires extending
// this list - no other proxy code changes.
const REQUIRED_PARAMS = ['start_date', 'end_date'] as const;

const FORWARD_PARAMS = [
  'start_date',
  'end_date',
  'channels',
  'seasons',
  'styles',
] as const;

export async function GET(
  req: NextRequest,
  context: { params: Promise<{ metricId: string }> },
) {
  const { metricId } = await context.params;
  const { searchParams } = new URL(req.url);

  // Required params guard
  for (const p of REQUIRED_PARAMS) {
    if (!searchParams.get(p)) {
      return NextResponse.json(
        { error: `Missing ${p}` },
        { status: 400 },
      );
    }
  }

  // JWT from cookie
  const cookieStore = await cookies();
  const token = cookieStore.get('auth-token')?.value;

  if (!token) {
    return NextResponse.json(
      { error: 'Not authenticated' },
      { status: 401 },
    );
  }

  // Forward whitelisted params, preserving repeated values
  // Example: ?channels=google-ads&channels=facebook-ads
  const forwarded = new URLSearchParams();

  for (const name of FORWARD_PARAMS) {
    for (const value of searchParams.getAll(name)) {
      forwarded.append(name, value);
    }
  }

  const upstreamUrl = `${METRICS_SERVICE_URL}/metrics/${metricId}?${forwarded.toString()}`;

  try {
    const res = await fetch(upstreamUrl, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
      cache: 'no-store',
    });

    const text = await res.text();

    // FastAPI returned empty body
    if (!text.trim()) {
      return NextResponse.json(
        {
          error: 'Metrics service returned empty response body',
          upstream_status: res.status,
          upstream_url: upstreamUrl,
        },
        { status: res.ok ? 502 : res.status },
      );
    }

    // FastAPI returned body, but it may not be JSON
    let data: unknown;

    try {
      data = JSON.parse(text);
    } catch {
      return NextResponse.json(
        {
          error: 'Metrics service returned non-JSON response',
          upstream_status: res.status,
          upstream_url: upstreamUrl,
          body_preview: text.slice(0, 500),
        },
        { status: 502 },
      );
    }

    return NextResponse.json(data, { status: res.status });
  } catch (e) {
    return NextResponse.json(
      {
        error: e instanceof Error ? e.message : String(e),
        upstream_url: upstreamUrl,
      },
      { status: 500 },
    );
  }
}