import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  personalityService,
  PersonalityFeedbackPayload,
} from "@/services/personality.service";

export function usePersonalityMessages(userId: string, entryId?: string, enabled = true) {
  return useQuery({
    queryKey: ["personalityMessages", userId, entryId ?? "all"],
    queryFn: () => personalityService.getMessages(userId, entryId),
    enabled: enabled && !!userId,
    staleTime: 30_000,
  });
}

export function usePersonalityFeedback(userId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: PersonalityFeedbackPayload) =>
      personalityService.submitFeedback(userId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["personalityState", userId] });
      void queryClient.invalidateQueries({ queryKey: ["personalityMessages", userId] });
    },
  });
}
