import apiClient, { apiPath } from "@/lib/api";

export interface UserStats {
  user_id: string;
  total_xp: number;
  current_level: number;
  current_level_xp: number;
  next_level_xp: number;
  active_quests: number;
  skills_practiced: number;
  journal_entries: number;
  current_streak: number;
  xp_today: number;
  xp_this_week: number;
  recent_gain: number;
}

export interface UserListItem {
  id: string;
  username?: string | null;
  display_name?: string | null;
  email: string;
}

export const userService = {
  listUsers: async (): Promise<UserListItem[]> => {
    const { data } = await apiClient.get(apiPath("/users"));
    return data;
  },

  getUserStats: async (userId: string): Promise<UserStats> => {
    const { data } = await apiClient.get(apiPath(`/users/${userId}/stats`));
    return data;
  },
};
