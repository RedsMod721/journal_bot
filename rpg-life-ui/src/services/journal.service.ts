import apiClient, { apiPath } from "@/lib/api";

export interface JournalSubmitParams {
  user_id: string;
  raw_text: string;
}

export interface JournalSubmitResponse {
  entry_id: string;
  status: string;
  message: string;
}

export interface JournalEntryStatusResponse {
  entry_id: string;
  status: "pending" | "processing" | "completed" | "failed";
  word_count: number;
  created_at: string;
  processed_at?: string | null;
  processing_duration_ms?: number | null;
  error_message?: string | null;
}

export const journalService = {
  submitEntry: async (params: JournalSubmitParams): Promise<JournalSubmitResponse> => {
    const { data } = await apiClient.post(apiPath("/journal/entries"), params);
    return data;
  },

  getEntryStatus: async (
    entryId: string,
    userId: string
  ): Promise<JournalEntryStatusResponse> => {
    const { data } = await apiClient.get(apiPath(`/journal/entries/${entryId}`), {
      params: { user_id: userId },
    });
    return data;
  },
};
