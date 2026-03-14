import apiClient, { apiPath } from "@/lib/api";
import { Arc, ArcHistoryResponse, CurrentArcResponse } from "@/types/arc";

// Arc router is mounted at /api/v1/arcs — apiPath prepends /api
const arcPath = (path: string) => apiPath(`/v1/arcs${path}`);

export interface CreateEventArcData {
  event_name: string;
  theme_ids?: string[];
  duration_days?: number;
  xp_requirement_multiplier?: number;
  xp_reward_multiplier?: number;
  decay_rate_multiplier?: number;
}

export const arcsService = {
  getCurrent: async (userId: string): Promise<CurrentArcResponse> => {
    const { data } = await apiClient.get(arcPath("/current"), {
      params: { user_id: userId },
    });
    return data;
  },

  getHistory: async (
    userId: string,
    cursor?: string,
    limit = 20
  ): Promise<ArcHistoryResponse> => {
    const params: Record<string, string | number> = { user_id: userId, limit };
    if (cursor) params.cursor = cursor;
    const { data } = await apiClient.get(arcPath("/history"), { params });
    return data;
  },

  createEvent: async (
    userId: string,
    payload: CreateEventArcData
  ): Promise<Arc> => {
    const { data } = await apiClient.post(arcPath("/event"), payload, {
      params: { user_id: userId },
    });
    return data;
  },

  activateVacation: async (
    userId: string,
    duration_days?: number
  ): Promise<Arc> => {
    const { data } = await apiClient.post(
      arcPath("/vacation/activate"),
      { duration_days },
      { params: { user_id: userId } }
    );
    return data;
  },

  endVacation: async (userId: string): Promise<Arc> => {
    const { data } = await apiClient.post(
      arcPath("/vacation/end"),
      null,
      { params: { user_id: userId } }
    );
    return data;
  },

  endArc: async (userId: string, arcId: string): Promise<Arc> => {
    const { data } = await apiClient.post(
      arcPath(`/${arcId}/end`),
      null,
      { params: { user_id: userId } }
    );
    return data;
  },

  abandonArc: async (userId: string, arcId: string): Promise<Arc> => {
    const { data } = await apiClient.post(
      arcPath(`/${arcId}/abandon`),
      null,
      { params: { user_id: userId } }
    );
    return data;
  },
};
