import apiClient, { apiPath } from "@/lib/api";

export interface AnomalyScoreResponse {
  entry_id: string;
  score: number;
  troll_multiplier: number;
  calculated_at?: string | null;
  missing: boolean;
  detection_factors?: Record<string, unknown> | null;
}

export interface RecentAnomaliesResponse {
  anomalies: AnomalyScoreResponse[];
  total: number;
}

export const anomalyService = {
  getEntryScore: async (entryId: string, userId: string): Promise<AnomalyScoreResponse> => {
    const { data } = await apiClient.get(apiPath(`/anomaly/${entryId}`), {
      params: { user_id: userId },
    });
    return data;
  },

  getRecent: async (
    userId: string,
    minScore = 6,
    limit = 5
  ): Promise<RecentAnomaliesResponse> => {
    const { data } = await apiClient.get(apiPath("/anomaly/recent"), {
      params: { user_id: userId, min_score: minScore, limit },
    });
    return data;
  },
};
