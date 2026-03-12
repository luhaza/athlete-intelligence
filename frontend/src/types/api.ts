// TypeScript interfaces mirroring backend Pydantic schemas

export interface AthleteResponse {
  id: number;
  strava_athlete_id: number;
  username: string | null;
  firstname: string | null;
  lastname: string | null;
  full_name: string;
  resting_heart_rate: number | null;
  max_heart_rate: number | null;
}

export interface ActivitySummary {
  id: number;
  strava_activity_id: number;
  name: string;
  sport_type: string;
  start_date: string;
  start_date_local: string;
  distance: number; // meters
  moving_time: number; // seconds
  elapsed_time: number; // seconds
  average_speed: number | null; // m/s
  average_heartrate: number | null;
  average_cadence: number | null;
  average_watts: number | null;
  total_elevation_gain: number | null;
  training_load: number | null;
  // computed fields
  distance_miles: number;
  distance_km: number;
  duration_formatted: string;
  pace_per_mile: string | null;
  speed_mph: number | null;
}

export interface ActivityDetail extends ActivitySummary {
  description: string | null;
  workout_type: number | null;
  timezone: string | null;
  max_speed: number | null;
  max_heartrate: number | null;
  max_watts: number | null;
  weighted_average_watts: number | null;
  elev_high: number | null;
  elev_low: number | null;
  calories: number | null;
  suffer_score: number | null;
  gear_id: string | null;
  trainer: boolean;
  commute: boolean;
  manual: boolean;
  private: boolean;
  elevation_gain_feet: number | null;
}

export interface ActivityListResponse {
  total: number;
  limit: number;
  offset: number;
  activities: ActivitySummary[];
}

export interface LapSummary {
  lap_index: number;
  name: string | null;
  distance: number; // meters
  moving_time: number; // seconds
  elapsed_time: number; // seconds
  average_speed: number | null;
  average_heartrate: number | null;
  average_cadence: number | null;
  average_watts: number | null;
  distance_miles: number;
  pace_per_mile: string | null;
}

export interface PerformanceDaySnapshot {
  date: string; // YYYY-MM-DD
  daily_load: number;
  ctl: number;
  atl: number;
  tsb: number;
}

export interface PerformanceResponse {
  start_date: string;
  end_date: string;
  series: PerformanceDaySnapshot[];
  current_ctl: number;
  current_atl: number;
  current_tsb: number;
  trend: "improving" | "declining" | "stable";
}

export interface LoadPeriodSummary {
  period_label: string;
  start_date: string;
  end_date: string;
  total_load: number;
  total_distance_km: number;
  total_moving_time_hours: number;
  total_activities: number;
  activities_by_sport: Record<string, number>;
}

export interface LoadSummaryResponse {
  period: "weekly" | "monthly";
  periods: LoadPeriodSummary[];
}
