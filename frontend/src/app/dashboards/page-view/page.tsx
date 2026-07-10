/* eslint-disable @typescript-eslint/no-explicit-any */
// @ts-nocheck
"use client";

// ============================================================================
// Page View Dashboard  (replaces legacy Panoply "Page_view" PBI report)
//
// - Pick a date range + optional Category, see product-level rows, download CSV.
// - CSV download matches the legacy PBI export EXACTLY: same headers, same order,
//   NO date column, product-level totals.
// - Date range is remembered across refresh / navigation (localStorage).
// - Table auto-loads on open / refresh and whenever the date range changes.
// ============================================================================

import { useState, useMemo, useEffect, useRef } from "react";

type PageViewRow = {
  page: string;
  event_count: number;
  add_to_cart: number;
  unique_orders: number;
  unique_sold: number;
  net_sales: number;
  category: string;
  gender: string;
  descr: string;
  [channel: string]: string | number; // 15 个 channel 列
};

// ---- PBI column order + exact headers (left = display header, key = metric field) ----
const COLUMNS = [
  { header: "Page",             key: "page",             type: "text"  },
  { header: "Event_count",      key: "event_count",      type: "int"   },
  { header: "Add_to_cart",      key: "add_to_cart",      type: "int"   },
  { header: "Unique_orders",    key: "unique_orders",    type: "int"   },
  { header: "Unique_sold",      key: "unique_sold",      type: "int"   },
  { header: "Net_sales",        key: "net_sales",        type: "money" },
  { header: "Category",         key: "category",         type: "text"  },
  { header: "Gender",           key: "gender",           type: "text"  },
  { header: "Desc",             key: "descr",            type: "text"  },
  { header: "Email",            key: "email",            type: "int"   },
  { header: "Paid Search",      key: "paid_search",      type: "int"   },
  { header: "Paid Social",      key: "paid_social",      type: "int"   },
  { header: "Affiliates",       key: "affiliates",       type: "int"   },
  { header: "Organic Social",   key: "organic_social",   type: "int"   },
  { header: "Direct",           key: "direct",           type: "int"   },
  { header: "Organic search",   key: "organic_search",   type: "int"   },
  { header: "SMS",              key: "sms",              type: "int"   },
  { header: "Cross-network",    key: "cross_network",    type: "int"   },
  { header: "Referral",         key: "referral",         type: "int"   },
  { header: "Paid Shopping",    key: "paid_shopping",    type: "int"   },
  { header: "Organic Shopping", key: "organic_shopping", type: "int"   },
  { header: "Organic Video",    key: "organic_video",    type: "int"   },
  { header: "Paid Other",       key: "paid_other",       type: "int"   },
  { header: "Unassigned",       key: "unassigned",       type: "int"   },
];

// ---- Date range persistence (remember user's choice across refresh) ----
const STORAGE_KEY = "pageView.dateRange.v1";
const DEFAULT_START = "2025-07-01"; // both Shopify + GA4 complete from here

