import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemesSkills } from "@/pages/ThemesSkills";

vi.mock("@/contexts/UserContext", () => ({
  useUser: () => ({
    user: { id: "user-1", name: "Test User" },
  }),
}));

vi.mock("@/hooks/useThemes", () => ({
  useThemes: () => ({
    data: [
      {
        theme_id: "theme-1",
        user_id: "user-1",
        name: "Physical",
        description: "Exercise and health",
        rank: "F",
        total_xp: 200,
        current_level: 2,
        current_level_xp: 50,
        next_level_xp: 150,
        related_skills_count: 3,
        created_at: "2026-03-10T00:00:00Z",
        updated_at: "2026-03-10T00:00:00Z",
      },
    ],
    isLoading: false,
    error: null,
  }),
}));

vi.mock("@/hooks/useSkillHierarchy", () => ({
  useSkillHierarchy: () => ({
    data: [],
    isLoading: false,
    error: null,
  }),
}));

vi.mock("@/hooks/useRealmPreferences", () => ({
  useRealmPreferences: () => ({
    getRankLabel: (rank?: string | null) => rank,
  }),
}));

describe("ThemesSkills", () => {
  it("renders Themes tab data from /api/themes hook even when hierarchy is empty", async () => {
    const user = userEvent.setup();
    const queryClient = new QueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <ThemesSkills />
      </QueryClientProvider>
    );

    await user.click(screen.getByRole("tab", { name: "Themes" }));

    expect(screen.getByText("Physical")).toBeInTheDocument();
  });
});
