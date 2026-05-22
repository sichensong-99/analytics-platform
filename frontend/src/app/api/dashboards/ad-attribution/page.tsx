'use client';

import { useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import Link from 'next/link';

const ReactECharts = dynamic(() => import('echarts-for-react'), { ssr: false });

function getDateRange() {
  const end = new Date();
  const start = new Date();
  start.setDate(start.getDate() - 13);
  return {
    start: start.toISOString().slice(0, 10),
    end: end.toISOString().slice(0, 10),
  };
}

interface RoasResponse {
  data: { channel: string; value: number }[];
}

interface SpendResponse {
  data: { date: string; channel: string; value: number }[];
}

export default function AdAttributionPage() {
  const [roas, setRoas] = useState<RoasResponse | null>(null);
  const [spend, setSpend] = useState<SpendResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const { start, end } = getDateRange();
    Promise.all([
      fetch(
        `/api/metrics/roas_by_channel?start_date=${start}&end_date=${end}`,
      ).then((r) => r.json()),
      fetch(
        `/api/metrics/ad_spend_by_day?start_date=${start}&end_date=${end}`,
      ).then((r) => r.json()),
    ])
      .then(([r, s]) => {
        if (r.error || s.error) {
          setError(r.error || s.error);
        } else {
          setRoas(r);
          setSpend(s);
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

  if (error || !roas || !spend) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="bg-white p-6 rounded border border-red-200">
          <p className="text-red-600 font-semibold mb-2">Error</p>
          <p className="text-sm text-gray-600">{error}</p>
        </div>
      </div>
    );
  }

  const channelOption = {
    title: { text: 'ROAS by Channel', textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'axis' },
    grid: { left: 50, right: 20, top: 50, bottom: 30 },
    xAxis: { type: 'category', data: roas.data.map((c) => c.channel) },
    yAxis: { type: 'value' },
    series: [
      {
        type: 'bar',
        data: roas.data.map((c) => c.value),
        itemStyle: { color: '#8b5cf6' },
      },
    ],
  };

  // Group spend by date and channel
  const dates = Array.from(new Set(spend.data.map((d) => d.date))).sort();
  const channels = Array.from(new Set(spend.data.map((d) => d.channel)));
  const trendOption = {
    title: { text: 'Ad Spend Trend', textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'axis' },
    legend: { top: 25 },
    grid: { left: 50, right: 20, top: 70, bottom: 30 },
    xAxis: { type: 'category', data: dates.map((d) => d.slice(5)) },
    yAxis: { type: 'value' },
    series: channels.map((ch) => ({
      name: ch,
      type: 'line',
      smooth: true,
      data: dates.map((d) => {
        const row = spend.data.find((s) => s.date === d && s.channel === ch);
        return row ? row.value : 0;
      }),
    })),
  };

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
        <h1 className="text-2xl font-bold text-gray-900 mb-2">
          Ad Attribution (Triple Whale)
        </h1>
        <p className="text-xs text-gray-400 mb-6">
          Powered by Metrics Service
        </p>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
          <div className="bg-white p-4 rounded-lg border border-gray-200">
            <ReactECharts option={channelOption} style={{ height: 300 }} />
          </div>
          <div className="bg-white p-4 rounded-lg border border-gray-200">
            <ReactECharts option={trendOption} style={{ height: 300 }} />
          </div>
        </div>

        <div className="bg-white p-4 rounded-lg border border-gray-200">
          <h3 className="font-semibold text-gray-900 mb-4">
            Channel Performance
          </h3>
          <table className="w-full text-sm">
            <thead className="text-left text-gray-500 border-b">
              <tr>
                <th className="pb-2 font-medium">Channel</th>
                <th className="pb-2 font-medium">ROAS</th>
              </tr>
            </thead>
            <tbody>
              {roas.data.map((c) => (
                <tr key={c.channel} className="border-b last:border-0">
                  <td className="py-2 text-gray-900">{c.channel}</td>
                  <td className="py-2 font-medium">{c.value.toFixed(2)}x</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </main>
    </div>
  );
}