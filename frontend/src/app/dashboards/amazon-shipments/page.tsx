'use client';

import { useEffect, useState, useMemo } from 'react';
import Link from 'next/link';

const STATUS_OPTIONS = [
  'WORKING', 'READY_TO_SHIP', 'SHIPPED', 'RECEIVING', 'IN_TRANSIT',
  'DELIVERED', 'CHECKED_IN', 'CLOSED', 'CANCELLED', 'DELETED', 'ERROR',
];

const PAGE_SIZE = 25; // 跟 Style 页一致

interface Row {
  shipment_id: string;
  shipment_name: string;
  shipment_status: string;
  destination_fc_id: string;
  created_date: string | null;
  seller_sku: string;
  fulfillment_network_sku: string;
  quantity_shipped: number;
  quantity_received: number;
  quantity_in_case: number;
  receiving_gap: number;
}

interface SnapshotResponse {
  metric_id: string;
  name: string;
  version: string;
  unit: string;
  params: Record<string, unknown>;
  data: Row[];
}

function csvEscape(value: unknown): string {
  if (value === null || value === undefined) return '';
  return `"${String(value).replace(/"/g, '""')}"`;
}

export default function AmazonShipmentsPage() {
  const [selectedStatuses, setSelectedStatuses] = useState<string[]>([]);
  const [selectedFcs, setSelectedFcs] = useState<string[]>([]);
  const [resp, setResp] = useState<SnapshotResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [page, setPage] = useState(1); // 分页：当前页

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError('');
      const qs = new URLSearchParams();
      selectedStatuses.forEach((s) => qs.append('statuses', s));
      selectedFcs.forEach((f) => qs.append('fcs', f));
      try {
        const r = await fetch(`/api/snapshot/amazon_fba_receiving_by_sku?${qs.toString()}`);
        const d = await r.json();
        if (!r.ok) throw new Error(d.error ?? d.detail ?? `HTTP ${r.status}`);
        if (d.error) throw new Error(d.error);
        if (!cancelled) { setResp(d); setLoading(false); }
      } catch (e) {
        if (!cancelled) {
          setResp(null);
          setError(e instanceof Error ? e.message : String(e));
          setLoading(false);
        }
      }
    }
    load();
    return () => { cancelled = true; };
  }, [selectedStatuses, selectedFcs]);

  const rows = resp?.data ?? [];

  // 数据变了（换 filter / 重新加载）就回到第 1 页
  useEffect(() => { setPage(1); }, [resp]);

  const totalPages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const pageRows = useMemo(
    () => rows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE),
    [rows, page],
  );

  const kpi = useMemo(() => ({
    nShipments: new Set(rows.map((r) => r.shipment_id)).size,
    nSkus: new Set(rows.map((r) => r.seller_sku)).size,
    totalShipped: rows.reduce((s, r) => s + (r.quantity_shipped ?? 0), 0),
    totalGap: rows.reduce((s, r) => s + (r.receiving_gap ?? 0), 0),
  }), [rows]);

  const fcOptions = useMemo(
    () => Array.from(new Set(rows.map((r) => r.destination_fc_id).filter(Boolean))).sort(),
    [rows],
  );

  function downloadCSV() {
    if (rows.length === 0) return;
    const headers = [
      'shipment_id', 'shipment_name', 'shipment_status', 'destination_fc_id',
      'created_date', 'seller_sku', 'fulfillment_network_sku',
      'quantity_shipped', 'quantity_received', 'quantity_in_case', 'receiving_gap',
    ];
    const lines = [headers.join(',')];
    for (const r of rows) { // 注意：导出用全量 rows，不是 pageRows
      lines.push([
        csvEscape(r.shipment_id), csvEscape(r.shipment_name),
        csvEscape(r.shipment_status), csvEscape(r.destination_fc_id),
        csvEscape(r.created_date), csvEscape(r.seller_sku),
        csvEscape(r.fulfillment_network_sku),
        r.quantity_shipped, r.quantity_received, r.quantity_in_case, r.receiving_gap,
      ].join(','));
    }
    const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `amazon-fba-receiving-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function toggleItem(arr: string[], item: string, setter: (a: string[]) => void) {
    setter(arr.includes(item) ? arr.filter((x) => x !== item) : [...arr, item]);
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white border-b border-gray-200 px-6 py-3">
        <Link href="/dashboards" className="text-sm text-blue-600 hover:underline">
          Back to Dashboards
        </Link>
      </nav>

      <main className="max-w-7xl mx-auto px-6 py-8">
        <div className="flex justify-between items-start mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              Amazon FBA Inbound — Receiving by SKU
            </h1>
            <p className="text-xs text-gray-400 mt-1">
              {resp
                ? `Powered by Metrics Service - ${resp.metric_id} ${resp.version}`
                : 'Loading metric definition...'}
            </p>
            <p className="text-xs text-gray-500 mt-1">
              Migrated from PBI amazon_ship - SP-API shipmentItems x shipments
            </p>
          </div>
          <button
            onClick={downloadCSV}
            disabled={rows.length === 0}
            className="px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
          >
            Download CSV
          </button>
        </div>

        {/* Filters */}
        <div className="bg-white p-4 rounded-lg border border-gray-200 mb-6">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">Filters</h3>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Shipment Status - empty = all
              </label>
              <div className="max-h-32 overflow-y-auto border border-gray-200 rounded p-2 text-sm">
                {STATUS_OPTIONS.map((s) => (
                  <label key={s} className="flex items-center gap-2 py-0.5">
                    <input
                      type="checkbox"
                      checked={selectedStatuses.includes(s)}
                      onChange={() => toggleItem(selectedStatuses, s, setSelectedStatuses)}
                    />
                    <span>{s}</span>
                  </label>
                ))}
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Destination FC - empty = all
              </label>
              <div className="max-h-32 overflow-y-auto border border-gray-200 rounded p-2 text-sm">
                {fcOptions.length === 0 ? (
                  <p className="text-xs text-gray-400">No data loaded.</p>
                ) : (
                  fcOptions.map((f) => (
                    <label key={f} className="flex items-center gap-2 py-0.5">
                      <input
                        type="checkbox"
                        checked={selectedFcs.includes(f)}
                        onChange={() => toggleItem(selectedFcs, f, setSelectedFcs)}
                      />
                      <span>{f}</span>
                    </label>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>

        {loading && (
          <div className="bg-white p-4 rounded-lg border border-gray-200 text-sm text-gray-500">
            Loading from FastAPI...
          </div>
        )}

        {error && (
          <div className="bg-white p-4 rounded-lg border border-red-200 text-sm">
            <p className="text-red-600 font-semibold">Error: {error}</p>
          </div>
        )}

        {!loading && !error && (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
              <KpiCard label="Shipments" value={kpi.nShipments.toString()} />
              <KpiCard label="SKUs" value={kpi.nSkus.toString()} />
              <KpiCard label="Units Shipped" value={kpi.totalShipped.toLocaleString()} />
              <KpiCard label="Receiving Gap" value={kpi.totalGap.toLocaleString()} />
            </div>

            <div className="bg-white p-4 rounded-lg border border-gray-200 overflow-x-auto">
              <h3 className="text-sm font-semibold text-gray-700 mb-3">
                Receiving Detail ({rows.length.toLocaleString()} rows)
              </h3>
              {rows.length === 0 ? (
                <p className="text-sm text-gray-500">No data for the selected filters.</p>
              ) : (
                <>
                  <table className="min-w-full text-sm">
                    <thead>
                      <tr className="border-b border-gray-200 bg-gray-50">
                        <th className="text-left px-2 py-2 font-medium">Shipment</th>
                        <th className="text-left px-2 py-2 font-medium">Status</th>
                        <th className="text-left px-2 py-2 font-medium">FC</th>
                        <th className="text-left px-2 py-2 font-medium">Created</th>
                        <th className="text-left px-2 py-2 font-medium">SKU</th>
                        <th className="text-right px-2 py-2 font-medium">Shipped</th>
                        <th className="text-right px-2 py-2 font-medium">Received</th>
                        <th className="text-right px-2 py-2 font-medium bg-amber-50">Gap</th>
                      </tr>
                    </thead>
                    <tbody>
                      {pageRows.map((r, idx) => (
                        <tr key={`${r.shipment_id}-${r.seller_sku}-${(page - 1) * PAGE_SIZE + idx}`}
                            className="border-b border-gray-100 hover:bg-gray-50">
                          <td className="px-2 py-1.5 font-mono text-xs">{r.shipment_id}</td>
                          <td className="px-2 py-1.5 text-xs">{r.shipment_status}</td>
                          <td className="px-2 py-1.5 text-xs">{r.destination_fc_id}</td>
                          <td className="px-2 py-1.5 text-xs">{r.created_date ?? '—'}</td>
                          <td className="px-2 py-1.5 font-mono text-xs">{r.seller_sku}</td>
                          <td className="px-2 py-1.5 text-right tabular-nums">
                            {(r.quantity_shipped ?? 0).toLocaleString()}
                          </td>
                          <td className="px-2 py-1.5 text-right tabular-nums">
                            {(r.quantity_received ?? 0).toLocaleString()}
                          </td>
                          <td className={`px-2 py-1.5 text-right tabular-nums font-semibold bg-amber-50 ${
                            r.receiving_gap > 0 ? 'text-amber-700' : 'text-gray-400'
                          }`}>
                            {(r.receiving_gap ?? 0).toLocaleString()}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>

                  {rows.length > PAGE_SIZE && (
                    <div className="flex items-center justify-between mt-3 text-sm">
                      <span className="text-gray-500">
                        Showing {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, rows.length)} of {rows.length.toLocaleString()}
                      </span>
                      <div className="flex items-center gap-2">
                        <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}
                          className="px-3 py-1 border border-gray-200 rounded disabled:opacity-40 hover:bg-gray-50">
                          Prev
                        </button>
                        <span className="text-gray-600">Page {page} / {totalPages}</span>
                        <button onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page >= totalPages}
                          className="px-3 py-1 border border-gray-200 rounded disabled:opacity-40 hover:bg-gray-50">
                          Next
                        </button>
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          </>
        )}
      </main>
    </div>
  );
}

function KpiCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-white p-4 rounded-lg border border-gray-200">
      <div className="text-sm text-gray-500">{label}</div>
      <div className="text-2xl font-bold text-gray-900 mt-1">{value}</div>
    </div>
  );
}