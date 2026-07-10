'use client';

import { useEffect, useState } from 'react';
import { ROLES } from '@/lib/rbac';

type User = { email: string; name: string; role: string; createdAt: string };

export default function AdminPanel({ currentEmail }: { currentEmail: string }) {
  const [users, setUsers] = useState<User[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [role, setRole] = useState<string>('viewer');
  const [password, setPassword] = useState('');

  async function load() {
    setLoading(true);
    try {
      const r = await fetch('/api/admin/users');
      if (!r.ok) throw new Error(`list failed (HTTP ${r.status})`);
      const j = await r.json();
      setUsers(j.users ?? []);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  function flash(m: string) {
    setMsg(m);
    setErr(null);
    setTimeout(() => setMsg(null), 3000);
  }

  async function createUser() {
    setErr(null);
    if (!email || !password) {
      setErr('Email and password are required.');
      return;
    }
    const r = await fetch('/api/admin/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, name, role, password }),
    });
    if (!r.ok) {
      const j = await r.json().catch(() => ({}));
      setErr(j.error ?? `create failed (HTTP ${r.status})`);
      return;
    }
    setEmail('');
    setName('');
    setPassword('');
    setRole('viewer');
    flash('User created.');
    load();
  }

  async function changeRole(userEmail: string, newRole: string) {
    const r = await fetch(`/api/admin/users/${encodeURIComponent(userEmail)}/role`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role: newRole }),
    });
    if (!r.ok) {
      setErr(`role update failed (HTTP ${r.status})`);
      return;
    }
    flash(`Role updated for ${userEmail}.`);
    load();
  }

  async function resetPassword(userEmail: string) {
    const np = prompt(`New password for ${userEmail}:`);
    if (!np) return;
    const r = await fetch(`/api/admin/users/${encodeURIComponent(userEmail)}/password`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: np }),
    });
    if (!r.ok) {
      setErr(`password reset failed (HTTP ${r.status})`);
      return;
    }
    flash(`Password reset for ${userEmail}. Share it via Slack/WeChat.`);
  }

  async function removeUser(userEmail: string) {
    if (!confirm(`Delete ${userEmail}? This cannot be undone.`)) return;
    const r = await fetch(`/api/admin/users/${encodeURIComponent(userEmail)}`, {
      method: 'DELETE',
    });
    if (!r.ok) {
      const j = await r.json().catch(() => ({}));
      setErr(j.error ?? `delete failed (HTTP ${r.status})`);
      return;
    }
    flash(`Deleted ${userEmail}.`);
    load();
  }

  return (
    <div className="space-y-8">
      {msg && <div className="rounded bg-green-50 text-green-700 text-sm px-4 py-2">{msg}</div>}
      {err && <div className="rounded bg-red-50 text-red-700 text-sm px-4 py-2">{err}</div>}

      <section className="bg-white rounded-lg border border-gray-200 p-6">
        <h2 className="text-lg font-semibold mb-4">Create user</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <input className="border rounded px-3 py-2 text-sm" placeholder="email@company.com"
            value={email} onChange={(e) => setEmail(e.target.value)} />
          <input className="border rounded px-3 py-2 text-sm" placeholder="Display name"
            value={name} onChange={(e) => setName(e.target.value)} />
          <select className="border rounded px-3 py-2 text-sm" value={role}
            onChange={(e) => setRole(e.target.value)}>
            {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
          <input className="border rounded px-3 py-2 text-sm" placeholder="Initial password"
            value={password} onChange={(e) => setPassword(e.target.value)} />
        </div>
        <button onClick={createUser}
          className="mt-4 bg-blue-600 text-white text-sm px-4 py-2 rounded hover:bg-blue-700">
          Create
        </button>
      </section>

      <section className="bg-white rounded-lg border border-gray-200 p-6">
        <h2 className="text-lg font-semibold mb-4">Users</h2>
        {loading ? (
          <p className="text-sm text-gray-500">Loading…</p>
        ) : users.length === 0 ? (
          <p className="text-sm text-gray-500">No users.</p>
        ) : (
          <div className="space-y-2">
            {users.map((u) => (
              <div key={u.email}
                className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-100 py-2">
                <div className="min-w-0">
                  <div className="text-sm font-medium text-gray-900">{u.name || u.email}</div>
                  <div className="text-xs text-gray-500">{u.email}</div>
                </div>
                <div className="flex items-center gap-2">
                  <select className="border rounded px-2 py-1 text-sm" value={u.role}
                    onChange={(e) => changeRole(u.email, e.target.value)}>
                    {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                  </select>
                  <button onClick={() => resetPassword(u.email)}
                    className="text-sm text-blue-600 hover:underline">
                    reset password
                  </button>
                  {u.email.toLowerCase() !== currentEmail.toLowerCase() && (
                    <button onClick={() => removeUser(u.email)}
                      className="text-sm text-red-600 hover:underline">
                      delete
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}