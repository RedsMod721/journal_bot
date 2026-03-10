import { useQuery } from "@tanstack/react-query";
import { userService, UserStats } from "@/services/user.service";

export const DEFAULT_STATS: UserStats = {
  user_id: "",
  total_xp: 0,
  current_level: 1,
  current_level_xp: 0,
  next_level_xp: 1410000,
  active_quests: 0,
  skills_practiced: 0,
  journal_entries: 0,
  current_streak: 0,
  xp_today: 0,
  xp_this_week: 0,
  recent_gain: 0,
};

export function useUserStats(userId: string) {
  return useQuery({
    queryKey: ["userStats", userId],
    queryFn: () => userService.getUserStats(userId),
    enabled: !!userId,
    staleTime: 2 * 60 * 1000,
  });
}
