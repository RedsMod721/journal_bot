import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Journal } from "@/pages/Journal";

const mutateAsync = vi.fn();

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
  useJournalEntryStatus: () => ({
    isLoading: false,
    data: null,
    error: null,
  }),
}));

describe("Journal page submit flow", () => {
  beforeEach(() => {
    mutateAsync.mockReset();
    mutateAsync.mockResolvedValue({
      entry_id: "entry-1",
      status: "submitted",
      message: "ok",
    });
  });

  it("submits valid journal content", async () => {
    const client = new QueryClient();
    const user = userEvent.setup();

    render(
      <QueryClientProvider client={client}>
        <Journal />
      </QueryClientProvider>
    );

    const textarea = screen.getByPlaceholderText("Today I practiced...");
    await user.type(
      textarea,
      "I wrote a robust integration test and improved the API consistency today."
    );
    await user.click(screen.getByRole("button", { name: "Submit Entry" }));

    expect(mutateAsync).toHaveBeenCalledTimes(1);
    expect(mutateAsync).toHaveBeenCalledWith({
      user_id: "11111111-1111-1111-1111-111111111111",
      raw_text: "I wrote a robust integration test and improved the API consistency today.",
    });
  });
});
