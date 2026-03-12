import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Journal } from "@/pages/Journal";

const mutateAsync = vi.fn();
const useJournalEntryStatusMock = vi.fn();

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

describe("Journal page submit flow", () => {
  beforeEach(() => {
    mutateAsync.mockReset();
    useJournalEntryStatusMock.mockReset();
    useJournalEntryStatusMock.mockReturnValue({
      isLoading: false,
      data: null,
      error: null,
    });
    mutateAsync.mockResolvedValue({
      entry_id: "entry-1",
      status: "submitted",
      message: "ok",
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
      raw_text: "I wrote a robust integration test and improved the API consistency today.",
    });

    await waitFor(() => {
      expect(useJournalEntryStatusMock).toHaveBeenLastCalledWith(
        "entry-1",
        "11111111-1111-1111-1111-111111111111",
        true
      );
    });
    expect(
      screen.getByText("Entry submitted successfully! Processing in background...")
    ).toBeInTheDocument();
    expect(screen.getByText("Entry ID: entry-1")).toBeInTheDocument();
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
});
