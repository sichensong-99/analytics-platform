'use client';

import { useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import Link from 'next/link';

const ReactECharts = dynamic(() => import('echarts-for-react'), { ssr: false });


// Date range: last 30 days
function getDateRange() {
  const end = new Date();
  const start = new Date();
  start.setDate(start.getDate() - 29);
  return {
    start: start.toISOString().slice(0, 10),
    end: end.toISOString().slice(0, 10),
  };
}


interface MetricResponse {
  metric_id: string;
  name: string;
  version: string;
  unit: string;
  data: { date: string; value: number }[];
}


export default function ShopifySalesPage() {
  const [revenue, setRevenue] = useState<MetricResponse | null>(null);
  const [aov, setAov] = useState<MetricResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const { start, end } = getDateRange();

    Promise.all([
      fetch(`/api/metrics/revenue_by_day?start_date=${start}&end_date=${end}`).then(
        (r) => r.json(),
      ),
      fetch(`/api/metrics/aov_by_day?start_date=${start}&end_date=${end}`).then(
        (r) => r.json(),
      ),
    ])
      .then(([rev, aovData]) => {
        if (rev.error || aovData.error) {
          setError(rev.error || aovData.error);
        } else {
          setRevenue(rev);
          setAov(aovData);
        }
        setLoading(false);
      })
      .catch((e) => {
        setError(String(e));
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <p className="text-gray-500">Loading metrics from FastAPI...</p>
      </div>
    );
  }

  if (error || !revenue || !aov) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="bg-white p-6 rounded border border-red-200">
          <p className="text-red-600 font-semibold mb-2">Error loading data</p>
          <p className="text-sm text-gray-600">{error}</p>
        </div>
      </div>
    );
  }

  const totalRevenue = revenue.data.reduce((sum, d) => sum + d.value, 0);
  const avgAov =
    aov.data.reduce((sum, d) => sum + d.value, 0) / Math.max(aov.data.length, 1);
  const todayRevenue = revenue.data[revenue.data.length - 1]?.value ?? 0;

  const trendOption = {
    title: {
      text: `${revenue.name} (Last 30 Days)`,
      textStyle: { fontSize: 14 },
    },
    tooltip: { trigger: 'axis' },
    grid: { left: 60, right: 20, top: 50, bottom: 30 },
    xAxis: {
      type: 'category',
      data: revenue.data.map((d) => d.date.slice(5)),
      axisLabel: { fontSize: 11 },
    },
    yAxis: { type: 'value' },
    series: [
      {
        data: revenue.data.map((d) => d.value),
        type: 'line',
        smooth: true,
        areaStyle: { opacity: 0.2 },
        lineStyle: { color: '#3b82f6' },
        itemStyle: { color: '#3b82f6' },
      },
    ],
  };

  const aovOption = {
    title: {
      text: `${aov.name} Trend`,
      textStyle: { fontSize: 14 },
    },
    tooltip: { trigger: 'axis' },
    grid: { left: 60, right: 20, top: 50, bottom: 30 },
    xAxis: {
      type: 'category',
      data: aov.data.map((d) => d.date.slice(5)),
      axisLabel: { fontSize: 11 },
    },
    yAxis: { type: 'value' },
    series: [
      {
        data: aov.data.map((d) => d.value),
        type: 'bar',
        itemStyle: { color: '#10b981' },
      },
    ],
  };

  function downloadCSV() {
    const headers = ['Date', 'Revenue', 'AOV'];
    const rows = revenue!.data.map((d, i) => [
      d.date,
      d.value.toFixed(2),
      aov!.data[i]?.value.toFixed(2) ?? '',
    ]);
    const csv = [headers, ...rows].map((r) => r.join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'shopify-sales.csv';
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white border-b border-gray-200 px-6 py-3">
        <Link
          href="/dashboards"
          className="text-sm text-blue-600 hover:underline"
        >
          ← Back to Dashboards
        </Link>
      </nav>

      <main className="max-w-7xl mx-auto px-6 py-8">
        <div className="flex justify-between items-start mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              Shopify Sales Overview
            </h1>
            <p className="text-xs text-gray-400 mt-1">
              Powered by Metrics Service · revenue_by_day {revenue.version}
            </p>
          </div>
          <button
            onClick={downloadCSV}
            className="px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700"
          >
            Download CSV
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <KpiCard
            label="Today's Revenue"
            value={`$${todayRevenue.toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
          />
          <KpiCard
            label="30-Day Total"
            value={`$${totalRevenue.toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
          />
          <KpiCard label="Avg AOV" value={`$${avgAov.toFixed(2)}`} />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="bg-white p-4 rounded-lg border border-gray-200">
            <ReactECharts option={trendOption} style={{ height: 300 }} />
          </div>
          <div className="bg-white p-4 rounded-lg border border-gray-200">
            <ReactECharts option={aovOption} style={{ height: 300 }} />
          </div>
        </div>
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