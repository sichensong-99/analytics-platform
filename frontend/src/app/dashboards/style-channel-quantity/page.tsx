'use client';

import { useEffect, useState, useMemo } from 'react';
import dynamic from 'next/dynamic';
import Link from 'next/link';

const ReactECharts = dynamic(() => import('echarts-for-react'), { ssr: false });

// ============================================================
// Filter option catalogs
// Values verified against dim_channel / dim_product.
// Phase 2C will fetch these from /dimensions endpoints dynamically.
// ============================================================
const CHANNEL_OPTIONS = [
  { source: 'google-ads', group: 'Paid Search' },
  { source: 'facebook-ads', group: 'Paid Social' },
  { source: 'pinterest-ads', group: 'Paid Social' },
  { source: 'bing', group: 'Paid Search' },
  { source: 'klaviyo', group: 'Email' },
  { source: 'attentive', group: 'SMS' },
  { source: 'impact', group: 'Affiliate' },
  { source: 'organic_and_social', group: 'Organic' },
  { source: 'Direct', group: 'Direct' },
];

const SEASON_OPTIONS = ['F25', 'BAS', 'S25', 'S26', 'BAS-DIS', 'F24'];

const STYLE_OPTIONS = [
  'T5FL0A29PRT',
  'T5FLL801RT',
  'TBASMS40SRT',
  'T5FLL803RT',
  'T5FM9002RT',
  'TMBAS9589RT',
  'SILVERTOTE',
  'PACKBAG',
];

// Default range — Slice 1 TW-overlap window
function defaultDateRange() {
  return { start: '2025-07-01', end: '2025-07-27' };
}

interface Row {
  iso_year: number;
  iso_week: number;
  vend_id: string;
  item_description: string;
  season: string;
  channel_source: string;

  // Current API field
  channel_group?: string;

  // Backward compatibility if API still returns the older alias
  legacy_channel_group?: string;

  value: number;
}

interface MetricResponse {
  metric_id: string;
  name: string;
  version: string;
  unit: string;
  params: Record<string, unknown>;
  data: Row[];
}

function csvEscape(value: unknown): string {
  if (value === null || value === undefined) return '';
  const s = String(value);
  return `"${s.replace(/"/g, '""')}"`;
}

function getChannelGroup(row: Row): string {
  return row.channel_group ?? row.legacy_channel_group ?? '';
}

