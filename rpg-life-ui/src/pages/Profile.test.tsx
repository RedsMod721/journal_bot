import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Profile } from "@/pages/Profile";

const feedbackMutateMock = vi.fn();

vi.mock("@/contexts/UserContext", () => ({
  useUser: () => ({
    user: { id: "user-1", name: "Test User" },
  }),
}));

vi.mock("@/hooks/useUserStats", () => ({
  useUserStats: () => ({
    data: {
      user_id: "user-1",
      total_xp: 1200,
      current_level: 4,
      current_level_xp: 200,
      next_level_xp: 400,
      active_quests: 2,
      skills_practiced: 5,
      journal_entries: 12,
      current_streak: 3,
      xp_today: 120,
      xp_this_week: 400,
      recent_gain: 80,
    },
    isLoading: false,
    error: null,
  }),
}));

vi.mock("@/hooks/usePersonalityState", () => ({
  usePersonalityState: () => ({
    data: {
      active_personality: "coach",
      likability_scores: {
        observer: 80,
        therapist: 70,
        coach: 88,
        sassy: 50,
        wargod: 40,
        raphael: 60,
      },
      switch_cooldown_seconds: 600,
      multi_personality_annotations: 0,
    },
    isLoading: false,
  }),
}));

vi.mock("@/hooks/usePersonalityMessages", () => ({
  usePersonalityMessages: () => ({
    data: [
      {
        id: "msg-1",
        entry_id: "entry-1",
        personality: "coach",
        message_type: "entry_feedback",
        message_text: "Strong momentum today.",
        context_data: {},
        created_at: "2026-03-13T00:00:00.000Z",
      },
    ],
    isLoading: false,
  }),
  usePersonalityFeedback: () => ({
    mutate: feedbackMutateMock,
    isPending: false,
  }),
}));

vi.mock("@/hooks/useRecentAnomalies", () => ({
  useRecentAnomalies: () => ({
    data: {
      anomalies: [
        {
          entry_id: "entry-1",
          score: 7.5,
          troll_multiplier: 2.75,
          missing: false,
        },
      ],
    },
    isLoading: false,
  }),
}));

vi.mock("@/components/dashboard/HarmonyRadarChart", () => ({
  HarmonyRadarChart: () => <div>HarmonyRadarChart</div>,
}));

vi.mock("@/components/dashboard/VarietyScoreCard", () => ({
  VarietyScoreCard: () => <div>VarietyScoreCard</div>,
}));

vi.mock("@/components/profile/ForgivenessProfileCard", () => ({
  ForgivenessProfileCard: () => <div>ForgivenessProfileCard</div>,
}));

describe("Profile", () => {
  beforeEach(() => {
    feedbackMutateMock.mockReset();
  });

  it("renders live personality and anomaly sections", () => {
    const client = new QueryClient();

    render(
      <QueryClientProvider client={client}>
        <Profile />
      </QueryClientProvider>
    );

    expect(screen.getByText("Personality System")).toBeInTheDocument();
    expect(screen.getByText("Recent Anomalies")).toBeInTheDocument();
    expect(screen.getByText("Latest Personality Message")).toBeInTheDocument();
    expect(screen.queryByText("AI personality archetypes (Coming in Week 6)")).not.toBeInTheDocument();
  });

  it("sends personality feedback from the latest message card", () => {
    const client = new QueryClient();

    render(
      <QueryClientProvider client={client}>
        <Profile />
      </QueryClientProvider>
    );

    fireEvent.click(screen.getByRole("button", { name: "Helpful" }));
    expect(feedbackMutateMock).toHaveBeenCalledWith({
      message_id: "msg-1",
      feedback_type: "thumbs_up",
    });
  });
});
