import { useQuery } from "@tanstack/react-query";
import { personalityService } from "@/services/personality.service";

export function usePersonalityState(userId: string, enabled = true) {
  return useQuery({
    queryKey: ["personalityState", userId],
    queryFn: () => personalityService.getState(userId),
    enabled: enabled && !!userId,
    staleTime: 60_000,
  });
}
