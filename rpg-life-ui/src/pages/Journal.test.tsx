import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Journal } from "@/pages/Journal";

const mutateAsync = vi.fn();
const useJournalEntryStatusMock = vi.fn();
const useEntryAnomalyMock = vi.fn();
const usePersonalityMessagesMock = vi.fn();
const feedbackMutateMock = vi.fn();

vi.mock("@/contexts/UserContext", () => ({
  useUser: () => ({
    user: { id: "11111111-1111-1111-1111-111111111111", name: "Test User" },
  }),
}));

vi.mock("@/hooks/useJournalSubmit", () => ({
  useJournalSubmit: () => ({
    mutateAsync,
    isPending: false,
  }),
}));

vi.mock("@/hooks/useJournalEntryStatus", () => ({
  useJournalEntryStatus: (...args: unknown[]) => useJournalEntryStatusMock(...args),
}));

vi.mock("@/hooks/useEntryAnomaly", () => ({
  useEntryAnomaly: (...args: unknown[]) => useEntryAnomalyMock(...args),
}));

vi.mock("@/hooks/usePersonalityMessages", () => ({
  usePersonalityMessages: (...args: unknown[]) => usePersonalityMessagesMock(...args),
  usePersonalityFeedback: () => ({
    mutate: feedbackMutateMock,
    isPending: false,
  }),
}));

describe("Journal page submit flow", () => {
  beforeEach(() => {
    mutateAsync.mockReset();
    useJournalEntryStatusMock.mockReset();
    useEntryAnomalyMock.mockReset();
    usePersonalityMessagesMock.mockReset();
    feedbackMutateMock.mockReset();
    useJournalEntryStatusMock.mockReturnValue({
      isLoading: false,
      data: null,
      error: null,
    });
    useEntryAnomalyMock.mockReturnValue({
      data: null,
      isLoading: false,
    });
    usePersonalityMessagesMock.mockReturnValue({
      data: [],
      isLoading: false,
    });
    mutateAsync.mockResolvedValue({
      entry_id: "entry-1",
      job_id: "job-1",
      processing_run_id: "run-1",
      idempotency_key: "idemp-1",
      status: "pending",
      poll_path: "/api/v1/entry-jobs/job-1",
      retryable: true,
    });
  });

  it("submits valid journal content", async () => {
    const client = new QueryClient();

    render(
      <QueryClientProvider client={client}>
        <Journal />
      </QueryClientProvider>
    );

    const textarea = screen.getByPlaceholderText("Today I practiced...");
    fireEvent.change(textarea, {
      target: {
        value: "I wrote a robust integration test and improved the API consistency today.",
      },
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Submit Entry" }));
    });

    await waitFor(() => {
      expect(mutateAsync).toHaveBeenCalledTimes(1);
    });
    expect(mutateAsync).toHaveBeenCalledWith({
      user_id: "11111111-1111-1111-1111-111111111111",
      content: "I wrote a robust integration test and improved the API consistency today.",
    });

    await waitFor(() => {
      expect(useJournalEntryStatusMock).toHaveBeenLastCalledWith(
        "job-1",
        "11111111-1111-1111-1111-111111111111",
        true
      );
    });
    expect(
      screen.getByText("Entry submitted successfully! Processing in background...")
    ).toBeInTheDocument();
    expect(screen.getByText("Job ID: job-1")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Today I practiced...")).toHaveValue("");
  });

  it("does not show success or clear text when submit fails", async () => {
    mutateAsync.mockRejectedValue(new Error("not found"));

    const client = new QueryClient();

    render(
      <QueryClientProvider client={client}>
        <Journal />
      </QueryClientProvider>
    );

    const textarea = screen.getByPlaceholderText("Today I practiced...");
    const text = "I captured the failure path without losing my draft.";

    fireEvent.change(textarea, { target: { value: text } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Submit Entry" }));
    });

    await waitFor(() => {
      expect(mutateAsync).toHaveBeenCalledTimes(1);
    });
    expect(textarea).toHaveValue(text);
    expect(
      screen.queryByText("Entry submitted successfully! Processing in background...")
    ).not.toBeInTheDocument();
    expect(screen.queryByText("not found")).not.toBeInTheDocument();
  });

  it("renders anomaly and personality feedback when the job completes", async () => {
    useJournalEntryStatusMock.mockReturnValue({
      isLoading: false,
      error: null,
      data: {
        status: "completed",
        job_id: "job-1",
        processing_run_id: "run-1",
        entry_id: "entry-1",
        attempt_count: 1,
        last_error_code: null,
        terminal_result: { status: "completed" },
        terminal_result_pointer: {
          schema_version: 1,
          job_id: "job-1",
          entry_id: "entry-1",
          status: "completed",
          poll_path: "/api/v1/entry-jobs/job-1",
        },
      },
    });
    useEntryAnomalyMock.mockReturnValue({
      isLoading: false,
      data: {
        entry_id: "entry-1",
        score: 7.25,
        troll_multiplier: 2.5,
        missing: false,
      },
    });
    usePersonalityMessagesMock.mockReturnValue({
      isLoading: false,
      data: [
        {
          id: "msg-1",
          entry_id: "entry-1",
          personality: "coach",
          message_type: "entry_feedback",
          message_text: "Keep going.",
          context_data: {},
          created_at: "2026-03-13T00:00:00.000Z",
        },
      ],
    });

    const client = new QueryClient();

    render(
      <QueryClientProvider client={client}>
        <Journal />
      </QueryClientProvider>
    );

    fireEvent.change(screen.getByPlaceholderText("Today I practiced..."), {
      target: {
        value: "I shipped the new contract and reviewed the output.",
      },
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Submit Entry" }));
    });

    expect(screen.getByText("Anomaly Score")).toBeInTheDocument();
    expect(screen.getByText("coach feedback")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Helpful" }));
    expect(feedbackMutateMock).toHaveBeenCalledWith({
      message_id: "msg-1",
      feedback_type: "thumbs_up",
    });
  });
});
