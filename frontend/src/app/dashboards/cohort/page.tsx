'use client';

import { useEffect, useState, useMemo } from 'react';
import dynamic from 'next/dynamic';
import Link from 'next/link';

const ReactECharts = dynamic(() => import('echarts-for-react'), { ssr: false });

interface MonthlyRow {
  month: string;
  new_orders: number;
  returning_orders: number;
  new_revenue: number;
  returning_revenue: number;
}
interface RetentionRow {
  cohort_month: string;
  period_index: number;
  active_customers: number;
  cohort_size: number;
  retention_rate: number;
}
interface CohortResponse {
  monthly: MonthlyRow[];
  retention: RetentionRow[];
}

const MAX_PERIOD = 12;
const RECENT_COHORTS = 18;
const RECENT_MONTHS = 24;

export default function CohortPage() {
  const [data, setData] = useState<CohortResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError('');
      try {
        const r = await fetch('/api/cohort');
        const d = await r.json();
        if (!r.ok || d.error) throw new Error(d.error ?? `HTTP ${r.status}`);
        if (!cancelled) { setData(d); setLoading(false); }
      } catch (e) {
        if (!cancelled) { setError(e instanceof Error ? e.message : String(e)); setLoading(false); }
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const kpi = useMemo(() => {
    const m = data?.monthly ?? [];
    const ret = data?.retention ?? [];
    const totalNew = m.reduce((s, x) => s + x.new_orders, 0);
    const totalRet = m.reduce((s, x) => s + x.returning_orders, 0);
    const total = totalNew + totalRet;
    const repurchaseRate = total ? Math.round((totalRet / total) * 1000) / 10 : 0;
    const latest = m[m.length - 1];
    const latestTotal = latest ? latest.new_orders + latest.returning_orders : 0;
    const latestRet = latestTotal ? Math.round((latest.returning_orders / latestTotal) * 1000) / 10 : 0;
    return { repurchaseRate, cohorts: new Set(ret.map((r) => r.cohort_month)).size, latestRet, totalOrders: total };
  }, [data]);

  const monthlyOption = useMemo(() => {
    const m = (data?.monthly ?? []).slice(-RECENT_MONTHS);
    return {
      title: { text: 'New vs Returning Orders by Month', textStyle: { fontSize: 14 } },
      tooltip: { trigger: 'axis' },
      legend: { bottom: 0 },
      grid: { left: 60, right: 20, top: 50, bottom: 60 },
      xAxis: { type: 'category', data: m.map((x) => x.month), axisLabel: { fontSize: 11, rotate: 45 } },
      yAxis: { type: 'value', name: 'Orders' },
      series: [
        { name: 'New', type: 'bar', stack: 'orders', data: m.map((x) => x.new_orders), itemStyle: { color: '#6366f1' } },
        { name: 'Returning', type: 'bar', stack: 'orders', data: m.map((x) => x.returning_orders), itemStyle: { color: '#10b981' } },
      ],
    };
  }, [data]);

  const heatmapOption = useMemo(() => {
    const ret = data?.retention ?? [];
    const cohorts = Array.from(new Set(ret.map((r) => r.cohort_month))).sort().slice(-RECENT_COHORTS);
    const xLabels = Array.from({ length: MAX_PERIOD + 1 }, (_, i) => `M${i}`);
    const cells: [number, number, number][] = [];
    for (const r of ret) {
      const y = cohorts.indexOf(r.cohort_month);
      if (y < 0 || r.period_index > MAX_PERIOD) continue;
      cells.push([r.period_index, y, Math.round(r.retention_rate * 1000) / 10]);
    }
    return {
      title: { text: 'Cohort Retention (% of first-month customers still ordering)', textStyle: { fontSize: 14 } },
      tooltip: {
        position: 'top',
        formatter: (p: { data: [number, number, number] }) =>
          `${cohorts[p.data[1]]} · M${p.data[0]}<br/>${p.data[2]}% retained`,
      },
      grid: { left: 70, right: 20, top: 50, bottom: 40 },
      xAxis: { type: 'category', data: xLabels, splitArea: { show: true } },
      yAxis: { type: 'category', data: cohorts, axisLabel: { fontSize: 11 }, splitArea: { show: true } },
      visualMap: { min: 0, max: 100, calculable: true, orient: 'horizontal', left: 'center', bottom: 0,
        inRange: { color: ['#f1f5f9', '#93c5fd', '#2563eb', '#1e3a8a'] } },
      series: [{ type: 'heatmap', data: cells, label: { show: false },
        emphasis: { itemStyle: { shadowBlur: 8, shadowColor: 'rgba(0,0,0,0.3)' } } }],
    };
  }, [data]);

  function downloadCSV() {
    const ret = data?.retention ?? [];
    if (!ret.length) return;
    const headers = ['cohort_month', 'period_index', 'active_customers', 'cohort_size', 'retention_rate'];
    const lines = [headers.join(',')];
    for (const r of ret) {
      lines.push([r.cohort_month, r.period_index, r.active_customers, r.cohort_size, r.retention_rate].join(','));
    }
    const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'cohort-retention.csv';
    a.click();
    URL.revokeObjectURL(url);
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
            <h1 className="text-2xl font-bold text-gray-900">Customer Cohort &amp; Repurchase</h1>
            <p className="text-xs text-gray-500 mt-1">
              Window-function modeling over Shopify orders · new vs returning + cohort retention
            </p>
          </div>
          <button
            onClick={downloadCSV}
            disabled={!data?.retention?.length}
            className="px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
          >
            Download retention CSV
          </button>
        </div>

        {loading && <div className="bg-white p-4 rounded-lg border border-gray-200 text-sm text-gray-500">Loading…</div>}
        {error && (
          <div className="bg-white p-4 rounded-lg border border-red-200 text-sm">
            <p className="text-red-600 font-semibold">Error: {error}</p>
          </div>
        )}

        {!loading && !error && data && (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
              <KpiCard label="Repurchase rate (all-time)" value={`${kpi.repurchaseRate}%`} />
              <KpiCard label="Repurchase rate (latest month)" value={`${kpi.latestRet}%`} />
              <KpiCard label="Cohorts tracked" value={kpi.cohorts.toString()} />
              <KpiCard label="Orders modeled" value={kpi.totalOrders.toLocaleString()} />
            </div>

            <div className="grid grid-cols-1 gap-4">
              <div className="bg-white p-4 rounded-lg border border-gray-200">
                <ReactECharts option={monthlyOption} style={{ height: 360 }} />
              </div>
              <div className="bg-white p-4 rounded-lg border border-gray-200">
                <ReactECharts option={heatmapOption} style={{ height: 520 }} />
              </div>
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