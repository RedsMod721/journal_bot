import { useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { journalService } from "@/services/journal.service";

export function useJournalEntryStatus(jobId: string, userId: string, enabled: boolean) {
  const queryClient = useQueryClient();
  const invalidatedJobId = useRef<string | null>(null);

  const query = useQuery({
    queryKey: ["journalEntryStatus", jobId, userId],
    queryFn: () => journalService.getEntryStatus(jobId, userId),
    enabled: enabled && !!jobId && !!userId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (!status || status === "in_progress") {
        return 2000;
      }
      return false;
    },
  });

  useEffect(() => {
    if (!jobId) {
      invalidatedJobId.current = null;
      return;
    }

    const status = query.data?.status;
    const isTerminal = status === "completed" || status === "failed_terminal";
    if (!isTerminal || invalidatedJobId.current === jobId) {
      return;
    }

    invalidatedJobId.current = jobId;
    const entryId = query.data?.entry_id;
    void queryClient.invalidateQueries({ queryKey: ["skills", userId] });
    void queryClient.invalidateQueries({ queryKey: ["quests", userId] });
    void queryClient.invalidateQueries({ queryKey: ["userStats", userId] });
    void queryClient.invalidateQueries({ queryKey: ["recentAnomalies", userId] });
    void queryClient.invalidateQueries({ queryKey: ["personalityState", userId] });
    void queryClient.invalidateQueries({ queryKey: ["personalityMessages", userId] });
    void queryClient.invalidateQueries({ queryKey: ["journalEntries", userId] });
    if (entryId) {
      void queryClient.invalidateQueries({
        queryKey: ["journalEntryDetail", userId, entryId],
      });
    }
  }, [jobId, query.data?.entry_id, query.data?.status, queryClient, userId]);

  return query;
}
