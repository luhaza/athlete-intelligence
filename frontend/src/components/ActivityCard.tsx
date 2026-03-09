import Link from "next/link";
import type { ActivitySummary } from "@/types/api";

const SPORT_ICONS: Record<string, string> = {
  Run: "🏃",
  Ride: "🚴",
  Swim: "🏊",
  Walk: "🚶",
  Hike: "🥾",
  WeightTraining: "🏋️",
  Yoga: "🧘",
};

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

interface ActivityCardProps {
  activity: ActivitySummary;
}

export default function ActivityCard({ activity: a }: ActivityCardProps) {
  const icon = SPORT_ICONS[a.sport_type] ?? "🏅";

  return (
    <Link href={`/activities/${a.strava_activity_id}`}>
      <div className="bg-white border border-gray-200 rounded-xl p-4 hover:border-blue-300 hover:shadow-sm transition-all flex items-center gap-4">
        <span className="text-2xl">{icon}</span>
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-gray-900 truncate">{a.name}</p>
          <p className="text-xs text-gray-400 mt-0.5">
            {formatDate(a.start_date_local)} &middot; {a.sport_type}
          </p>
        </div>
        <div className="flex gap-5 text-sm text-gray-600 shrink-0">
          <div className="text-right">
            <p className="font-medium">{a.distance_miles.toFixed(1)} mi</p>
            <p className="text-xs text-gray-400">distance</p>
          </div>
          <div className="text-right">
            <p className="font-medium">{a.duration_formatted}</p>
            <p className="text-xs text-gray-400">time</p>
          </div>
          {a.pace_per_mile && (
            <div className="text-right">
              <p className="font-medium">{a.pace_per_mile}</p>
              <p className="text-xs text-gray-400">/mile</p>
            </div>
          )}
          {a.average_heartrate && (
            <div className="text-right">
              <p className="font-medium">{Math.round(a.average_heartrate)}</p>
              <p className="text-xs text-gray-400">bpm</p>
            </div>
          )}
        </div>
      </div>
    </Link>
  );
}
