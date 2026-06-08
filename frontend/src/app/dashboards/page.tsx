import Link from 'next/link';
import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { verifyToken } from '@/lib/auth';
import { canAccess, type PageKey } from '@/lib/rbac';

type Card = {
  key: PageKey;
  href: string;
  title: string;
  description: string;
  category: string;
  color: string;
};

const dashboards: Card[] = [
  {
    key: 'style-channel-quantity',
    href: '/dashboards/style-channel-quantity',
    title: 'Style × Channel × Week — Quantity',
    description:
      'Net units sold sliced by product style and marketing channel · cross-source (Shopify × Triple Whale)',
    category: 'Sales × Marketing',
    color: 'bg-emerald-50 text-emerald-700',
  },
  {
    key: 'amazon-shipments',
    href: '/dashboards/amazon-shipments',
    title: 'Amazon FBA — Receiving by SKU',
    description: 'FBA inbound shipment receiving status by SKU',
    category: 'Operations',
    color: 'bg-amber-50 text-amber-700',
  },
];

const platform: Card[] = [
  {
    key: 'catalog',
    href: '/catalog',
    title: 'Metrics Catalog',
    description: 'Every metric definition, version & changelog — the single source of truth',
    category: 'Platform',
    color: 'bg-slate-100 text-slate-700',
  },
  {
    key: 'lineage',
    href: '/lineage',
    title: 'Data Lineage',
    description: 'Source → warehouse → metric → dashboard DAG · click any node for impact analysis',
    category: 'Platform',
    color: 'bg-slate-100 text-slate-700',
  },
];

function CardGrid({ cards }: { cards: Card[] }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {cards.map((c) => (
        <Link
          key={c.href}
          href={c.href}
          className="bg-white p-6 rounded-lg border border-gray-200 hover:shadow-md hover:border-blue-300 transition"
        >
          <span className={`inline-block text-xs font-medium px-2 py-1 rounded ${c.color} mb-3`}>
            {c.category}
          </span>
          <h3 className="text-lg font-semibold text-gray-900 mb-1">{c.title}</h3>
          <p className="text-sm text-gray-500">{c.description}</p>
        </Link>
      ))}
    </div>
  );
}

export default async function DashboardsPage() {
  const token = (await cookies()).get('auth-token')?.value;
  const user = token ? verifyToken(token) : null;
  if (!user) redirect('/');

  const role = user.role;
  const visibleDashboards = dashboards.filter((c) => canAccess(role, c.key));
  const visiblePlatform = platform.filter((c) => canAccess(role, c.key));
  const isAdmin = canAccess(role, 'admin');

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white border-b border-gray-200 px-6 py-3 flex justify-between items-center">
        <h1 className="text-lg font-bold text-gray-900">Internal Analytics</h1>
        <div className="flex items-center gap-4">
          {isAdmin && (
            <Link href="/admin" className="text-sm text-blue-600 hover:underline">
              Admin
            </Link>
          )}
          <span className="text-sm text-gray-600">
            {user.name} · {role}
          </span>
          <form action="/api/logout" method="POST">
            <button type="submit" className="text-sm text-blue-600 hover:underline">
              Sign out
            </button>
          </form>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto px-6 py-8">
        <div className="mb-6">
          <h2 className="text-2xl font-bold text-gray-900">Dashboards</h2>
          <p className="text-gray-500 mt-1">Analytics available to your role</p>
        </div>

        {visibleDashboards.length > 0 ? (
          <CardGrid cards={visibleDashboards} />
        ) : (
          <p className="text-gray-500">No dashboards assigned to your role yet.</p>
        )}

        {visiblePlatform.length > 0 && (
          <>
            <div className="mt-10 mb-6">
              <h2 className="text-2xl font-bold text-gray-900">Platform</h2>
              <p className="text-gray-500 mt-1">Metric governance & lineage</p>
            </div>
            <CardGrid cards={visiblePlatform} />
          </>
        )}
      </main>
    </div>
  );
}