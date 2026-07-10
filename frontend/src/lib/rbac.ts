// Role-based access control (pure — client-safe).
export const ROLES = ['admin', 'viewer'] as const;
export type Role = (typeof ROLES)[number];

export type PageKey =
  | 'style-channel-quantity'
  | 'page-view' 
  | 'amazon-shipments'
  | 'cohort'
  | 'catalog'
  | 'lineage'
  | 'admin';

// admin = everything (incl. user management) · viewer = all dashboards + Catalog/Lineage (read-only); admin console stays admin-only
const ACCESS: Record<string, PageKey[]> = {
  admin:  ['style-channel-quantity', 'page-view', 'amazon-shipments', 'cohort', 'catalog', 'lineage', 'admin'],
  viewer: ['style-channel-quantity', 'page-view', 'amazon-shipments', 'cohort', 'catalog', 'lineage'],
};

export function canAccess(role: string | undefined, page: PageKey): boolean {
  if (!role) return false;
  return (ACCESS[role] ?? []).includes(page);
}