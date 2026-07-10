'use client';

import { useEffect, useState, useMemo } from 'react';
import dynamic from 'next/dynamic';
import Link from 'next/link';

const ReactECharts = dynamic(() => import('echarts-for-react'), { ssr: false });

// Display-only pagination for the matrix table. CSV always exports all matching rows.
const PAGE_SIZE = 25;

// First date with platform data (used by the "All" quick-range preset).
const DATA_START = '2025-07-01';

function defaultDateRange() {
  return { start: '2025-07-01', end: '2025-07-27' };
}

// Format a Date as YYYY-MM-DD using LOCAL parts (avoids the UTC off-by-one
// that `toISOString().slice(0,10)` can produce near midnight).
function fmtLocal(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

// Quick-range presets — one click instead of flipping the date calendars.
const PRESETS: { label: string; range: () => { start: string; end: string } }[] = [
  {
    label: 'Last 7 days',
    range: () => {
      const e = new Date();
      const s = new Date();
      s.setDate(s.getDate() - 6);
      return { start: fmtLocal(s), end: fmtLocal(e) };
    },
  },
  {
    label: 'Last 4 weeks',
    range: () => {
      const e = new Date();
      const s = new Date();
      s.setDate(s.getDate() - 27);
      return { start: fmtLocal(s), end: fmtLocal(e) };
    },
  },
  {
    label: 'This month',
    range: () => {
      const e = new Date();
      const s = new Date(e.getFullYear(), e.getMonth(), 1);
      return { start: fmtLocal(s), end: fmtLocal(e) };
    },
  },
  {
    label: 'Last 90 days',
    range: () => {
      const e = new Date();
      const s = new Date();
      s.setDate(s.getDate() - 89);
      return { start: fmtLocal(s), end: fmtLocal(e) };
    },
  },
  {
    label: 'All',
    range: () => ({ start: DATA_START, end: fmtLocal(new Date()) }),
  },
];

// Remember the user's last-used date range across navigation + refresh.
const STORAGE_KEY = 'styleChannelQuantity.dateRange.v1';

function loadSavedRange(): { start: string; end: string } {
  if (typeof window === 'undefined') return defaultDateRange();
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const p = JSON.parse(raw);
      if (typeof p?.start === 'string' && typeof p?.end === 'string') {
        return { start: p.start, end: p.end };
      }
    }
  } catch {
    /* ignore corrupt or blocked storage */
  }
  return defaultDateRange();
}

interface Row {
  iso_year: number;
  iso_week: number;
  vend_id: string;
  item_description: string;
  season: string;
  channel_source: string;
  channel_group?: string;
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

// Rows returned by the SKU-grain units + dollar export metric.
interface SkuDollarRow {
  sku: string;
  channel: string;
  week_ending_date: string;
  units_sold: number;
  dollar_sales: number;
}

// Which channel taxonomy drives the chart + matrix pivot.
type ChannelDim = 'channel_source' | 'channel_group';

function csvEscape(value: unknown): string {
  if (value === null || value === undefined) return '';
  const s = String(value);
  return `"${s.replace(/"/g, '""')}"`;
}

function getChannelGroup(row: Row): string {
  return row.channel_group ?? row.legacy_channel_group ?? '';
}

// "2026-06-14" (or with a time suffix) -> "6/14/2026" to match the stakeholder CSV format.
function toUSDate(iso: string): string {
  const m = String(iso).slice(0, 10).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!m) return String(iso);
  return `${Number(m[2])}/${Number(m[3])}/${m[1]}`;
}

