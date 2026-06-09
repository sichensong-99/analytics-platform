import { NextResponse } from 'next/server';
import { requireRole } from '@/lib/guard';
import { deleteUser } from '@/lib/users';

export async function DELETE(
  _req: Request,
  { params }: { params: Promise<{ email: string }> },
) {
  const admin = await requireRole('admin');
  if (!admin) return NextResponse.json({ error: 'Forbidden' }, { status: 403 });

  const target = decodeURIComponent((await params).email);
  if (admin.email?.toLowerCase() === target.toLowerCase()) {
    return NextResponse.json({ error: 'You cannot delete your own account' }, { status: 400 });
  }
  try {
    await deleteUser(target);
    return NextResponse.json({ success: true });
  } catch (e) {
    return NextResponse.json({ error: e instanceof Error ? e.message : String(e) }, { status: 500 });
  }
}