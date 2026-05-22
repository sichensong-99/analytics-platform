import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';

const METRICS_SERVICE_URL =
  process.env.METRICS_SERVICE_URL || 'http://localhost:8000';

// Whitelist of query params we forward to FastAPI.
// Adding a new optional filter for a future metric only requires extending
// this list — no other proxy code changes.
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
    return NextResponse.json({ error: 'Not authenticated' }, { status: 401 });
  }

  // Forward whitelisted params, preserving repeated values
  // (e.g. ?channels=google-ads&channels=meta)
  const forwarded = new URLSearchParams();
  for (const name of FORWARD_PARAMS) {
    for (const value of searchParams.getAll(name)) {
      forwarded.append(name, value);
    }
  }

  const url = `${METRICS_SERVICE_URL}/metrics/${metricId}?${forwarded.toString()}`;
  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}