export default function StyleChannelQuantityPage() {
  const [startDate, setStartDate] = useState(defaultDateRange().start);
  const [endDate, setEndDate] = useState(defaultDateRange().end);

  // True once we've restored the saved range from localStorage. We gate the
  // data fetch on this so we don't fire one request with the default range and
  // then immediately a second with the restored range.
  const [hydrated, setHydrated] = useState(false);

  const [selectedChannels, setSelectedChannels] = useState<string[]>([]);
  const [selectedSeasons, setSelectedSeasons] = useState<string[]>([]);
  const [selectedStyles, setSelectedStyles] = useState<string[]>([]);

  // search-within-filter text
  const [channelSearch, setChannelSearch] = useState('');
  const [seasonSearch, setSeasonSearch] = useState('');
  const [styleSearch, setStyleSearch] = useState('');

  const [resp, setResp] = useState<MetricResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [page, setPage] = useState(0);

  // stakeholder's SKU + dollar export (fetched fresh at SKU grain from the metric layer).
  const [exporting, setExporting] = useState(false);

  // Channel taxonomy for the on-screen chart + matrix. channel_source is the
  // granular Triple Whale source; channel_group is the dimension's roll-up
  // (Paid Search / Paid Social / Email / ...). The CSV exports always include
  // both regardless of this toggle. Switch the initial value to 'channel_group'
  // if you'd rather the cleaner grouped view be the default (e.g. for demos).
  const [channelDim, setChannelDim] = useState<ChannelDim>('channel_source');

  // Restore the last-used date range on mount.
  useEffect(() => {
    const saved = loadSavedRange();
    setStartDate(saved.start);
    setEndDate(saved.end);
    setHydrated(true);
  }, []);

  // Persist the date range whenever it changes (after hydration).
  useEffect(() => {
    if (!hydrated) return;
    try {
      window.localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ start: startDate, end: endDate }),
      );
    } catch {
      /* ignore */
    }
  }, [startDate, endDate, hydrated]);

  // Fetch the FULL date-range dataset (no dimension filters) — filtering is done client-side
  // so filter options reflect the REAL data, not a hardcoded list, and never collapse.
  useEffect(() => {
    if (!hydrated) return;
    let cancelled = false;

    async function loadMetric() {
      setLoading(true);
      setError('');

      const qs = new URLSearchParams();
      qs.append('start_date', startDate);
      qs.append('end_date', endDate);

      try {
        const r = await fetch(
          `/api/metrics/quantity_by_style_channel_week?${qs.toString()}`,
        );
        const d = await r.json();

        if (!r.ok) throw new Error(d.error ?? d.detail ?? `HTTP ${r.status}`);
        if (d.error) throw new Error(d.error);

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
  }, [startDate, endDate, hydrated]);

  const allRows = resp?.data ?? [];

  // ---- Dynamic filter options derived from the real data (was hardcoded) ----
  const channelOptions = useMemo(() => {
    const m = new Map<string, string>(); // channel_source -> channel_group
    for (const r of allRows) if (r.channel_source) m.set(r.channel_source, getChannelGroup(r));
    return Array.from(m.entries())
      .map(([source, group]) => ({ source, group }))
      .sort((a, b) => a.source.localeCompare(b.source));
  }, [allRows]);

  const seasonOptions = useMemo(
    () => Array.from(new Set(allRows.map((r) => r.season).filter(Boolean))).sort(),
    [allRows],
  );

  const styleOptions = useMemo(() => {
    const m = new Map<string, string>(); // vend_id -> item_description
    for (const r of allRows) if (r.vend_id) m.set(r.vend_id, r.item_description ?? '');
    return Array.from(m.entries())
      .map(([vend_id, item]) => ({ vend_id, item }))
      .sort((a, b) => a.vend_id.localeCompare(b.vend_id));
  }, [allRows]);

  // ---- Client-side filtering for display (empty selection = all) ----
  // Note: the Channels filter always works on the granular channel_source, independent
  // of the chart/matrix view toggle (you filter on the source, view it either way).
  const rows = useMemo(
    () =>
      allRows.filter(
        (r) =>
          (selectedChannels.length === 0 || selectedChannels.includes(r.channel_source)) &&
          (selectedSeasons.length === 0 || selectedSeasons.includes(r.season)) &&
          (selectedStyles.length === 0 || selectedStyles.includes(r.vend_id)),
      ),
    [allRows, selectedChannels, selectedSeasons, selectedStyles],
  );

  // New result or filter change -> back to first page.
  useEffect(() => {
    setPage(0);
  }, [rows.length, resp]);

  // The active channel label for a row, per the chart/matrix toggle.
  const dimValue = (r: Row) =>
    channelDim === 'channel_group' ? (getChannelGroup(r) || '(ungrouped)') : r.channel_source;

  const kpi = useMemo(() => {
    const totalQty = rows.reduce((s, r) => s + r.value, 0);
    return {
      totalQty,
      nStyles: new Set(rows.map((r) => r.vend_id)).size,
      nChannels: new Set(rows.map(dimValue)).size,
      nWeeks: new Set(rows.map((r) => `${r.iso_year}-W${r.iso_week}`)).size,
    };
  }, [rows, channelDim]);

  const lineOption = useMemo(() => {
    const weekLabels = Array.from(
      new Set(
        rows.map((r) => `${r.iso_year}-W${String(r.iso_week).padStart(2, '0')}`),
      ),
    ).sort();

    const channels = Array.from(new Set(rows.map(dimValue))).sort();

    const series = channels.map((ch) => {
      const data = weekLabels.map((wl) => {
        const [y, w] = wl.split('-W');
        return rows
          .filter(
            (r) =>
              dimValue(r) === ch &&
              r.iso_year === Number(y) &&
              r.iso_week === Number(w),
          )
          .reduce((s, r) => s + r.value, 0);
      });
      return { name: ch, type: 'line', smooth: true, data };
    });

    return {
      title: {
        text:
          channelDim === 'channel_group'
            ? 'Quantity by Channel Group x Week'
            : 'Quantity by Channel x Week',
        textStyle: { fontSize: 14 },
      },
      tooltip: { trigger: 'axis' },
      legend: { type: 'scroll', bottom: 0 },
      grid: { left: 60, right: 20, top: 50, bottom: 50 },
      xAxis: { type: 'category', data: weekLabels, axisLabel: { fontSize: 11 } },
      yAxis: { type: 'value', name: 'Units' },
      series,
    };
  }, [rows, channelDim]);

  const matrix = useMemo(() => {
    const channels = Array.from(new Set(rows.map(dimValue))).sort();

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
      const key = dimValue(r);
      e.cells[key] = (e.cells[key] ?? 0) + r.value;
      e.total += r.value;
    }

    const styleRows = Array.from(styleMap.entries())
      .map(([vend_id, e]) => ({ vend_id, ...e }))
      .sort((a, b) => b.total - a.total);

    return { channels, styleRows };
  }, [rows, channelDim]);

  // Pagination (display only)
  const pageCount = Math.max(1, Math.ceil(matrix.styleRows.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  const pagedRows = matrix.styleRows.slice(
    safePage * PAGE_SIZE,
    safePage * PAGE_SIZE + PAGE_SIZE,
  );
  const firstShown = matrix.styleRows.length === 0 ? 0 : safePage * PAGE_SIZE + 1;
  const lastShown = safePage * PAGE_SIZE + pagedRows.length;

  // Style-level export. Always includes BOTH channel_source and channel_group,
  // regardless of the on-screen view toggle.
  function downloadCSV() {
    if (rows.length === 0) return;

    const headers = [
      'iso_year', 'iso_week', 'vend_id', 'item_description', 'season',
      'channel_source', 'channel_group', 'quantity',
    ];

    const lines = [headers.join(',')];
    for (const r of rows) {
      lines.push(
        [
          r.iso_year, r.iso_week, csvEscape(r.vend_id), csvEscape(r.item_description),
          csvEscape(r.season), csvEscape(r.channel_source), csvEscape(getChannelGroup(r)), r.value,
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

  // stakeholder's export: SKU x channel x week_ending_date x units_sold x dollar_sales.
  // Fetched fresh at SKU grain from the metric layer (the on-screen tables are style-level).
  // Intentionally TW channel only — do not add channel_group here.
  async function downloadSkuDollarCSV() {
    setExporting(true);
    try {
      const qs = new URLSearchParams();
      qs.append('start_date', startDate);
      qs.append('end_date', endDate);

      const r = await fetch(
        `/api/metrics/units_dollars_by_sku_channel_week?${qs.toString()}`,
      );
      const d = await r.json();
      if (!r.ok || d.error) {
        throw new Error(d.error ?? d.detail ?? `HTTP ${r.status}`);
      }

      const data: SkuDollarRow[] = d.data ?? [];
      if (data.length === 0) {
        alert('No SKU-level sales for the selected date range.');
        return;
      }

      const headers = ['sku', 'channel', 'week_ending_date', 'units_sold', 'dollar_sales'];
      const lines = [headers.join(',')];
      for (const row of data) {
        lines.push(
          [
            csvEscape(row.sku),
            csvEscape(row.channel),
            csvEscape(toUSDate(row.week_ending_date)),
            row.units_sold,
            row.dollar_sales,
          ].join(','),
        );
      }

      const csv = lines.join('\n');
      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `sku-channel-units-dollars-${startDate}-to-${endDate}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert(`Export failed: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setExporting(false);
    }
  }

  function toggleItem(arr: string[], item: string, setter: (a: string[]) => void) {
    if (arr.includes(item)) setter(arr.filter((x) => x !== item));
    else setter([...arr, item]);
  }

  function clearFilters() {
    setSelectedChannels([]);
    setSelectedSeasons([]);
    setSelectedStyles([]);
    setChannelSearch('');
    setSeasonSearch('');
    setStyleSearch('');
  }

  // option lists filtered by search text
  const shownChannels = channelOptions.filter((c) =>
    c.source.toLowerCase().includes(channelSearch.toLowerCase()),
  );
  const shownSeasons = seasonOptions.filter((s) =>
    s.toLowerCase().includes(seasonSearch.toLowerCase()),
  );
  const shownStyles = styleOptions.filter((s) =>
    `${s.vend_id} ${s.item}`.toLowerCase().includes(styleSearch.toLowerCase()),
  );

  const anyFilter =
    selectedChannels.length + selectedSeasons.length + selectedStyles.length > 0;

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
              Style x Channel x Week - Quantity
            </h1>
            <p className="text-xs text-gray-400 mt-1">
              {resp
                ? `Powered by Metrics Service - ${resp.metric_id} ${resp.version}`
                : 'Loading metric definition...'}
            </p>
            <p className="text-xs text-gray-500 mt-1">
              Migrated from PBI Style_selling_df - TW channel taxonomy with channel_group roll-up
            </p>
            <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1 mt-2 inline-block">
            Coverage from Jul 2025 · excludes replacement & EXC orders and line-level refunds
            </p>
          </div>

          <div className="flex flex-col gap-2 items-end">
            <button
              onClick={downloadCSV}
              disabled={rows.length === 0}
              className="px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
            >
              Download CSV (style-level)
            </button>
            <button
              onClick={downloadSkuDollarCSV}
              disabled={exporting}
              className="px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
            >
              {exporting ? 'Preparing…' : 'Download CSV (SKU-level)'}
            </button>
          </div>
        </div>

        <div className="bg-white p-4 rounded-lg border border-gray-200 mb-6">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-gray-700">Filters</h3>
            <button
              onClick={clearFilters}
              disabled={!anyFilter}
              className="text-xs px-2 py-1 border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-40"
            >
              Clear filters
            </button>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
            {/* Dates */}
            <div>

              <label className="block text-xs font-medium text-gray-600 mb-1">Start Date</label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="w-full px-2 py-1 text-sm border border-gray-300 rounded"
              />
              <label className="block text-xs font-medium text-gray-600 mt-2 mb-1">End Date</label>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="w-full px-2 py-1 text-sm border border-gray-300 rounded"
              />
            </div>

            {/* Channels */}
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Channels{' '}
                {selectedChannels.length > 0 && (
                  <span className="text-blue-600">({selectedChannels.length} selected)</span>
                )}
                {selectedChannels.length === 0 && <span className="text-gray-400">(all)</span>}
              </label>
              <input
                value={channelSearch}
                onChange={(e) => setChannelSearch(e.target.value)}
                placeholder="Search channels…"
                className="w-full mb-1 px-2 py-1 text-xs border border-gray-300 rounded"
              />
              <div className="max-h-32 overflow-y-auto border border-gray-200 rounded p-2 text-sm">
                {channelOptions.length === 0 ? (
                  <p className="text-xs text-gray-400">No data loaded.</p>
                ) : shownChannels.length === 0 ? (
                  <p className="text-xs text-gray-400">No match.</p>
                ) : (
                  shownChannels.map((c) => (
                    <label key={c.source} className="flex items-center gap-2 py-0.5">
                      <input
                        type="checkbox"
                        checked={selectedChannels.includes(c.source)}
                        onChange={() => toggleItem(selectedChannels, c.source, setSelectedChannels)}
                      />
                      <span>
                        {c.source}
                        {c.group && <span className="text-gray-400 text-xs ml-1">({c.group})</span>}
                      </span>
                    </label>
                  ))
                )}
              </div>
            </div>

            {/* Seasons */}
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Seasons{' '}
                {selectedSeasons.length > 0 && (
                  <span className="text-blue-600">({selectedSeasons.length} selected)</span>
                )}
                {selectedSeasons.length === 0 && <span className="text-gray-400">(all)</span>}
              </label>
              <input
                value={seasonSearch}
                onChange={(e) => setSeasonSearch(e.target.value)}
                placeholder="Search seasons…"
                className="w-full mb-1 px-2 py-1 text-xs border border-gray-300 rounded"
              />
              <div className="max-h-32 overflow-y-auto border border-gray-200 rounded p-2 text-sm">
                {seasonOptions.length === 0 ? (
                  <p className="text-xs text-gray-400">No data loaded.</p>
                ) : shownSeasons.length === 0 ? (
                  <p className="text-xs text-gray-400">No match.</p>
                ) : (
                  shownSeasons.map((s) => (
                    <label key={s} className="flex items-center gap-2 py-0.5">
                      <input
                        type="checkbox"
                        checked={selectedSeasons.includes(s)}
                        onChange={() => toggleItem(selectedSeasons, s, setSelectedSeasons)}
                      />
                      <span>{s}</span>
                    </label>
                  ))
                )}
              </div>
            </div>

            {/* Styles */}
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Styles (vend_id){' '}
                {selectedStyles.length > 0 && (
                  <span className="text-blue-600">({selectedStyles.length} selected)</span>
                )}
                {selectedStyles.length === 0 && (
                  <span className="text-gray-400">({styleOptions.length} options)</span>
                )}
              </label>
              <input
                value={styleSearch}
                onChange={(e) => setStyleSearch(e.target.value)}
                placeholder="Search styles…"
                className="w-full mb-1 px-2 py-1 text-xs border border-gray-300 rounded"
              />
              <div className="max-h-32 overflow-y-auto border border-gray-200 rounded p-2 text-sm">
                {styleOptions.length === 0 ? (
                  <p className="text-xs text-gray-400">No data loaded.</p>
                ) : shownStyles.length === 0 ? (
                  <p className="text-xs text-gray-400">No match.</p>
                ) : (
                  shownStyles.map((s) => (
                    <label key={s.vend_id} className="flex items-center gap-2 py-0.5">
                      <input
                        type="checkbox"
                        checked={selectedStyles.includes(s.vend_id)}
                        onChange={() => toggleItem(selectedStyles, s.vend_id, setSelectedStyles)}
                      />
                      <span className="font-mono text-xs">{s.vend_id}</span>
                      {s.item && <span className="text-gray-400 text-xs truncate">{s.item}</span>}
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
              <KpiCard label="Total Units" value={kpi.totalQty.toLocaleString()} />
              <KpiCard label="Styles" value={kpi.nStyles.toString()} />
              <KpiCard
                label={channelDim === 'channel_group' ? 'Channel Groups' : 'Channels'}
                value={kpi.nChannels.toString()}
              />
              <KpiCard label="Weeks" value={kpi.nWeeks.toString()} />
            </div>

            {/* Channel taxonomy toggle — re-pivots both the chart and the matrix. */}
            <div className="flex items-center gap-2 mb-4">
              <span className="text-xs font-medium text-gray-600">Channel view:</span>
              <div className="inline-flex rounded border border-gray-300 overflow-hidden text-xs">
                <button
                  onClick={() => setChannelDim('channel_source')}
                  className={`px-3 py-1 ${
                    channelDim === 'channel_source'
                      ? 'bg-blue-600 text-white'
                      : 'bg-white text-gray-700 hover:bg-gray-50'
                  }`}
                >
                  Channel (TW)
                </button>
                <button
                  onClick={() => setChannelDim('channel_group')}
                  className={`px-3 py-1 border-l border-gray-300 ${
                    channelDim === 'channel_group'
                      ? 'bg-blue-600 text-white'
                      : 'bg-white text-gray-700 hover:bg-gray-50'
                  }`}
                >
                  Channel Group
                </button>
              </div>
            </div>

            <div className="grid grid-cols-1 gap-4">
              <div className="bg-white p-4 rounded-lg border border-gray-200">
                <ReactECharts option={lineOption} style={{ height: 360 }} />
              </div>

              <div className="bg-white p-4 rounded-lg border border-gray-200">
                <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
                  <h3 className="text-sm font-semibold text-gray-700">
                    Style x {channelDim === 'channel_group' ? 'Channel Group' : 'Channel'} Matrix (summed across selected weeks)
                  </h3>
                  {matrix.styleRows.length > 0 && (
                    <span className="text-xs text-gray-400">
                      Showing styles {firstShown}-{lastShown} of {matrix.styleRows.length} · CSV downloads all rows matching the current filters
                    </span>
                  )}
                </div>

                <div className="overflow-x-auto">
                  {matrix.styleRows.length === 0 ? (
                    <p className="text-sm text-gray-500">No data for the selected filters.</p>
                  ) : (
                    <table className="min-w-full text-sm">
                      <thead>
                        <tr className="border-b border-gray-200 bg-gray-50">
                          <th className="text-left px-2 py-2 font-medium">vend_id</th>
                          <th className="text-left px-2 py-2 font-medium">Item</th>
                          <th className="text-left px-2 py-2 font-medium">Season</th>
                          {matrix.channels.map((ch) => (
                            <th key={ch} className="text-right px-2 py-2 font-medium whitespace-nowrap">
                              {ch}
                            </th>
                          ))}
                          <th className="text-right px-2 py-2 font-medium bg-blue-50">Total</th>
                        </tr>
                      </thead>
                      <tbody>
                        {pagedRows.map((sr) => (
                          <tr key={sr.vend_id} className="border-b border-gray-100 hover:bg-gray-50">
                            <td className="px-2 py-1.5 font-mono text-xs">{sr.vend_id}</td>
                            <td className="px-2 py-1.5 text-xs text-gray-600">{sr.item}</td>
                            <td className="px-2 py-1.5 text-xs">{sr.season}</td>
                            {matrix.channels.map((ch) => (
                              <td key={ch} className="px-2 py-1.5 text-right tabular-nums">
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

                {pageCount > 1 && (
                  <div className="flex items-center justify-between mt-4">
                    <button
                      onClick={() => setPage((p) => Math.max(0, p - 1))}
                      disabled={safePage === 0}
                      className="px-3 py-1 text-sm border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-40"
                    >
                      Prev
                    </button>
                    <span className="text-xs text-gray-500">
                      Page {safePage + 1} of {pageCount}
                    </span>
                    <button
                      onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
                      disabled={safePage >= pageCount - 1}
                      className="px-3 py-1 text-sm border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-40"
                    >
                      Next
                    </button>
                  </div>
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
