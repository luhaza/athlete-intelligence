import Link from "next/link";
import { notFound } from "next/navigation";
import { getActivity, getActivityLaps } from "@/lib/api";

interface Props {
  params: Promise<{ id: string }>;
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString("en-US", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

export default async function ActivityDetailPage({ params }: Props) {
  const { id: idStr } = await params;
  const id = Number(idStr);
  if (!Number.isFinite(id)) notFound();
  const [activity, laps] = await Promise.all([
    getActivity(id),
    getActivityLaps(id).catch(() => []),
  ]);

  return (
    <div className="space-y-6">
      <div>
        <Link
          href="/activities"
          className="text-sm text-blue-600 hover:underline"
        >
          &larr; Activities
        </Link>
        <h1 className="text-2xl font-bold text-gray-900 mt-2">
          {activity.name}
        </h1>
        <p className="text-sm text-gray-500 mt-1">
          {formatDate(activity.start_date_local)} &middot; {activity.sport_type}
        </p>
      </div>

      {/* Stats grid */}
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <h2 className="text-sm font-semibold text-gray-700 mb-4">Stats</h2>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
          <Stat label="Distance" value={`${activity.distance_miles.toFixed(2)} mi`} />
          <Stat label="Time" value={activity.duration_formatted} />
          {activity.pace_per_mile && (
            <Stat label="Pace" value={`${activity.pace_per_mile} /mi`} />
          )}
          {activity.average_heartrate && (
            <Stat label="Avg HR" value={`${Math.round(activity.average_heartrate)} bpm`} />
          )}
          {activity.max_heartrate && (
            <Stat label="Max HR" value={`${Math.round(activity.max_heartrate)} bpm`} />
          )}
          {activity.elevation_gain_feet != null && (
            <Stat
              label="Elevation"
              value={`${activity.elevation_gain_feet.toFixed(0)} ft`}
            />
          )}
          {activity.calories != null && (
            <Stat label="Calories" value={`${Math.round(activity.calories)} kcal`} />
          )}
          {activity.training_load != null && (
            <Stat label="Training Load" value={activity.training_load.toFixed(1)} />
          )}
        </div>
      </div>

      {/* Lap table */}
      {laps.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">
            Laps / Splits
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-gray-400 border-b border-gray-100">
                  <th className="pb-2 font-medium">Lap</th>
                  <th className="pb-2 font-medium">Distance</th>
                  <th className="pb-2 font-medium">Time</th>
                  <th className="pb-2 font-medium">Pace</th>
                  <th className="pb-2 font-medium">Avg HR</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {laps.map((lap) => (
                  <tr key={lap.lap_index} className="text-gray-700">
                    <td className="py-2 text-gray-400">{lap.lap_index}</td>
                    <td className="py-2">{lap.distance_miles.toFixed(2)} mi</td>
                    <td className="py-2">
                      {formatMovingTime(lap.moving_time)}
                    </td>
                    <td className="py-2">{lap.pace_per_mile ?? "—"}</td>
                    <td className="py-2">
                      {lap.average_heartrate
                        ? `${Math.round(lap.average_heartrate)} bpm`
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-gray-400">{label}</p>
      <p className="font-semibold text-gray-800 mt-0.5">{value}</p>
    </div>
  );
}

function formatMovingTime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return `${m}:${String(s).padStart(2, "0")}`;
}
