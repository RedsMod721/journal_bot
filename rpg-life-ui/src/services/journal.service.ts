import apiClient, { apiPath } from "@/lib/api";

export interface JournalSubmitParams {
  user_id: string;
  content?: string;
  raw_text?: string;
  idempotency_key?: string;
  processing_mode?: "auto" | "sync" | "async";
}

export interface JournalSubmitResponse {
  result_type?: "ack";
  entry_id: string;
  job_id: string;
  processing_run_id: string;
  idempotency_key: string;
  status: string;
  poll_path: string;
  retryable: boolean;
  created_at_utc?: string | null;
  updated_at_utc?: string | null;
  attempt_count?: number;
  last_error_code?: string | null;
}

export interface JournalEntryStatusResponse {
  status: "in_progress" | "completed" | "failed_terminal";
  job_id: string;
  processing_run_id: string;
  entry_id: string;
  created_at_utc?: string | null;
  updated_at_utc?: string | null;
  attempt_count: number;
  last_error_code?: string | null;
  terminal_result?: Record<string, unknown> | null;
  terminal_result_pointer: {
    schema_version: number;
    job_id: string;
    entry_id: string;
    status: string;
    poll_path: string;
    terminal_result_hash?: string | null;
  };
}

export const journalService = {
  submitEntry: async (params: JournalSubmitParams): Promise<JournalSubmitResponse> => {
    const content = params.content ?? params.raw_text ?? "";
    const payload = {
      user_id: params.user_id,
      content,
      idempotency_key: params.idempotency_key ?? crypto.randomUUID(),
      processing_mode: params.processing_mode ?? "async",
    };
    const { data } = await apiClient.post(apiPath("/v1/entries"), payload);
    return data;
  },

  getEntryStatus: async (
    jobId: string,
    userId: string
  ): Promise<JournalEntryStatusResponse> => {
    const { data } = await apiClient.get(apiPath(`/v1/entry-jobs/${jobId}`), {
      params: { user_id: userId },
    });
    return data;
  },
};
