import { NextRequest, NextResponse } from 'next/server';
import { requireRole } from '@/lib/guard';
import { setUserPassword } from '@/lib/users';

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ email: string }> },
) {
  if (!(await requireRole('admin'))) {
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
  }
  const { email } = await params;
  const { password } = await req.json();
  if (!password) return NextResponse.json({ error: 'password is required' }, { status: 400 });
  try {
    await setUserPassword(decodeURIComponent(email), password);
    return NextResponse.json({ success: true });
  } catch (e) {
    return NextResponse.json({ error: e instanceof Error ? e.message : String(e) }, { status: 500 });
  }
}