export default function StyleChannelQuantityPage() {
  // === Filter state ===
  const [startDate, setStartDate] = useState(defaultDateRange().start);
  const [endDate, setEndDate] = useState(defaultDateRange().end);
  const [selectedChannels, setSelectedChannels] = useState<string[]>([]);
  const [selectedSeasons, setSelectedSeasons] = useState<string[]>([]);
  const [selectedStyles, setSelectedStyles] = useState<string[]>([]);

  // === Data state ===
  const [resp, setResp] = useState<MetricResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // === Fetch on any filter change ===
  useEffect(() => {
    let cancelled = false;

    async function loadMetric() {
      setLoading(true);
      setError('');

      const qs = new URLSearchParams();
      qs.append('start_date', startDate);
      qs.append('end_date', endDate);

      selectedChannels.forEach((c) => qs.append('channels', c));
      selectedSeasons.forEach((s) => qs.append('seasons', s));
      selectedStyles.forEach((st) => qs.append('styles', st));

      try {
        const r = await fetch(
          `/api/metrics/quantity_by_style_channel_week?${qs.toString()}`,
        );

        const d = await r.json();

        if (!r.ok) {
          throw new Error(d.error ?? d.detail ?? `HTTP ${r.status}`);
        }

        if (d.error) {
          throw new Error(d.error);
        }

        if (!cancelled) {
          setResp(d);
          setLoading(false);
        }
      } catch (e) {
        if (!cancelled) {
          setResp(null);
          setError(e instanceof Error ? e.message : String(e));
          setLoading(false);
        }
      }
    }

    loadMetric();

    return () => {
      cancelled = true;
    };
  }, [startDate, endDate, selectedChannels, selectedSeasons, selectedStyles]);

  const rows = resp?.data ?? [];

  // === KPIs ===
  const kpi = useMemo(() => {
    const totalQty = rows.reduce((s, r) => s + r.value, 0);

    return {
      totalQty,
      nStyles: new Set(rows.map((r) => r.vend_id)).size,
      nChannels: new Set(rows.map((r) => r.channel_source)).size,
      nWeeks: new Set(rows.map((r) => `${r.iso_year}-W${r.iso_week}`)).size,
    };
  }, [rows]);

  // === Line chart: x = ISO weeks, one line per channel ===
  const lineOption = useMemo(() => {
    const weekLabels = Array.from(
      new Set(
        rows.map(
          (r) => `${r.iso_year}-W${String(r.iso_week).padStart(2, '0')}`,
        ),
      ),
    ).sort();

    const channels = Array.from(
      new Set(rows.map((r) => r.channel_source)),
    ).sort();

    const series = channels.map((ch) => {
      const data = weekLabels.map((wl) => {
        const [y, w] = wl.split('-W');

        return rows
          .filter(
            (r) =>
              r.channel_source === ch &&
              r.iso_year === Number(y) &&
              r.iso_week === Number(w),
          )
          .reduce((s, r) => s + r.value, 0);
      });

      return {
        name: ch,
        type: 'line',
        smooth: true,
        data,
      };
    });

    return {
      title: {
        text: 'Quantity by Channel x Week',
        textStyle: { fontSize: 14 },
      },
      tooltip: { trigger: 'axis' },
      legend: { type: 'scroll', bottom: 0 },
      grid: { left: 60, right: 20, top: 50, bottom: 50 },
      xAxis: {
        type: 'category',
        data: weekLabels,
        axisLabel: { fontSize: 11 },
      },
      yAxis: { type: 'value', name: 'Units' },
      series,
    };
  }, [rows]);

  // === Matrix: style rows x channel columns, summed across weeks ===
  const matrix = useMemo(() => {
    const channels = Array.from(
      new Set(rows.map((r) => r.channel_source)),
    ).sort();

    const styleMap = new Map<
      string,
      {
        item: string;
        season: string;
        cells: Record<string, number>;
        total: number;
      }
    >();

    for (const r of rows) {
      if (!styleMap.has(r.vend_id)) {
        styleMap.set(r.vend_id, {
          item: r.item_description,
          season: r.season,
          cells: {},
          total: 0,
        });
      }

      const e = styleMap.get(r.vend_id)!;
      e.cells[r.channel_source] = (e.cells[r.channel_source] ?? 0) + r.value;
      e.total += r.value;
    }

    const styleRows = Array.from(styleMap.entries())
      .map(([vend_id, e]) => ({ vend_id, ...e }))
      .sort((a, b) => b.total - a.total);

    return { channels, styleRows };
  }, [rows]);

  function downloadCSV() {
    if (rows.length === 0) return;

    const headers = [
      'iso_year',
      'iso_week',
      'vend_id',
      'item_description',
      'season',
      'channel_source',
      'channel_group',
      'quantity',
    ];

    const lines = [headers.join(',')];

    for (const r of rows) {
      lines.push(
        [
          r.iso_year,
          r.iso_week,
          csvEscape(r.vend_id),
          csvEscape(r.item_description),
          csvEscape(r.season),
          csvEscape(r.channel_source),
          csvEscape(getChannelGroup(r)),
          r.value,
        ].join(','),
      );
    }

    const csv = lines.join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);

    const a = document.createElement('a');
    a.href = url;
    a.download = `style-channel-quantity-${startDate}-to-${endDate}.csv`;
    a.click();

    URL.revokeObjectURL(url);
  }

  function toggleItem(
    arr: string[],
    item: string,
    setter: (a: string[]) => void,
  ) {
    if (arr.includes(item)) {
      setter(arr.filter((x) => x !== item));
    } else {
      setter([...arr, item]);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white border-b border-gray-200 px-6 py-3">
        <Link href="/dashboards" className="text-sm text-blue-600 hover:underline">
          Back to Dashboards
        </Link>
      </nav>

      <main className="max-w-7xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="flex justify-between items-start mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              Style x Channel x Week - Quantity
            </h1>

            <p className="text-xs text-gray-400 mt-1">
              {resp
                ? `Powered by Metrics Service - ${resp.metric_id} ${resp.version}`
                : 'Loading metric definition...'}
            </p>

            <p className="text-xs text-gray-500 mt-1">
              Migrated from PBI Style_selling_df - TW channel taxonomy with
              channel_group roll-up
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

          <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Start Date
              </label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="w-full px-2 py-1 text-sm border border-gray-300 rounded"
              />

              <label className="block text-xs font-medium text-gray-600 mt-2 mb-1">
                End Date
              </label>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="w-full px-2 py-1 text-sm border border-gray-300 rounded"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Channels (TW) - empty = all
              </label>

              <div className="max-h-32 overflow-y-auto border border-gray-200 rounded p-2 text-sm">
                {CHANNEL_OPTIONS.map((c) => (
                  <label key={c.source} className="flex items-center gap-2 py-0.5">
                    <input
                      type="checkbox"
                      checked={selectedChannels.includes(c.source)}
                      onChange={() =>
                        toggleItem(selectedChannels, c.source, setSelectedChannels)
                      }
                    />
                    <span>
                      {c.source}
                      <span className="text-gray-400 text-xs ml-1">
                        ({c.group})
                      </span>
                    </span>
                  </label>
                ))}
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Seasons - empty = all
              </label>

              <div className="max-h-32 overflow-y-auto border border-gray-200 rounded p-2 text-sm">
                {SEASON_OPTIONS.map((s) => (
                  <label key={s} className="flex items-center gap-2 py-0.5">
                    <input
                      type="checkbox"
                      checked={selectedSeasons.includes(s)}
                      onChange={() =>
                        toggleItem(selectedSeasons, s, setSelectedSeasons)
                      }
                    />
                    <span>{s}</span>
                  </label>
                ))}
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Styles (vend_id) - empty = all
              </label>

              <div className="max-h-32 overflow-y-auto border border-gray-200 rounded p-2 text-sm">
                {STYLE_OPTIONS.map((st) => (
                  <label key={st} className="flex items-center gap-2 py-0.5">
                    <input
                      type="checkbox"
                      checked={selectedStyles.includes(st)}
                      onChange={() =>
                        toggleItem(selectedStyles, st, setSelectedStyles)
                      }
                    />
                    <span>{st}</span>
                  </label>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Status */}
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
              <KpiCard label="Total Units" value={kpi.totalQty.toLocaleString()} />
              <KpiCard label="Styles" value={kpi.nStyles.toString()} />
              <KpiCard label="Channels" value={kpi.nChannels.toString()} />
              <KpiCard label="Weeks" value={kpi.nWeeks.toString()} />
            </div>

            <div className="grid grid-cols-1 gap-4">
              <div className="bg-white p-4 rounded-lg border border-gray-200">
                <ReactECharts option={lineOption} style={{ height: 360 }} />
              </div>

              <div className="bg-white p-4 rounded-lg border border-gray-200 overflow-x-auto">
                <h3 className="text-sm font-semibold text-gray-700 mb-3">
                  Style x Channel Matrix (summed across selected weeks)
                </h3>

                {matrix.styleRows.length === 0 ? (
                  <p className="text-sm text-gray-500">
                    No data for the selected filters.
                  </p>
                ) : (
                  <table className="min-w-full text-sm">
                    <thead>
                      <tr className="border-b border-gray-200 bg-gray-50">
                        <th className="text-left px-2 py-2 font-medium">
                          vend_id
                        </th>
                        <th className="text-left px-2 py-2 font-medium">
                          Item
                        </th>
                        <th className="text-left px-2 py-2 font-medium">
                          Season
                        </th>

                        {matrix.channels.map((ch) => (
                          <th
                            key={ch}
                            className="text-right px-2 py-2 font-medium whitespace-nowrap"
                          >
                            {ch}
                          </th>
                        ))}

                        <th className="text-right px-2 py-2 font-medium bg-blue-50">
                          Total
                        </th>
                      </tr>
                    </thead>

                    <tbody>
                      {matrix.styleRows.map((sr) => (
                        <tr
                          key={sr.vend_id}
                          className="border-b border-gray-100 hover:bg-gray-50"
                        >
                          <td className="px-2 py-1.5 font-mono text-xs">
                            {sr.vend_id}
                          </td>
                          <td className="px-2 py-1.5 text-xs text-gray-600">
                            {sr.item}
                          </td>
                          <td className="px-2 py-1.5 text-xs">{sr.season}</td>

                          {matrix.channels.map((ch) => (
                            <td
                              key={ch}
                              className="px-2 py-1.5 text-right tabular-nums"
                            >
                              {(sr.cells[ch] ?? 0).toLocaleString()}
                            </td>
                          ))}

                          <td className="px-2 py-1.5 text-right tabular-nums font-semibold bg-blue-50">
                            {sr.total.toLocaleString()}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
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