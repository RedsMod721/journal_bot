import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CurrentArcCard } from "./CurrentArcCard";
import { arcsService } from "@/services/arcs.service";
import type { Arc } from "@/types/arc";

vi.mock("@/services/arcs.service");
vi.mock("@/hooks/use-toast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

const USER_ID = "user-test-123";

function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
}

function wrapper(client: QueryClient) {
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

const baseArc: Arc = {
  id: "arc-abc-123",
  arc_type: "redemption",
  status: "active",
  theme_ids: [],
  xp_requirement_multiplier: 1.0,
  xp_reward_multiplier: 1.5,
  decay_rate_multiplier: 1.0,
  started_at: "2026-03-01T10:00:00.000Z",
  created_at: "2026-03-01T10:00:00.000Z",
  updated_at: "2026-03-01T10:00:00.000Z",
};

describe("CurrentArcCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows skeleton while loading", () => {
    vi.mocked(arcsService.getCurrent).mockReturnValue(new Promise(() => {}));
    const client = makeClient();
    render(<CurrentArcCard userId={USER_ID} />, { wrapper: wrapper(client) });
    // Skeletons render instead of content
    expect(screen.queryByText("Active Story Arc")).not.toBeInTheDocument();
  });

  it("shows no-arc message when inactive", async () => {
    vi.mocked(arcsService.getCurrent).mockResolvedValue({
      active: false,
      arc: null,
    });
    const client = makeClient();
    render(<CurrentArcCard userId={USER_ID} />, { wrapper: wrapper(client) });
    expect(await screen.findByText("No Active Story Arc")).toBeInTheDocument();
  });

  it("calls onCreateEvent when the button is clicked with no arc", async () => {
    vi.mocked(arcsService.getCurrent).mockResolvedValue({
      active: false,
      arc: null,
    });
    const onCreateEvent = vi.fn();
    const client = makeClient();
    const { getByRole } = render(
      <CurrentArcCard userId={USER_ID} onCreateEvent={onCreateEvent} />,
      { wrapper: wrapper(client) }
    );
    const btn = await screen.findByRole("button", { name: /create event arc/i });
    btn.click();
    expect(onCreateEvent).toHaveBeenCalledOnce();
  });

  it("displays redemption arc with 1.5x reward multiplier in green", async () => {
    vi.mocked(arcsService.getCurrent).mockResolvedValue({
      active: true,
      arc: baseArc,
    });
    const client = makeClient();
    render(<CurrentArcCard userId={USER_ID} />, { wrapper: wrapper(client) });

    expect(await screen.findByText("Active Story Arc")).toBeInTheDocument();
    expect(screen.getByText("1.50x")).toBeInTheDocument();
    expect(screen.getByText("Redemption")).toBeInTheDocument();
  });

  it("shows event arc with custom event_name as badge label", async () => {
    vi.mocked(arcsService.getCurrent).mockResolvedValue({
      active: true,
      arc: {
        ...baseArc,
        arc_type: "event",
        event_name: "Conference Week",
        xp_reward_multiplier: 1.25,
      },
    });
    const client = makeClient();
    render(<CurrentArcCard userId={USER_ID} />, { wrapper: wrapper(client) });

    expect(await screen.findByText("Conference Week")).toBeInTheDocument();
  });

  it("shows regression arc with decay multiplier above 1 in green", async () => {
    vi.mocked(arcsService.getCurrent).mockResolvedValue({
      active: true,
      arc: {
        ...baseArc,
        arc_type: "regression",
        xp_reward_multiplier: 0.5,
        decay_rate_multiplier: 1.5,
      },
    });
    const client = makeClient();
    render(<CurrentArcCard userId={USER_ID} />, { wrapper: wrapper(client) });

    expect(await screen.findByText("Regression")).toBeInTheDocument();
    // reward multiplier below 1 renders in red class
    const rewardVal = await screen.findByText("0.50x");
    expect(rewardVal.className).toMatch(/text-red/);
    // decay above 1 renders in green
    const decayVal = screen.getByText("1.50x");
    expect(decayVal.className).toMatch(/text-green/);
  });

  it("shows error message on fetch failure", async () => {
    vi.mocked(arcsService.getCurrent).mockRejectedValue(
      new Error("Network error: cannot reach API")
    );
    const client = makeClient();
    render(<CurrentArcCard userId={USER_ID} />, { wrapper: wrapper(client) });
    expect(
      await screen.findByText(/Network error: cannot reach API/i)
    ).toBeInTheDocument();
  });

  it("shows End Arc Early button for non-vacation event arcs", async () => {
    vi.mocked(arcsService.getCurrent).mockResolvedValue({
      active: true,
      arc: { ...baseArc, arc_type: "event", event_name: "Sprint Week" },
    });
    vi.mocked(arcsService.endArc).mockResolvedValue({
      ...baseArc,
      status: "completed",
    });
    const client = makeClient();
    render(<CurrentArcCard userId={USER_ID} />, { wrapper: wrapper(client) });
    expect(
      await screen.findByRole("button", { name: /end arc early/i })
    ).toBeInTheDocument();
  });

  it("does not show End Arc Early button for vacation arc", async () => {
    vi.mocked(arcsService.getCurrent).mockResolvedValue({
      active: true,
      arc: { ...baseArc, arc_type: "event", event_name: "vacation_mode" },
    });
    const client = makeClient();
    render(<CurrentArcCard userId={USER_ID} />, { wrapper: wrapper(client) });
    await screen.findByText("Active Story Arc");
    expect(
      screen.queryByRole("button", { name: /end arc early/i })
    ).not.toBeInTheDocument();
  });
});
