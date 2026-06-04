"use client";

// Phase 4.5 — Step 6: real-time channel health dashboard
// Polls GET /metrics/channel-health every few seconds, shows current ROAS per
// channel, and flags anomalous channels in red.
//
// Drop-in:
//   - App Router:  save as app/realtime/page.tsx
//   - Pages Router: save as components/ChannelHealthDashboard.tsx and render it
//   - needs Apache ECharts (already in your stack):  npm i echarts
//
// If your FastAPI isn't on localhost:8000, set:
//   NEXT_PUBLIC_API_BASE=http://localhost:8000
//
// CORS: add this to your FastAPI main.py so the browser can fetch cross-origin:
//   from fastapi.middleware.cors import CORSMiddleware
//   app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"],
//                      allow_methods=["*"], allow_headers=["*"])

import { useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const REFRESH_MS = 5000;

type HealthWindow = {
  channel: string;
  window_start: string;
  window_end: string;
  total_spend: number;
  attributed_revenue: number;
  roas: number;
  order_count: number;
  is_anomaly: boolean;
  last_updated: string;
};

export default function ChannelHealthDashboard() {
  const [windows, setWindows] = useState<HealthWindow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<echarts.ECharts | null>(null);

  // poll the endpoint
  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const res = await fetch(`${API_BASE}/metrics/channel-health?minutes=30`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = await res.json();
        if (!active) return;
        setWindows(json.windows ?? []);
        setUpdatedAt(new Date());
        setError(null);
      } catch (e: any) {
        if (active) setError(e?.message ?? "fetch failed");
      }
    };
    load();
    const id = setInterval(load, REFRESH_MS);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, []);

  // latest window per channel
  const latest = useMemo(() => {
    const byChannel = new Map<string, HealthWindow>();
    for (const w of windows) {
      const cur = byChannel.get(w.channel);
      if (!cur || w.window_start > cur.window_start) byChannel.set(w.channel, w);
    }
    return Array.from(byChannel.values()).sort((a, b) =>
      a.channel.localeCompare(b.channel)
    );
  }, [windows]);

  const anomalies = latest.filter((w) => w.is_anomaly);

  // render / update chart
  useEffect(() => {
    if (!chartRef.current) return;
    if (!chartInstance.current) chartInstance.current = echarts.init(chartRef.current);
    chartInstance.current.setOption({
      grid: { left: 48, right: 16, top: 24, bottom: 32 },
      tooltip: { trigger: "axis" },
      xAxis: { type: "category", data: latest.map((w) => w.channel) },
      yAxis: { type: "value", name: "ROAS" },
      series: [
        {
          type: "bar",
          barWidth: "45%",
          data: latest.map((w) => ({
            value: w.roas,
            itemStyle: { color: w.is_anomaly ? "#ef4444" : "#3b82f6" },
          })),
        },
      ],
    });
  }, [latest]);

  useEffect(
    () => () => {
      chartInstance.current?.dispose();
      chartInstance.current = null;
    },
    []
  );

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold">Real-time Channel Health</h1>
        <span className="text-sm text-gray-500">
          {error
            ? `⚠ ${error}`
            : updatedAt
            ? `updated ${updatedAt.toLocaleTimeString()}`
            : "loading…"}
        </span>
      </div>

      {anomalies.length > 0 && (
        <div className="mb-4 rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-red-700">
          ⚠ ROAS anomaly: <b>{anomalies.map((a) => a.channel).join(", ")}</b> dropped sharply.
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        {latest.map((w) => (
          <div
            key={w.channel}
            className={`rounded-lg border p-4 ${
              w.is_anomaly ? "border-red-400 bg-red-50" : "border-gray-200 bg-white"
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="font-medium capitalize">{w.channel}</span>
              {w.is_anomaly && (
                <span className="text-xs font-semibold text-red-600">ANOMALY</span>
              )}
            </div>
            <div className="mt-2 text-2xl font-bold">{w.roas?.toFixed(2)}</div>
            <div className="text-xs text-gray-500">ROAS</div>
            <div className="mt-2 text-xs text-gray-500">
              spend ${w.total_spend?.toFixed(0)} · rev ${w.attributed_revenue?.toFixed(0)} ·{" "}
              {w.order_count} orders
            </div>
          </div>
        ))}
      </div>

      <div ref={chartRef} style={{ width: "100%", height: 320 }} />

      {latest.length === 0 && !error && (
        <p className="text-gray-500 text-sm mt-4">
          Waiting for data… make sure the metrics service is up (try
          METRICS_DATA_SOURCE=mock to preview).
        </p>
      )}
    </div>
  );
}
