// Role-based access control (pure — no server imports, client-safe).

export const ROLES = [
  'admin',
  'merchandising',
  'marketing',
  'operations',
  'geodis',
  'viewer',
] as const;

export type Role = (typeof ROLES)[number];

export type PageKey =
  | 'style-channel-quantity'
  | 'amazon-shipments'
  | 'catalog'
  | 'lineage'
  | 'admin';

// Which pages each role may access. Adjust to your team's real needs.
const ACCESS: Record<string, PageKey[]> = {
  admin: ['style-channel-quantity', 'amazon-shipments', 'catalog', 'lineage', 'admin'],
  merchandising: ['style-channel-quantity', 'amazon-shipments'],
  marketing: ['style-channel-quantity'],
  operations: ['amazon-shipments', 'style-channel-quantity'],
  geodis: ['amazon-shipments'],
  viewer: ['style-channel-quantity', 'amazon-shipments'],
};

export function canAccess(role: string | undefined, page: PageKey): boolean {
  if (!role) return false;
  return (ACCESS[role] ?? []).includes(page);
}