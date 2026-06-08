// Server-only: verify the JWT cookie and require one of the given roles.
import { cookies } from 'next/headers';
import { verifyToken, type UserPayload } from '@/lib/auth';

export async function requireRole(...roles: string[]): Promise<UserPayload | null> {
  const token = (await cookies()).get('auth-token')?.value;
  const user = token ? verifyToken(token) : null;
  if (!user || !roles.includes(user.role)) return null;
  return user;
}