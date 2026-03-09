"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { LoadPeriodSummary } from "@/types/api";

interface WeeklyLoadChartProps {
  periods: LoadPeriodSummary[];
}

interface TooltipPayload {
  payload?: {
    total_distance_km: number;
    total_moving_time_hours: number;
    total_activities: number;
  };
}

function CustomTooltip({ payload, label }: { payload?: TooltipPayload[]; label?: string }) {
  if (!payload?.length || !payload[0].payload) return null;
  const p = payload[0].payload;
  return (
    <div className="bg-white border border-gray-200 rounded-lg p-3 text-xs shadow-md">
      <p className="font-semibold text-gray-700 mb-1">{label}</p>
      <p className="text-gray-600">{(p.total_distance_km * 0.621371).toFixed(1)} mi</p>
      <p className="text-gray-600">{p.total_moving_time_hours.toFixed(1)} hrs</p>
      <p className="text-gray-600">{p.total_activities} activities</p>
    </div>
  );
}

export default function WeeklyLoadChart({ periods }: WeeklyLoadChartProps) {
  const data = periods.map((p) => ({
    label: p.period_label.replace(/^\d{4}-W/, "W"),
    load: Math.round(p.total_load),
    total_distance_km: p.total_distance_km,
    total_moving_time_hours: p.total_moving_time_hours,
    total_activities: p.total_activities,
  }));

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 5, right: 16, left: 0, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
        <XAxis dataKey="label" tick={{ fontSize: 11 }} tickLine={false} />
        <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
        <Tooltip content={<CustomTooltip />} cursor={{ fill: "#f3f4f6" }} />
        <Bar dataKey="load" fill="#3b82f6" radius={[4, 4, 0, 0]} name="Training Load" />
      </BarChart>
    </ResponsiveContainer>
  );
}
