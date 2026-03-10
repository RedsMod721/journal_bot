import { useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { journalService } from "@/services/journal.service";

export function useJournalEntryStatus(entryId: string, userId: string, enabled: boolean) {
  const queryClient = useQueryClient();
  const invalidatedEntryId = useRef<string | null>(null);

  const query = useQuery({
    queryKey: ["journalEntryStatus", entryId, userId],
    queryFn: () => journalService.getEntryStatus(entryId, userId),
    enabled: enabled && !!entryId && !!userId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (!status || status === "pending" || status === "processing") {
        return 2000;
      }
      return false;
    },
  });

  useEffect(() => {
    if (!entryId) {
      invalidatedEntryId.current = null;
      return;
    }

    const status = query.data?.status;
    const isTerminal = status === "completed" || status === "failed";
    if (!isTerminal || invalidatedEntryId.current === entryId) {
      return;
    }

    invalidatedEntryId.current = entryId;
    void queryClient.invalidateQueries({ queryKey: ["skills", userId] });
    void queryClient.invalidateQueries({ queryKey: ["quests", userId] });
    void queryClient.invalidateQueries({ queryKey: ["userStats", userId] });
  }, [entryId, query.data?.status, queryClient, userId]);

  return query;
}
