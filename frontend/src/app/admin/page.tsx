import { redirect } from 'next/navigation';
import Link from 'next/link';
import { requireRole } from '@/lib/guard';
import AdminPanel from './AdminPanel';

export default async function AdminPage() {
  const admin = await requireRole('admin');
  if (!admin) redirect('/dashboards');

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white border-b border-gray-200 px-6 py-3 flex justify-between items-center">
        <h1 className="text-lg font-bold text-gray-900">User Administration</h1>
        <Link href="/dashboards" className="text-sm text-blue-600 hover:underline">
          ← Dashboards
        </Link>
      </nav>
      <main className="max-w-4xl mx-auto px-6 py-8">
        <AdminPanel />
      </main>
    </div>
  );
}