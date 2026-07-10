// Server-only: verify the JWT cookie and require one of the given roles.
import { cookies } from 'next/headers';
import { verifyToken, type UserPayload } from '@/lib/auth';
import { canAccess, type PageKey } from '@/lib/rbac';

export async function requireRole(...roles: string[]): Promise<UserPayload | null> {
  const token = (await cookies()).get('auth-token')?.value;
  const user = token ? verifyToken(token) : null;
  if (!user || !roles.includes(user.role)) return null;
  return user;
}

// Server-only: verify the JWT cookie and require access to a specific page,
// using the single source of truth in rbac.ts (canAccess).
export async function requirePage(page: PageKey): Promise<UserPayload | null> {
  const token = (await cookies()).get('auth-token')?.value;
  const user = token ? verifyToken(token) : null;
  if (!user || !canAccess(user.role, page)) return null;
  return user;
}