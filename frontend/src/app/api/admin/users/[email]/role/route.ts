import { NextRequest, NextResponse } from 'next/server';
import { requireRole } from '@/lib/guard';
import { setUserRole } from '@/lib/users';

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ email: string }> },
) {
  if (!(await requireRole('admin'))) {
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
  }
  const { email } = await params;
  const { role } = await req.json();
  if (!role) return NextResponse.json({ error: 'role is required' }, { status: 400 });
  try {
    await setUserRole(decodeURIComponent(email), role);
    return NextResponse.json({ success: true });
  } catch (e) {
    return NextResponse.json({ error: e instanceof Error ? e.message : String(e) }, { status: 500 });
  }
}