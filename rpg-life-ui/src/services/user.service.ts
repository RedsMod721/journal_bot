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
  email?: string | null;
}

export type RealmRankWordingPreset =
  | "standard"
  | "arcane_magic_system"
  | "galactic_tech_rank"
  | "divine_ascension_path"
  | "cultivation_realm";

export interface RealmScopePreferences {
  visual: boolean;
  naming: boolean;
  messages: boolean;
  llm: boolean;
}

export interface RealmRanksWordingPreference {
  preset: RealmRankWordingPreset;
}

export interface RealmPreferences {
  scope: RealmScopePreferences;
  ranks_wording: RealmRanksWordingPreference;
}

export interface SkillHierarchyPreferences {
  default_blocked_preference: boolean;
}

export interface UserPreferencesResponse {
  user_id: string;
  realm: RealmPreferences;
  skill_hierarchy: SkillHierarchyPreferences;
}

export interface RankWordingOption {
  rank: string;
  wording: string;
}

export interface RankWordingPresetResponse {
  preset: RealmRankWordingPreset;
  name: string;
  ranks: RankWordingOption[];
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

  getUserPreferences: async (userId: string): Promise<UserPreferencesResponse> => {
    const { data } = await apiClient.get(apiPath(`/users/${userId}/preferences`));
    return data;
  },

  updateUserPreferences: async (
    userId: string,
    payload: {
      realm?: RealmPreferences;
      skill_hierarchy?: SkillHierarchyPreferences;
    }
  ): Promise<UserPreferencesResponse> => {
    const { data } = await apiClient.put(apiPath(`/users/${userId}/preferences`), payload);
    return data;
  },

  getRealmRankWordingPresets: async (): Promise<RankWordingPresetResponse[]> => {
    const { data } = await apiClient.get(
      apiPath("/users/preferences/realm/rank-wording-presets")
    );
    return data;
  },
};
