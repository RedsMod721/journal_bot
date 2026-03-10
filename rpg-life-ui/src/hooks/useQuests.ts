import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { questsService } from "@/services/quests.service";
import { useToast } from "@/hooks/use-toast";

export function useQuests(userId: string, status?: string) {
  return useQuery({
    queryKey: ["quests", userId, status],
    queryFn: () => questsService.getQuests(userId, status),
    enabled: !!userId,
    staleTime: 5 * 60 * 1000,
  });
}

export function useQuest(questId: string, userId: string) {
  return useQuery({
    queryKey: ["quest", questId, userId],
    queryFn: () => questsService.getQuestById(questId, userId),
    enabled: !!questId && !!userId,
  });
}

export function useCompleteQuest() {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: ({ questId, userId }: { questId: string; userId: string }) =>
      questsService.completeQuest(questId, userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["quests"] });
      queryClient.invalidateQueries({ queryKey: ["userStats"] });

      toast({
        title: "Quest Completed! 🎉",
        description: "Great job! Your progress has been updated.",
      });
    },
    onError: (error: Error) => {
      toast({
        variant: "destructive",
        title: "Failed to Complete Quest",
        description: error.message,
      });
    },
  });
}
