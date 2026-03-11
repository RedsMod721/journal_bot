import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ForgivenessProfileCard } from "@/components/profile/ForgivenessProfileCard";
import { forgivenessService } from "@/services/forgiveness.service";

vi.mock("@/contexts/UserContext", () => ({
  useUser: () => ({
    user: { id: "11111111-1111-1111-1111-111111111111", name: "Test User" },
  }),
}));

function renderWithQueryClient() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

  render(
    <QueryClientProvider client={client}>
      <ForgivenessProfileCard />
    </QueryClientProvider>,
  );
}

describe("ForgivenessProfileCard", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows only the preset name for non-custom presets", async () => {
    vi.spyOn(forgivenessService, "getConfig").mockResolvedValue({
      preset: "balanced",
      skill_decay_rate: 0.05,
      skill_grace_period_days: 7,
      insight_decay_rate: 0.1,
      insight_grace_period_days: 3,
      critical_staleness_threshold: 0.8,
    });

    renderWithQueryClient();

    expect(await screen.findByText("Balanced")).toBeInTheDocument();
    expect(screen.queryByText("Skill Half-life")).not.toBeInTheDocument();
    expect(
      screen.queryByText("days before skill decay starts"),
    ).not.toBeInTheDocument();
  });

  it("shows final values for the custom preset", async () => {
    vi.spyOn(forgivenessService, "getConfig").mockResolvedValue({
      preset: "custom",
      skill_decay_rate: 0.05,
      skill_grace_period_days: 12,
      insight_decay_rate: 0.1,
      insight_grace_period_days: 5,
      critical_staleness_threshold: 0.8,
    });

    renderWithQueryClient();

    expect(await screen.findByText("Custom")).toBeInTheDocument();
    expect(screen.getByText("Skill Half-life")).toBeInTheDocument();
    expect(screen.getByText("14 days")).toBeInTheDocument();
    expect(
      screen.getByText("12 days before skill decay starts"),
    ).toBeInTheDocument();
    expect(screen.getByText("Insight Half-life")).toBeInTheDocument();
    expect(screen.getByText("7 days")).toBeInTheDocument();
    expect(
      screen.getByText("5 days before insight decay starts"),
    ).toBeInTheDocument();
  });
});
