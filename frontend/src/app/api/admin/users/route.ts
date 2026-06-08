import { NextRequest, NextResponse } from 'next/server';
import { requireRole } from '@/lib/guard';
import { listUsers, createUser } from '@/lib/users';

export async function GET() {
  if (!(await requireRole('admin'))) {
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
  }
  try {
    const users = await listUsers();
    return NextResponse.json({ users });
  } catch (e) {
    return NextResponse.json({ error: e instanceof Error ? e.message : String(e) }, { status: 500 });
  }
}

export async function POST(req: NextRequest) {
  if (!(await requireRole('admin'))) {
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
  }
  const { email, name, role, password } = await req.json();
  if (!email || !password) {
    return NextResponse.json({ error: 'Email and password are required' }, { status: 400 });
  }
  try {
    await createUser({ email, name: name ?? '', role: role ?? 'viewer', password });
    return NextResponse.json({ success: true });
  } catch (e) {
    const status = (e as { statusCode?: number })?.statusCode === 409 ? 409 : 500;
    const error =
      status === 409 ? 'A user with that email already exists' : (e instanceof Error ? e.message : String(e));
    return NextResponse.json({ error }, { status });
  }
}