function todayISO() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate()
  ).padStart(2, "0")}`;
}

// Read saved range from localStorage. CLIENT-ONLY — never call during render.
function readSavedRange() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const p = JSON.parse(raw);
      if (typeof p?.start === "string" && typeof p?.end === "string") return p;
    }
  } catch {
    /* ignore corrupt or blocked storage */
  }
  return null;
}

// ============================================================================
// INTEGRATION POINT — calls the metrics API the same way the other dashboards do
// (GET /api/metrics/{name}?start_date=..&end_date=.., response keyed under .data)
// ============================================================================
async function fetchPageView(startDate: string, endDate: string) {
  const qs = new URLSearchParams();
  qs.append("start_date", startDate);
  qs.append("end_date", endDate);

  const r = await fetch(`/api/metrics/page_view_by_product?${qs.toString()}`);
  const d = await r.json();
  if (!r.ok || d.error) {
    throw new Error(d.error ?? d.detail ?? `HTTP ${r.status}`);
  }
  return d.data ?? [];
}

// ---- CSV helpers (RFC-4180: quote fields containing , " or newline) ----
function csvCell(v) {
  const s = v === null || v === undefined ? "" : String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export default function PageViewDashboard() {
  // SSR-stable initial values (no localStorage / today in the initializer ->
  // server and client first render produce identical HTML -> no hydration mismatch).
  const [startDate, setStartDate] = useState(DEFAULT_START);
  const [endDate, setEndDate]     = useState(DEFAULT_START);
  const [rows, setRows]           = useState<PageViewRow[]>([]);
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState("");
  const [category, setCategory]   = useState("ALL");
  const [loaded, setLoaded]       = useState(false);
  const [ready, setReady]         = useState(false); // client mounted + range restored

  // Only the most recent fetch is allowed to update state — guards against
  // StrictMode double-invoke and out-of-order responses from rapid date changes.
  const reqId = useRef(0);

  // 1) On mount (client only): restore the saved range, or fall back to defaults.
  useEffect(() => {
    const saved = readSavedRange();
    setStartDate(saved?.start ?? DEFAULT_START);
    setEndDate(saved?.end ?? todayISO());
    setReady(true);
  }, []);

  // 2) Persist the range whenever it changes — only after restore, so we never
  //    overwrite the saved value with the placeholder defaults on first paint.
  useEffect(() => {
    if (!ready) return;
    try {
      window.localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ start: startDate, end: endDate })
      );
    } catch {
      /* ignore */
    }
  }, [ready, startDate, endDate]);

  async function load() {
    if (!startDate || !endDate) return;
    const myId = ++reqId.current;
    setLoading(true);
    setError("");
    try {
      const data = await fetchPageView(startDate, endDate);
      if (myId !== reqId.current) return; // a newer request started — drop this result
      setRows(Array.isArray(data) ? (data as PageViewRow[]) : []);
      setCategory("ALL");
      setLoaded(true);
    } catch (e) {
      if (myId !== reqId.current) return;
      setError(e?.message || "Failed to load");
      setRows([]);
    } finally {
      if (myId === reqId.current) setLoading(false);
    }
  }

  // 3) Auto-load once the client is ready, and whenever the date range changes.
  useEffect(() => {
    if (!ready) return;
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, startDate, endDate]);

  const categories = useMemo(() => {
    const set = new Set(rows.map((r: PageViewRow) => r.category).filter(Boolean));
    return ["ALL", ...Array.from(set).sort()];
  }, [rows]);

  const filtered = useMemo(
    () => (category === "ALL" ? rows : rows.filter((r: PageViewRow) => r.category === category)),
    [rows, category]
  );

  function downloadCsv() {
    const header = COLUMNS.map((c) => c.header).join(",");
    const lines = filtered.map((r: PageViewRow) =>
      COLUMNS.map((c) => {
        let v = r[c.key];
        if (c.type === "money" && v !== null && v !== undefined) v = Number(v).toFixed(2);
        return csvCell(v);
      }).join(",")
    );
    const csv = [header, ...lines].join("\r\n");
    const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8;" }); // BOM for Excel
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download =
      `page_view_${startDate}_to_${endDate}` +
      (category !== "ALL" ? `_${category}` : "") + ".csv";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  const fmtInt = (v) => (v === null || v === undefined ? "" : Number(v).toLocaleString());
  const fmtMoney = (v) =>
    v === null || v === undefined ? "" : "$" + Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 });

  return (
    <div className="p-6 space-y-4">
      <nav className="border-b border-gray-200 pb-3">
        <a href="/dashboards" className="text-sm text-blue-600 hover:underline">← Back to Dashboards</a>
      </nav>
      <div>
        <h1 className="text-xl font-semibold">Page View by Product</h1>
      </div>

      {/* Controls */}
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col text-sm">
          <span className="text-gray-600">Start date</span>
          <input
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            className="border rounded px-2 py-1"
          />
        </label>
        <label className="flex flex-col text-sm">
          <span className="text-gray-600">End date</span>
          <input
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            className="border rounded px-2 py-1"
          />
        </label>

        <button
          onClick={load}
          disabled={loading}
          className="rounded bg-black text-white px-4 py-1.5 text-sm disabled:opacity-50"
        >
          {loading ? "Loading…" : "Load"}
        </button>

        <label className="flex flex-col text-sm">
          <span className="text-gray-600">Category</span>
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            disabled={!loaded}
            className="border rounded px-2 py-1 disabled:opacity-50"
          >
            {categories.map((c) => (
              <option key={c} value={c}>{c === "ALL" ? "All categories" : c}</option>
            ))}
          </select>
        </label>

        <button
          onClick={downloadCsv}
          disabled={!loaded || filtered.length === 0}
          className="rounded border px-4 py-1.5 text-sm disabled:opacity-50"
        >
          Download CSV
        </button>

        {loaded && (
          <span className="text-sm text-gray-500 ml-auto">
            {filtered.length.toLocaleString()} products
          </span>
        )}
      </div>

      {error && (
        <div className="text-sm text-red-600 border border-red-200 bg-red-50 rounded px-3 py-2">
          {error}
        </div>
      )}

      {/* Loading indicator (first load + manual reload) */}
      {loading && <p className="text-sm text-gray-400">Loading…</p>}

      {/* Table */}
      {loaded && !error && filtered.length > 0 && (
        <div className="overflow-auto border rounded max-h-[70vh]">
          <table className="text-sm border-collapse min-w-max">
            <thead className="sticky top-0 bg-gray-100">
              <tr>
                {COLUMNS.map((c) => (
                  <th
                    key={c.key}
                    className={`px-2 py-1 border-b font-medium whitespace-nowrap ${
                      c.type === "text" ? "text-left" : "text-right"
                    }`}
                  >
                    {c.header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((r: PageViewRow, i: number) => (
                <tr key={`${r.page}-${i}`} className="odd:bg-white even:bg-gray-50">
                  {COLUMNS.map((c) => (
                    <td
                      key={c.key}
                      className={`px-2 py-1 border-b whitespace-nowrap ${
                        c.type === "text" ? "text-left" : "text-right tabular-nums"
                      }`}
                    >
                      {c.type === "money" ? fmtMoney(r[c.key])
                        : c.type === "int" ? fmtInt(r[c.key])
                        : (r[c.key] ?? "")}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Loaded but no rows for this range */}
      {loaded && !error && !loading && filtered.length === 0 && (
        <p className="text-sm text-gray-400">No data for this date range.</p>
      )}

      {/* Before the first load finishes (brief) */}
      {!loaded && !loading && !error && (
        <p className="text-sm text-gray-400">Loading…</p>
      )}
    </div>
  );
}