import type {
  AthleteResponse,
  ActivityListResponse,
  ActivityDetail,
  LapSummary,
  PerformanceResponse,
  LoadSummaryResponse,
} from "@/types/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY ?? "";

async function apiFetch<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      headers: API_KEY ? { "X-API-Key": API_KEY } : {},
      cache: "no-store",
    });
  } catch {
    throw new Error(`API unreachable: ${path}`);
  }
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${path}`);
  }
  return res.json() as Promise<T>;
}

export function getAthlete(): Promise<AthleteResponse> {
  return apiFetch<AthleteResponse>("/athlete");
}

export function getPerformance(days = 90): Promise<PerformanceResponse> {
  const end = new Date();
  const start = new Date();
  start.setDate(start.getDate() - days);
  const fmt = (d: Date) =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  return apiFetch<PerformanceResponse>(
    `/athlete/performance?start=${fmt(start)}&end=${fmt(end)}`
  );
}

export function getLoadSummary(
  period: "weekly" | "monthly",
  count: number
): Promise<LoadSummaryResponse> {
  const param = period === "weekly" ? `weeks=${count}` : `months=${count}`;
  return apiFetch<LoadSummaryResponse>(
    `/athlete/load/summary?period=${period}&${param}`
  );
}

export function getActivities(
  limit = 20,
  offset = 0,
  sportType?: string
): Promise<ActivityListResponse> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  if (sportType) params.set("sport_type", sportType);
  return apiFetch<ActivityListResponse>(`/activities?${params}`);
}

export function getActivity(id: number): Promise<ActivityDetail> {
  return apiFetch<ActivityDetail>(`/activities/${id}`);
}

export function getActivityLaps(id: number): Promise<LapSummary[]> {
  return apiFetch<LapSummary[]>(`/activities/${id}/laps`);
}
