import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ForgivenessSettings } from "@/components/settings/ForgivenessSettings";
import { forgivenessService } from "@/services/forgiveness.service";

vi.mock("@/contexts/UserContext", () => ({
  useUser: () => ({
    user: { id: "11111111-1111-1111-1111-111111111111", name: "Test User" },
  }),
}));

vi.mock("@/hooks/use-toast", () => ({
  useToast: () => ({
    toast: vi.fn(),
  }),
}));

describe("ForgivenessSettings", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("loads balanced by default and shows preset names in the dropdown", async () => {
    vi.spyOn(forgivenessService, "getPresets").mockResolvedValue([
      {
        preset: "balanced",
        name: "Balanced",
        skill_decay_rate: 0.05,
        skill_grace_days: 7,
        insight_decay_rate: 0.1,
        insight_grace_days: 3,
        critical_threshold: 0.8,
      },
      {
        preset: "lenient",
        name: "Lenient",
        skill_decay_rate: 0.03,
        skill_grace_days: 10,
        insight_decay_rate: 0.07,
        insight_grace_days: 5,
        critical_threshold: 0.85,
      },
      {
        preset: "custom",
        name: "Custom",
        skill_decay_rate: 0.05,
        skill_grace_days: 7,
        insight_decay_rate: 0.1,
        insight_grace_days: 3,
        critical_threshold: 0.8,
      },
    ]);
    vi.spyOn(forgivenessService, "getConfig").mockResolvedValue({
      preset: "balanced",
      skill_decay_rate: 0.05,
      skill_grace_period_days: 7,
      insight_decay_rate: 0.1,
      insight_grace_period_days: 3,
      critical_staleness_threshold: 0.8,
    });

    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    const user = userEvent.setup();

    render(
      <QueryClientProvider client={client}>
        <ForgivenessSettings />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByRole("combobox")).toHaveTextContent("Balanced");
    });

    expect(screen.getAllByText("Fast decay")).toHaveLength(2);
    expect(screen.getAllByText("Never decays")).toHaveLength(2);

    await act(async () => {
      await user.click(screen.getByRole("combobox"));
    });

    expect(await screen.findByRole("option", { name: "Balanced" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Lenient" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Custom" })).toBeInTheDocument();
  });
});
