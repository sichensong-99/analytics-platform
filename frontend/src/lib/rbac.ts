// Role-based access control (pure — client-safe).
export const ROLES = ['admin', 'viewer'] as const;
export type Role = (typeof ROLES)[number];

export type PageKey =
  | 'style-channel-quantity'
  | 'amazon-shipments'
  | 'cohort'
  | 'catalog'
  | 'lineage'
  | 'admin';

// admin = everything · viewer = business dashboards only (no governance / admin)
const ACCESS: Record<string, PageKey[]> = {
  admin: ['style-channel-quantity', 'amazon-shipments', 'cohort', 'catalog', 'lineage', 'admin'],
  viewer: ['style-channel-quantity', 'amazon-shipments', 'cohort'],
};

export function canAccess(role: string | undefined, page: PageKey): boolean {
  if (!role) return false;
  return (ACCESS[role] ?? []).includes(page);
}