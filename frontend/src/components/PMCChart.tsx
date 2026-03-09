"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import type { PerformanceDaySnapshot } from "@/types/api";

interface PMCChartProps {
  series: PerformanceDaySnapshot[];
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr + "T00:00:00");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export default function PMCChart({ series }: PMCChartProps) {
  const data = series.map((s) => ({
    date: formatDate(s.date),
    CTL: Math.round(s.ctl * 10) / 10,
    ATL: Math.round(s.atl * 10) / 10,
    TSB: Math.round(s.tsb * 10) / 10,
  }));

  // Show every ~2 weeks on the x-axis
  const tickInterval = Math.max(1, Math.floor(data.length / 6));

  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={data} margin={{ top: 5, right: 16, left: 0, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 11 }}
          interval={tickInterval}
          tickLine={false}
        />
        <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
        <Tooltip
          contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e5e7eb" }}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <ReferenceLine y={0} stroke="#d1d5db" strokeDasharray="4 2" />
        <Line
          type="monotone"
          dataKey="CTL"
          stroke="#3b82f6"
          dot={false}
          strokeWidth={2}
          name="CTL (Fitness)"
        />
        <Line
          type="monotone"
          dataKey="ATL"
          stroke="#ef4444"
          dot={false}
          strokeWidth={2}
          name="ATL (Fatigue)"
        />
        <Line
          type="monotone"
          dataKey="TSB"
          stroke="#22c55e"
          dot={false}
          strokeWidth={2}
          strokeDasharray="5 3"
          name="TSB (Form)"
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
