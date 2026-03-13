import { useQuery } from "@tanstack/react-query";
import { anomalyService } from "@/services/anomaly.service";

export function useEntryAnomaly(entryId: string, userId: string, enabled: boolean) {
  return useQuery({
    queryKey: ["entryAnomaly", userId, entryId],
    queryFn: () => anomalyService.getEntryScore(entryId, userId),
    enabled: enabled && !!entryId && !!userId,
    staleTime: 60_000,
  });
}
