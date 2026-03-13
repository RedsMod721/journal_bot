import { useQuery } from "@tanstack/react-query";
import { anomalyService } from "@/services/anomaly.service";

export function useRecentAnomalies(userId: string, enabled = true) {
  return useQuery({
    queryKey: ["recentAnomalies", userId],
    queryFn: () => anomalyService.getRecent(userId),
    enabled: enabled && !!userId,
    staleTime: 60_000,
  });
}
