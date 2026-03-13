import { useQuery } from "@tanstack/react-query";
import { journalService } from "@/services/journal.service";

export function useJournalEntries(userId: string, enabled = true) {
  return useQuery({
    queryKey: ["journalEntries", userId],
    queryFn: () => journalService.getEntries(userId),
    enabled: enabled && !!userId,
    staleTime: 15_000,
  });
}

export function useJournalEntryDetail(
  entryId: string,
  userId: string,
  enabled = true
) {
  return useQuery({
    queryKey: ["journalEntryDetail", userId, entryId],
    queryFn: () => journalService.getEntryDetail(entryId, userId),
    enabled: enabled && !!entryId && !!userId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "pending" || status === "processing" ? 2000 : false;
    },
  });
}
