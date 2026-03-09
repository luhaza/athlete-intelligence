import { getPerformance, getLoadSummary } from "@/lib/api";
import StatCard from "@/components/StatCard";
import PMCChart from "@/components/PMCChart";
import WeeklyLoadChart from "@/components/WeeklyLoadChart";

const TREND_LABELS: Record<string, string> = {
  improving: "Improving",
  declining: "Declining",
  stable: "Stable",
};

const TREND_COLORS: Record<string, "green" | "red" | "gray"> = {
  improving: "green",
  declining: "red",
  stable: "gray",
};

export default async function DashboardPage() {
  const [perf, loadSummary] = await Promise.all([
    getPerformance(90),
    getLoadSummary("weekly", 12),
  ]);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-sm text-gray-500 mt-1">
          {perf.start_date} &rarr; {perf.end_date}
        </p>
      </div>

      {/* Stat row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <StatCard
          label="CTL (Fitness)"
          value={perf.current_ctl.toFixed(1)}
          sub="42-day avg load"
          color="blue"
        />
        <StatCard
          label="ATL (Fatigue)"
          value={perf.current_atl.toFixed(1)}
          sub="7-day avg load"
          color="red"
        />
        <StatCard
          label="TSB (Form)"
          value={perf.current_tsb.toFixed(1)}
          sub="CTL − ATL (yesterday)"
          color={perf.current_tsb >= 0 ? "green" : "red"}
        />
        <StatCard
          label="Trend"
          value={TREND_LABELS[perf.trend] ?? perf.trend}
          sub="7-day CTL direction"
          color={TREND_COLORS[perf.trend] ?? "gray"}
        />
      </div>

      {/* PMC chart */}
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <h2 className="text-sm font-semibold text-gray-700 mb-4">
          Performance Management Chart — last 90 days
        </h2>
        <PMCChart series={perf.series} />
      </div>

      {/* Weekly load bar chart */}
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <h2 className="text-sm font-semibold text-gray-700 mb-4">
          Weekly Training Load — last 12 weeks
        </h2>
        <WeeklyLoadChart periods={loadSummary.periods} />
      </div>
    </div>
  );
}
