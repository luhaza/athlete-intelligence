"use client";

import { useState } from "react";
import useSWR from "swr";
import { getActivities } from "@/lib/api";
import ActivityCard from "@/components/ActivityCard";
import type { ActivityListResponse } from "@/types/api";

const SPORT_TYPES = ["", "Run", "Ride", "Swim", "Walk", "Hike", "WeightTraining"];
const PAGE_SIZE = 20;

export default function ActivitiesPage() {
  const [offset, setOffset] = useState(0);
  const [sportType, setSportType] = useState("");

  const { data, isLoading, error } = useSWR<ActivityListResponse>(
    ["activities", offset, sportType],
    () => getActivities(PAGE_SIZE, offset, sportType || undefined)
  );

  const total = data?.total ?? 0;
  const hasPrev = offset > 0;
  const hasNext = offset + PAGE_SIZE < total;

  function handleSportChange(e: React.ChangeEvent<HTMLSelectElement>) {
    setSportType(e.target.value);
    setOffset(0);
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Activities</h1>
        <select
          value={sportType}
          onChange={handleSportChange}
          className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-300"
        >
          {SPORT_TYPES.map((t) => (
            <option key={t} value={t}>
              {t || "All sports"}
            </option>
          ))}
        </select>
      </div>

      {isLoading && (
        <div className="text-center text-gray-400 py-16 text-sm">Loading…</div>
      )}

      {error && (
        <div className="text-center text-red-500 py-16 text-sm">
          Failed to load activities. Is the API running?
        </div>
      )}

      {data && data.activities.length === 0 && (
        <div className="text-center text-gray-400 py-16 text-sm">
          No activities found.
        </div>
      )}

      {data && data.activities.length > 0 && (
        <>
          <div className="space-y-3">
            {data.activities.map((a) => (
              <ActivityCard key={a.id} activity={a} />
            ))}
          </div>

          <div className="flex items-center justify-between text-sm text-gray-500">
            <span>
              {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => setOffset(offset - PAGE_SIZE)}
                disabled={!hasPrev}
                className="px-3 py-1.5 rounded-lg border border-gray-200 disabled:opacity-40 hover:bg-gray-50 transition-colors"
              >
                Prev
              </button>
              <button
                onClick={() => setOffset(offset + PAGE_SIZE)}
                disabled={!hasNext}
                className="px-3 py-1.5 rounded-lg border border-gray-200 disabled:opacity-40 hover:bg-gray-50 transition-colors"
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
