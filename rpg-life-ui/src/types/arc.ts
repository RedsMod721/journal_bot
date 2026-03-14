export type ArcType = "tutorial" | "regression" | "redemption" | "event";
export type ArcStatus = "active" | "paused" | "completed" | "abandoned";

export interface Arc {
  id: string;
  arc_type: ArcType;
  status: ArcStatus;
  event_name?: string;
  theme_ids: string[];
  xp_requirement_multiplier: number;
  xp_reward_multiplier: number;
  decay_rate_multiplier: number;
  started_at: string;
  duration_days?: number;
  created_at: string;
  updated_at: string;
  completed_at?: string;
}

export interface CurrentArcResponse {
  active: boolean;
  arc: Arc | null;
}

export interface ArcHistoryResponse {
  items: Arc[];
  next_cursor: string | null;
}

export const ARC_TYPE_LABELS: Record<ArcType, string> = {
  tutorial: "Tutorial",
  regression: "Regression",
  redemption: "Redemption",
  event: "Event",
};

export const ARC_TYPE_COLORS: Record<ArcType, string> = {
  tutorial: "bg-blue-500/10 text-blue-500 border-blue-500/20",
  regression: "bg-red-500/10 text-red-500 border-red-500/20",
  redemption: "bg-green-500/10 text-green-500 border-green-500/20",
  event: "bg-purple-500/10 text-purple-500 border-purple-500/20",
};

export const ARC_STATUS_COLORS: Record<ArcStatus, string> = {
  active: "bg-green-500/10 text-green-500 border-green-500/20",
  paused: "bg-yellow-500/10 text-yellow-500 border-yellow-500/20",
  completed: "bg-blue-500/10 text-blue-500 border-blue-500/20",
  abandoned: "bg-gray-500/10 text-gray-500 border-gray-500/20",
};
