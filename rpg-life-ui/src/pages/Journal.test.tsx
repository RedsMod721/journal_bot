import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Journal } from "@/pages/Journal";

const mutateAsync = vi.fn();
const useJournalEntryStatusMock = vi.fn();
const useEntryAnomalyMock = vi.fn();
const useJournalEntriesMock = vi.fn();
const useJournalEntryDetailMock = vi.fn();
const usePersonalityMessagesMock = vi.fn();
const feedbackMutateMock = vi.fn();

let entriesData: Array<Record<string, unknown>> = [];
let detailByEntryId: Record<string, Record<string, unknown>> = {};
let messagesByEntryId: Record<string, Array<Record<string, unknown>>> = {};

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

vi.mock("@/hooks/useJournalEntries", () => ({
  useJournalEntries: (...args: unknown[]) => useJournalEntriesMock(...args),
  useJournalEntryDetail: (...args: unknown[]) => useJournalEntryDetailMock(...args),
}));

vi.mock("@/hooks/usePersonalityMessages", () => ({
  usePersonalityMessages: (...args: unknown[]) => usePersonalityMessagesMock(...args),
  usePersonalityFeedback: () => ({
    mutate: feedbackMutateMock,
    isPending: false,
  }),
}));

describe("Journal thread page", () => {
  beforeEach(() => {
    entriesData = [];
    detailByEntryId = {};
    messagesByEntryId = {};

    mutateAsync.mockReset();
    useJournalEntryStatusMock.mockReset();
    useEntryAnomalyMock.mockReset();
    useJournalEntriesMock.mockReset();
    useJournalEntryDetailMock.mockReset();
    usePersonalityMessagesMock.mockReset();
    feedbackMutateMock.mockReset();

    useJournalEntriesMock.mockImplementation(() => ({
      data: entriesData,
      isLoading: false,
      error: null,
    }));
    useJournalEntryDetailMock.mockImplementation((entryId: string) => ({
      data: detailByEntryId[entryId] ?? null,
      isLoading: false,
      error: null,
    }));
    useJournalEntryStatusMock.mockReturnValue({
      isLoading: false,
      data: null,
      error: null,
    });
    useEntryAnomalyMock.mockReturnValue({
      data: null,
      isLoading: false,
    });
    usePersonalityMessagesMock.mockImplementation((_userId: string, entryId?: string) => ({
      data: entryId ? messagesByEntryId[entryId] ?? [] : [],
      isLoading: false,
      error: null,
    }));

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

  function renderPage() {
    const client = new QueryClient();
    return render(
      <QueryClientProvider client={client}>
        <Journal />
      </QueryClientProvider>
    );
  }

  it("opens the submitted entry thread immediately and shows the disabled composer", async () => {
    const text =
      "I wrote a robust integration test and improved the API consistency today.";

    mutateAsync.mockImplementation(async () => {
      detailByEntryId["entry-1"] = {
        entry_id: "entry-1",
        content: text,
        status: "processing",
        question_state: "none",
        created_at: "2026-03-13T12:00:00.000Z",
        processed_at: null,
        processing_duration_ms: null,
        error_message: null,
      };
      entriesData = [
        {
          entry_id: "entry-1",
          status: "processing",
          word_count: 11,
          preview_text: "I wrote a robust integration test and improved the API consistency today.",
          question_state: "none",
          created_at: "2026-03-13T12:00:00.000Z",
          processed_at: null,
        },
      ];

      return {
        entry_id: "entry-1",
        job_id: "job-1",
        processing_run_id: "run-1",
        idempotency_key: "idemp-1",
        status: "pending",
        poll_path: "/api/v1/entry-jobs/job-1",
        retryable: true,
      };
    });

    renderPage();

    fireEvent.change(screen.getByPlaceholderText("Today I practiced..."), {
      target: { value: text },
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Submit Entry" }));
    });

    await waitFor(() => {
      expect(mutateAsync).toHaveBeenCalledTimes(1);
    });
    expect(mutateAsync).toHaveBeenCalledWith({
      user_id: "11111111-1111-1111-1111-111111111111",
      content: text,
    });

    await waitFor(() => {
      expect(screen.getAllByText(text)).toHaveLength(2);
    });
    expect(
      screen.getByText("Entry submitted successfully! Processing in background...")
    ).toBeInTheDocument();
    expect(screen.getByText("Job ID: job-1")).toBeInTheDocument();
    expect(screen.getByText("Future Question Responses")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reply unavailable" })).toBeDisabled();
  });

  it("renders anomaly metadata and a personality assistant bubble for a completed entry", async () => {
    const text = "I shipped the new contract and reviewed the output.";

    mutateAsync.mockImplementation(async () => {
      detailByEntryId["entry-1"] = {
        entry_id: "entry-1",
        content: text,
        status: "completed",
        question_state: "none",
        created_at: "2026-03-13T12:00:00.000Z",
        processed_at: "2026-03-13T12:02:00.000Z",
        processing_duration_ms: 120000,
        error_message: null,
      };
      entriesData = [
        {
          entry_id: "entry-1",
          status: "completed",
          word_count: 10,
          preview_text: text,
          question_state: "none",
          created_at: "2026-03-13T12:00:00.000Z",
          processed_at: "2026-03-13T12:02:00.000Z",
        },
      ];
      messagesByEntryId["entry-1"] = [
        {
          id: "msg-1",
          entry_id: "entry-1",
          personality: "coach",
          message_type: "entry_feedback",
          message_text: "Keep going.",
          logical_slot_key: "primary",
          context_data: {},
          multi_personality: {
            is_primary: true,
            primary_personality: "coach",
            impact_multiplier: 1,
          },
          created_at: "2026-03-13T12:02:00.000Z",
        },
      ];
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

      return {
        entry_id: "entry-1",
        job_id: "job-1",
        processing_run_id: "run-1",
        idempotency_key: "idemp-1",
        status: "pending",
        poll_path: "/api/v1/entry-jobs/job-1",
        retryable: true,
      };
    });

    renderPage();

    fireEvent.change(screen.getByPlaceholderText("Today I practiced..."), {
      target: { value: text },
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Submit Entry" }));
    });

    await waitFor(() => {
      expect(screen.getByText("Anomaly 7.25/10")).toBeInTheDocument();
    });
    expect(screen.getByText("Coach")).toBeInTheDocument();
    expect(screen.getByText("Keep going.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Helpful" }));
    expect(feedbackMutateMock).toHaveBeenCalledWith({
      message_id: "msg-1",
      feedback_type: "thumbs_up",
    });
  });

  it("renders multiple personality replies in transcript order with scope labels", async () => {
    entriesData = [
      {
        entry_id: "entry-2",
        status: "completed",
        word_count: 8,
        preview_text: "Completed multi-personality entry",
        question_state: "none",
        created_at: "2026-03-13T10:00:00.000Z",
        processed_at: "2026-03-13T10:02:00.000Z",
      },
    ];
    detailByEntryId["entry-2"] = {
      entry_id: "entry-2",
      content: "Completed multi-personality entry",
      status: "completed",
      question_state: "none",
      created_at: "2026-03-13T10:00:00.000Z",
      processed_at: "2026-03-13T10:02:00.000Z",
      processing_duration_ms: 120000,
      error_message: null,
    };
    messagesByEntryId["entry-2"] = [
      {
        id: "msg-secondary",
        entry_id: "entry-2",
        personality: "observer",
        message_type: "entry_feedback",
        message_text: "Secondary reply",
        logical_slot_key: "secondary",
        context_data: {},
        multi_personality: {
          is_primary: false,
          primary_personality: "coach",
          impact_multiplier: 0.5,
        },
        created_at: "2026-03-13T10:02:00.000Z",
      },
      {
        id: "msg-primary",
        entry_id: "entry-2",
        personality: "coach",
        message_type: "entry_feedback",
        message_text: "Primary reply",
        logical_slot_key: "primary",
        context_data: {},
        multi_personality: {
          is_primary: true,
          primary_personality: "coach",
          impact_multiplier: 1,
        },
        created_at: "2026-03-13T10:02:00.000Z",
      },
    ];

    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/Primary •/)).toBeInTheDocument();
    });
    expect(screen.getByText(/Secondary to coach •/)).toBeInTheDocument();

    const replyBodies = screen.getAllByText(/reply$/).map((node) => node.textContent);
    expect(replyBodies).toEqual(["Primary reply", "Secondary reply"]);
  });

  it("switches between recent entry threads on the same page", async () => {
    entriesData = [
      {
        entry_id: "entry-new",
        status: "completed",
        word_count: 7,
        preview_text: "Newer entry preview",
        question_state: "none",
        created_at: "2026-03-13T11:00:00.000Z",
        processed_at: "2026-03-13T11:02:00.000Z",
      },
      {
        entry_id: "entry-old",
        status: "completed",
        word_count: 6,
        preview_text: "Older entry preview",
        question_state: "none",
        created_at: "2026-03-12T09:00:00.000Z",
        processed_at: "2026-03-12T09:02:00.000Z",
      },
    ];
    detailByEntryId["entry-new"] = {
      entry_id: "entry-new",
      content: "Newer entry body",
      status: "completed",
      question_state: "none",
      created_at: "2026-03-13T11:00:00.000Z",
      processed_at: "2026-03-13T11:02:00.000Z",
      processing_duration_ms: 120000,
      error_message: null,
    };
    detailByEntryId["entry-old"] = {
      entry_id: "entry-old",
      content: "Older entry body",
      status: "completed",
      question_state: "none",
      created_at: "2026-03-12T09:00:00.000Z",
      processed_at: "2026-03-12T09:02:00.000Z",
      processing_duration_ms: 120000,
      error_message: null,
    };

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Newer entry body")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("Older entry preview").closest("button")!);

    await waitFor(() => {
      expect(screen.getByText("Older entry body")).toBeInTheDocument();
    });
    expect(screen.queryByText("Newer entry body")).not.toBeInTheDocument();
  });
});
