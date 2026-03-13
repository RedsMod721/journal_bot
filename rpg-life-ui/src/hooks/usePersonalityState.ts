import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  personalityService,
  type LikabilityScores,
} from "@/services/personality.service";

export function usePersonalityState(userId: string, enabled = true) {
  return useQuery({
    queryKey: ["personalityState", userId],
    queryFn: () => personalityService.getState(userId),
    enabled: enabled && !!userId,
    staleTime: 60_000,
  });
}

export function useUpdateLikabilityScores(userId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (likabilityScores: LikabilityScores) =>
      personalityService.updateLikabilityScores(userId, likabilityScores),
    onSuccess: (nextState) => {
      queryClient.setQueryData(["personalityState", userId], nextState);
      void queryClient.invalidateQueries({ queryKey: ["personalityState", userId] });
    },
  });
}
