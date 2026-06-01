import Link from 'next/link';
import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { verifyToken } from '@/lib/auth';

const dashboards = [
  {
    id: 'shopify-sales',
    title: 'Shopify Sales Overview',
    description: 'Daily orders, revenue, top products, and recent transactions',
    category: 'Sales',
    color: 'bg-blue-50 text-blue-700',
  },
  {
    id: 'ad-attribution',
    title: 'Ad Attribution (Triple Whale)',
    description: 'Channel performance, ROAS, ad spend trends',
    category: 'Marketing',
    color: 'bg-purple-50 text-purple-700',
  },
  {
    id: 'style-channel-quantity',
    title: 'Style × Channel × Week — Quantity',
    description:
      'Units sold sliced by product style and marketing channel · Replaces PBI Style_selling_df page',
    category: 'Sales × Marketing',
    color: 'bg-emerald-50 text-emerald-700',
  },
  {
    id: 'amazon-shipments',
    title: 'Amazon FBA — Receiving by SKU',
    description:
      'FBA inbound shipment receiving status by SKU · Replaces PBI amazon_ship feed',
    category: 'Operations',
    color: 'bg-amber-50 text-amber-700',
  },
];

export default async function DashboardsPage() {
  const cookieStore = await cookies();
  const token = cookieStore.get('auth-token')?.value;
  const user = token ? verifyToken(token) : null;

  if (!user) {
    redirect('/');
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white border-b border-gray-200 px-6 py-3 flex justify-between items-center">
        <h1 className="text-lg font-bold text-gray-900">Internal Analytics</h1>
        <div className="flex items-center gap-4">
          <span className="text-sm text-gray-600">{user.name}</span>
          <form action="/api/logout" method="POST">
            <button
              type="submit"
              className="text-sm text-blue-600 hover:underline"
            >
              Sign out
            </button>
          </form>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto px-6 py-8">
        <div className="mb-6">
          <h2 className="text-2xl font-bold text-gray-900">Dashboards</h2>
          <p className="text-gray-500 mt-1">
            Browse available analytics dashboards
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {dashboards.map((d) => (
            <Link
              key={d.id}
              href={`/dashboards/${d.id}`}
              className="bg-white p-6 rounded-lg border border-gray-200 hover:shadow-md hover:border-blue-300 transition"
            >
              <span
                className={`inline-block text-xs font-medium px-2 py-1 rounded ${d.color} mb-3`}
              >
                {d.category}
              </span>
              <h3 className="text-lg font-semibold text-gray-900 mb-1">
                {d.title}
              </h3>
              <p className="text-sm text-gray-500">{d.description}</p>
            </Link>
          ))}
        </div>
      </main>
    </div>
  );
}