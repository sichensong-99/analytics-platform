import { NextResponse } from 'next/server';
import { cookies } from 'next/headers';
import { requireRole } from '@/lib/guard';

const METRICS_SERVICE_URL = process.env.METRICS_SERVICE_URL || 'http://localhost:8000';

export async function GET() {
  if (!(await requireRole('admin'))) {
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
  }
  const token = (await cookies()).get('auth-token')?.value;
  const upstreamUrl = `${METRICS_SERVICE_URL}/catalog`;
  try {
    const res = await fetch(upstreamUrl, { headers: { Authorization: `Bearer ${token}` }, cache: 'no-store' });
    const text = await res.text();
    if (!text.trim()) {
      return NextResponse.json({ error: 'empty response', upstream_status: res.status }, { status: res.ok ? 502 : res.status });
    }
    let data: unknown;
    try { data = JSON.parse(text); }
    catch { return NextResponse.json({ error: 'non-JSON', body_preview: text.slice(0, 500) }, { status: 502 }); }
    return NextResponse.json(data, { status: res.status });
  } catch (e) {
    return NextResponse.json({ error: e instanceof Error ? e.message : String(e) }, { status: 500 });
  }
}