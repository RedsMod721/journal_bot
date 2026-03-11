import { createContext, useContext, useMemo, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useUser } from "@/contexts/UserContext";
import {
  type RankWordingPresetResponse,
  type RealmPreferences,
  type RealmRankWordingPreset,
  type SkillHierarchyPreferences,
  type UserPreferencesResponse,
  userService,
} from "@/services/user.service";

const DEFAULT_SCOPE = {
  visual: true,
  naming: false,
  messages: false,
  llm: false,
} as const;

const DEFAULT_REALM_PREFERENCES: RealmPreferences = {
  scope: { ...DEFAULT_SCOPE },
  ranks_wording: { preset: "standard" },
};

const DEFAULT_SKILL_HIERARCHY_PREFERENCES: SkillHierarchyPreferences = {
  default_blocked_preference: false,
};

interface RealmPreferencesContextValue {
  presets: RankWordingPresetResponse[];
  currentPreset: RealmRankWordingPreset;
  defaultBlockedPreference: boolean;
  isLoading: boolean;
  error: string | null;
  isUpdating: boolean;
  isUpdatingSkillHierarchy: boolean;
  setPreset: (preset: RealmRankWordingPreset) => Promise<void>;
  setDefaultBlockedPreference: (blocked: boolean) => Promise<void>;
  getRankLabel: (rank?: string | null) => string | null;
}

const RealmPreferencesContext = createContext<RealmPreferencesContextValue | undefined>(
  undefined
);

export function RealmPreferencesProvider({ children }: { children: ReactNode }) {
  const { user } = useUser();
  const queryClient = useQueryClient();

  const presetsQuery = useQuery({
    queryKey: ["realmRankWordingPresets"],
    queryFn: userService.getRealmRankWordingPresets,
    staleTime: 30 * 60 * 1000,
  });

  const preferencesQuery = useQuery({
    queryKey: ["userPreferences", user?.id],
    queryFn: () => userService.getUserPreferences(user?.id ?? ""),
    enabled: !!user?.id,
    staleTime: 5 * 60 * 1000,
  });

  const setPresetMutation = useMutation({
    mutationFn: async (preset: RealmRankWordingPreset) => {
      if (!user?.id) {
        throw new Error("Cannot update realm preset without an active user.");
      }

      const currentRealm = preferencesQuery.data?.realm ?? DEFAULT_REALM_PREFERENCES;
      const payload = {
        realm: {
          scope: currentRealm.scope,
          ranks_wording: { preset },
        },
      };
      return userService.updateUserPreferences(user.id, payload);
    },
    onMutate: async (preset) => {
      if (!user?.id) return undefined;

      const queryKey = ["userPreferences", user.id] as const;
      await queryClient.cancelQueries({ queryKey });
      const previous = queryClient.getQueryData<UserPreferencesResponse>(queryKey);
      const currentRealm = previous?.realm ?? DEFAULT_REALM_PREFERENCES;

      queryClient.setQueryData<UserPreferencesResponse>(queryKey, {
        user_id: user.id,
        realm: {
          scope: currentRealm.scope,
          ranks_wording: { preset },
        },
        skill_hierarchy:
          previous?.skill_hierarchy ?? DEFAULT_SKILL_HIERARCHY_PREFERENCES,
      });

      return { previous, queryKey };
    },
    onError: (_error, _preset, context) => {
      if (!context?.previous) return;
      queryClient.setQueryData(context.queryKey, context.previous);
    },
    onSuccess: (updated) => {
      if (!user?.id) return;
      queryClient.setQueryData(["userPreferences", user.id], updated);
    },
  });

  const setDefaultBlockedMutation = useMutation({
    mutationFn: async (blocked: boolean) => {
      if (!user?.id) {
        throw new Error("Cannot update skill defaults without an active user.");
      }
      return userService.updateUserPreferences(user.id, {
        skill_hierarchy: { default_blocked_preference: blocked },
      });
    },
    onMutate: async (blocked) => {
      if (!user?.id) return undefined;

      const queryKey = ["userPreferences", user.id] as const;
      await queryClient.cancelQueries({ queryKey });
      const previous = queryClient.getQueryData<UserPreferencesResponse>(queryKey);

      queryClient.setQueryData<UserPreferencesResponse>(queryKey, {
        user_id: user.id,
        realm: previous?.realm ?? DEFAULT_REALM_PREFERENCES,
        skill_hierarchy: {
          default_blocked_preference: blocked,
        },
      });

      return { previous, queryKey };
    },
    onError: (_error, _blocked, context) => {
      if (!context?.previous) return;
      queryClient.setQueryData(context.queryKey, context.previous);
    },
    onSuccess: (updated) => {
      if (!user?.id) return;
      queryClient.setQueryData(["userPreferences", user.id], updated);
    },
  });

  const currentPreset = (preferencesQuery.data?.realm.ranks_wording.preset ??
    "standard") as RealmRankWordingPreset;
  const defaultBlockedPreference =
    preferencesQuery.data?.skill_hierarchy.default_blocked_preference ?? false;

  const selectedPreset = useMemo(() => {
    const presets = presetsQuery.data ?? [];
    return presets.find((item) => item.preset === currentPreset) ?? presets[0];
  }, [currentPreset, presetsQuery.data]);

  const rankLabelMap = useMemo(() => {
    const map = new Map<string, string>();
    for (const row of selectedPreset?.ranks ?? []) {
      map.set(row.rank, row.wording);
    }
    return map;
  }, [selectedPreset]);

  const setPreset = async (preset: RealmRankWordingPreset) => {
    if (!user?.id || preset === currentPreset) return;
    await setPresetMutation.mutateAsync(preset);
  };

  const setDefaultBlockedPreference = async (blocked: boolean) => {
    if (!user?.id || blocked === defaultBlockedPreference) return;
    await setDefaultBlockedMutation.mutateAsync(blocked);
  };

  const error =
    presetsQuery.error ??
    preferencesQuery.error ??
    setPresetMutation.error ??
    setDefaultBlockedMutation.error;

  const value: RealmPreferencesContextValue = {
    presets: presetsQuery.data ?? [],
    currentPreset,
    defaultBlockedPreference,
    isLoading:
      presetsQuery.isLoading ||
      (!!user?.id && preferencesQuery.isLoading),
    error: error instanceof Error ? error.message : null,
    isUpdating: setPresetMutation.isPending,
    isUpdatingSkillHierarchy: setDefaultBlockedMutation.isPending,
    setPreset,
    setDefaultBlockedPreference,
    getRankLabel: (rank?: string | null) => {
      if (!rank) return null;
      return rankLabelMap.get(rank) ?? null;
    },
  };

  return (
    <RealmPreferencesContext.Provider value={value}>
      {children}
    </RealmPreferencesContext.Provider>
  );
}

export function useRealmPreferences() {
  const context = useContext(RealmPreferencesContext);
  if (context === undefined) {
    throw new Error("useRealmPreferences must be used within a RealmPreferencesProvider");
  }
  return context;
}
