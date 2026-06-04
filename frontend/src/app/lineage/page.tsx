"use client";

// Phase 5 — Data Lineage graph
// Renders the source -> silver -> warehouse -> metric -> dashboard DAG from
// GET /lineage. Click a node to trace its full upstream + downstream (impact
// analysis); click again (or "reset") to clear.
//
// Drop-in:
//   - App Router:   save as app/lineage/page.tsx
//   - Pages Router: save as components/LineageGraph.tsx and render it
//   - needs Apache ECharts:  npm i echarts
//
// To embed in the Catalog page instead (click a metric -> show its lineage),
// reuse this component and pre-select that metric's id.

import { useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

type LNode = { id: string; name: string; category: number };
type LEdge = { source: string; target: string };
type Lineage = { categories: string[]; nodes: LNode[]; edges: LEdge[] };

export default function LineageGraph() {
  const [data, setData] = useState<Lineage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const elRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/lineage`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(setData)
      .catch((e) => setError(e?.message ?? "fetch failed"));
  }, []);

  // upstream / downstream adjacency
  const { up, down } = useMemo(() => {
    const up = new Map<string, string[]>();
    const down = new Map<string, string[]>();
    for (const e of data?.edges ?? []) {
      if (!down.has(e.source)) down.set(e.source, []);
      down.get(e.source)!.push(e.target);
      if (!up.has(e.target)) up.set(e.target, []);
      up.get(e.target)!.push(e.source);
    }
    return { up, down };
  }, [data]);

  // set of nodes connected to the selected one (both directions)
  const connected = useMemo(() => {
    if (!selected) return null;
    const seen = new Set<string>([selected]);
    const walk = (adj: Map<string, string[]>) => {
      const stack = [selected];
      while (stack.length) {
        const n = stack.pop()!;
        for (const m of adj.get(n) ?? []) {
          if (!seen.has(m)) {
            seen.add(m);
            stack.push(m);
          }
        }
      }
    };
    walk(up);
    walk(down);
    return seen;
  }, [selected, up, down]);

  // layered layout: x by category, y spread within category
  const positioned = useMemo(() => {
    if (!data) return [];
    const byCat = new Map<number, LNode[]>();
    for (const n of data.nodes) {
      if (!byCat.has(n.category)) byCat.set(n.category, []);
      byCat.get(n.category)!.push(n);
    }
    const out: (LNode & { x: number; y: number })[] = [];
    byCat.forEach((nodes, cat) => {
      nodes.forEach((n, i) => {
        out.push({ ...n, x: cat * 260, y: (i - (nodes.length - 1) / 2) * 66 });
      });
    });
    return out;
  }, [data]);

  // render
  useEffect(() => {
    if (!elRef.current || !data) return;
    if (!chartRef.current) chartRef.current = echarts.init(elRef.current);
    const onNode = (id: string) => !connected || connected.has(id);
    chartRef.current.setOption({
      tooltip: {},
      legend: [{ data: data.categories, top: 0 }],
      series: [
        {
          type: "graph",
          layout: "none",
          roam: true,
          label: { show: true, fontSize: 11, position: "right" },
          edgeSymbol: ["none", "arrow"],
          edgeSymbolSize: 7,
          emphasis: { focus: "adjacency" },
          categories: data.categories.map((c) => ({ name: c })),
          data: positioned.map((n) => ({
            id: n.id,
            name: n.name,
            x: n.x,
            y: n.y,
            category: n.category,
            symbolSize: 14,
            itemStyle: { opacity: onNode(n.id) ? 1 : 0.15 },
            label: { opacity: onNode(n.id) ? 1 : 0.2 },
          })),
          links: data.edges.map((e) => {
            const on = !connected || (connected.has(e.source) && connected.has(e.target));
            return {
              source: e.source,
              target: e.target,
              lineStyle: {
                opacity: on ? 0.6 : 0.08,
                width: on ? 1.5 : 1,
                curveness: 0.1,
                color: connected && on ? "#2563eb" : undefined,
              },
            };
          }),
        },
      ],
    });
  }, [data, positioned, connected]);

  // click a node -> select / deselect
  useEffect(() => {
    const c = chartRef.current;
    if (!c) return;
    const handler = (p: any) => {
      if (p.dataType === "node") setSelected((s) => (s === p.data.id ? null : p.data.id));
    };
    c.on("click", handler);
    return () => {
      c.off("click", handler);
    };
  }, [data]);

  useEffect(
    () => () => {
      chartRef.current?.dispose();
      chartRef.current = null;
    },
    []
  );

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-2">
        <div>
          <h1 className="text-xl font-semibold">Data Lineage</h1>
          <p className="text-sm text-gray-500">
            Click a node to trace its upstream &amp; downstream (impact analysis). Click again to reset.
          </p>
        </div>
        {selected && (
          <button onClick={() => setSelected(null)} className="text-sm text-blue-600">
            reset
          </button>
        )}
      </div>
      {error && (
        <p className="text-red-600 text-sm mb-2">⚠ {error} — is the metrics service up?</p>
      )}
      <div
        ref={elRef}
        style={{ width: "100%", height: 520 }}
        className="rounded-lg border border-gray-200 bg-white"
      />
    </div>
  );
}
