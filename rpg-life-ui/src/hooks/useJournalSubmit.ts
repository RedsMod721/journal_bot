import { useMutation, useQueryClient } from "@tanstack/react-query";
import { journalService } from "@/services/journal.service";
import { useToast } from "@/hooks/use-toast";

export function useJournalSubmit() {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: journalService.submitEntry,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["skills"] });
      queryClient.invalidateQueries({ queryKey: ["quests"] });
      queryClient.invalidateQueries({ queryKey: ["userStats"] });
      queryClient.invalidateQueries({ queryKey: ["journalEntries"] });

      toast({
        title: "Entry Submitted!",
        description: "Your journal entry is being processed in the background.",
      });
    },
    onError: (error: Error) => {
      toast({
        variant: "destructive",
        title: "Submission Failed",
        description: error.message,
      });
    },
  });
}
