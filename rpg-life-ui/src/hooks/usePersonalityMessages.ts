import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  personalityService,
  PersonalityFeedbackPayload,
} from "@/services/personality.service";

interface UsePersonalityMessagesOptions {
  enabled?: boolean;
  limit?: number;
  refetchInterval?: number | false;
}

export function usePersonalityMessages(
  userId: string,
  entryId?: string,
  options?: UsePersonalityMessagesOptions
) {
  return useQuery({
    queryKey: ["personalityMessages", userId, entryId ?? "all"],
    queryFn: () => personalityService.getMessages(userId, entryId, options?.limit),
    enabled: (options?.enabled ?? true) && !!userId,
    staleTime: 30_000,
    refetchInterval: options?.refetchInterval ?? false,
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
