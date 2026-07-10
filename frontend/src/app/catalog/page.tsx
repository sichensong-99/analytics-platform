"use client";

// Phase 5 — Metrics Catalog page
// Lists every metric from GET /catalog, searchable, expandable to show the
// definition + version history (single source of truth for metric semantics).
//
// Drop-in:
//   - App Router:   save as app/catalog/page.tsx
//   - Pages Router: save as components/MetricsCatalog.tsx and render it
//
// Set the API base if your FastAPI isn't on localhost:8000:
//   NEXT_PUBLIC_API_BASE=http://localhost:8000

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

type ChangelogEntry = { version?: number; note?: string; breaking?: boolean };
type Metric = {
  key: string;
  label: string;
  description: string;
  version?: number | null;
  grain?: string | null;
  definition?: string | null;
  unit?: string | null;
  owner?: string | null;
  changelog?: ChangelogEntry[];
  source_system?: string | null;
  business_definition?: string | null;
  time_coverage?: Record<string, unknown> | null;
  inclusions?: string | string[] | null;
  exclusions?: string | string[] | null;
  attribution?: Record<string, unknown> | string | null;
  reconciliation?: string | null;
};

export default function MetricsCatalog() {
  const [metrics, setMetrics] = useState<Metric[]>([]);
  const [filters, setFilters] = useState<Record<string, any>>({});
  const [q, setQ] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [openKey, setOpenKey] = useState<string | null>(null);

  useEffect(() => {
    fetch(`/api/catalog`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((j) => {
  setMetrics(j.metrics ?? []);
  setFilters(j.filters ?? {});
})
      .catch((e) => setError(e?.message ?? "fetch failed"));
  }, []);

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return metrics;
    return metrics.filter((m) =>
      [m.key, m.label, m.description, m.grain, m.owner]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(s)
    );
  }, [metrics, q]);

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="mb-4">
          <Link href="/dashboards" className="text-sm text-blue-600 hover:underline">← Dashboards</Link>
        </div>
      <div className="mb-4">
        <h1 className="text-xl font-semibold">Metrics Catalog</h1>
        <p className="text-sm text-gray-500">
          {metrics.length} metrics · single source of truth for definitions &amp; versions
        </p>
      </div>

      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Search metrics…"
        className="w-full mb-4 rounded-lg border border-gray-300 px-3 py-2 text-sm"
      />

      {error && (
        <p className="text-red-600 text-sm mb-4">⚠ {error} — is the metrics service up?</p>
      )}

      <div className="space-y-3">
        {filtered.map((m) => {
          const open = openKey === m.key;
          return (
            <div key={m.key} className="rounded-lg border border-gray-200 bg-white">
              <button
                onClick={() => setOpenKey(open ? null : m.key)}
                className="w-full flex items-center justify-between px-4 py-3 text-left"
              >
                <div>
                  <span className="font-medium">{m.label}</span>
                  <span className="ml-2 text-xs text-gray-400 font-mono">{m.key}</span>
                  {m.description && (
                    <p className="text-sm text-gray-500 mt-0.5">{m.description}</p>
                  )}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {m.grain && (
                    <span className="text-xs rounded-full bg-gray-100 px-2 py-0.5 text-gray-600">
                      {m.grain}
                    </span>
                  )}
                  {m.version != null && (
                    <span className="text-xs rounded-full bg-blue-100 px-2 py-0.5 text-blue-700">
                      v{m.version}
                    </span>
                  )}
                </div>
              </button>

              {open && (
                <div className="border-t border-gray-100 px-4 py-3 text-sm space-y-3">
                  {m.definition && (
                    <div>
                      <div className="text-xs font-semibold text-gray-500 mb-1">Definition</div>
                      <pre className="bg-gray-50 rounded p-2 text-xs overflow-x-auto whitespace-pre-wrap">
                        {m.definition}
                      </pre>
                    </div>
                  )}
                  {(m.source_system ||
  m.exclusions ||
  m.attribution ||
  m.reconciliation ||
  (m.time_coverage &&
    typeof m.time_coverage === "object" &&
    "notes" in m.time_coverage &&
    m.time_coverage.notes != null)) && (
  <div className="space-y-2">
    <div className="text-xs font-semibold text-gray-500">Governance</div>
    <dl className="text-xs text-gray-700 space-y-1">
      {m.source_system && (
        <div>
          <dt className="inline font-medium">Source: </dt>
          <dd className="inline">{m.source_system}</dd>
        </div>
      )}

      {m.exclusions && (
        <div>
          <dt className="inline font-medium">Exclusions: </dt>
          <dd className="inline">
            {Array.isArray(m.exclusions)
              ? m.exclusions.join("; ")
              : m.exclusions}
          </dd>
        </div>
      )}

      {m.attribution && (
        <div>
          <dt className="inline font-medium">Attribution: </dt>
          <dd className="inline">
            {typeof m.attribution === "string"
              ? m.attribution
              : JSON.stringify(m.attribution)}
          </dd>
        </div>
      )}

      {m.reconciliation && (
        <div>
          <dt className="inline font-medium">Reconciliation: </dt>
          <dd className="inline">{m.reconciliation}</dd>
        </div>
      )}

      {m.time_coverage &&
        typeof m.time_coverage === "object" &&
        "notes" in m.time_coverage &&
        m.time_coverage.notes != null && (
          <div>
            <dt className="inline font-medium">Coverage: </dt>
            <dd className="inline">{String(m.time_coverage.notes)}</dd>
          </div>
        )}
    </dl>
  </div>
)}
                  <div className="flex gap-4 text-xs text-gray-600">
                    {m.unit && (
                      <span>
                        unit: <b>{m.unit}</b>
                      </span>
                    )}
                    {m.owner && (
                      <span>
                        owner: <b>{m.owner}</b>
                      </span>
                    )}
                  </div>
                  {m.changelog && m.changelog.length > 0 && (
                    <div>
                      <div className="text-xs font-semibold text-gray-500 mb-1">Version history</div>
                      <ul className="space-y-1">
                        {m.changelog.map((c, i) => (
                          <li key={i} className="text-xs flex items-center gap-2">
                            {c.version != null && (
                              <span className="font-mono text-gray-400">v{c.version}</span>
                            )}
                            <span>{c.note}</span>
                            {c.breaking && (
                              <span className="rounded bg-red-100 px-1.5 py-0.5 text-red-700 text-[10px] font-semibold">
                                BREAKING
                              </span>
                            )}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
        {filtered.length === 0 && !error && (
          <p className="text-gray-500 text-sm">No metrics match.</p>
        )}
      </div>

       {Object.keys(filters).length > 0 && (
        <div className="mt-6 rounded-lg border border-gray-200 bg-white p-4">
          <div className="text-sm font-semibold text-gray-700 mb-3">Filters</div>

          <div className="space-y-3">
            {Object.entries(filters).map(([key, f]) => (
              <div
                key={key}
                className="text-xs text-gray-700 border-t border-gray-100 pt-3 first:border-t-0 first:pt-0"
              >
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-medium">{f.label ?? key}</span>
                  <span className="font-mono text-gray-400">{key}</span>
                </div>

                {f.definition && (
                  <p className="text-gray-600">
                    <span className="font-medium">Definition: </span>
                    {f.definition}
                  </p>
                )}

                {f.source && (
                  <p className="text-gray-600">
                    <span className="font-medium">Source: </span>
                    {f.source}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
