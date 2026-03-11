import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemesSkills } from "@/pages/ThemesSkills";

const mockUseUser = vi.fn();
const mockUseThemes = vi.fn();
const mockUseSkillHierarchy = vi.fn();

vi.mock("@/contexts/UserContext", () => ({
  useUser: () => mockUseUser(),
}));

vi.mock("@/hooks/useThemes", () => ({
  useThemes: () => mockUseThemes(),
}));

vi.mock("@/hooks/useSkillHierarchy", () => ({
  useSkillHierarchy: () => mockUseSkillHierarchy(),
}));

vi.mock("@/hooks/useRealmPreferences", () => ({
  useRealmPreferences: () => ({
    getRankLabel: (rank?: string | null) => rank,
  }),
}));

describe("ThemesSkills", () => {
  beforeEach(() => {
    mockUseUser.mockReturnValue({
      user: { id: "user-1", name: "Test User" },
      isLoading: false,
    });
    mockUseThemes.mockReturnValue({
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
          related_skill_names: ["Running", "Mobility", "Stretching"],
          created_at: "2026-03-10T00:00:00Z",
          updated_at: "2026-03-10T00:00:00Z",
        },
      ],
      isLoading: false,
      error: null,
    });
    mockUseSkillHierarchy.mockReturnValue({
      data: [
        {
          skill_id: "skill-1",
          canonical_name: "Running",
          category: "Physical",
          total_xp: 120,
          current_level: 2,
          current_level_xp: 20,
          next_level_xp: 100,
          hierarchy_level: 2,
          parent_skill_ids: ["root-physical"],
          state: "activated",
          user_blocked: false,
        },
        {
          skill_id: "skill-2",
          canonical_name: "Meditation",
          category: "Mental",
          total_xp: 90,
          current_level: 1,
          current_level_xp: 90,
          next_level_xp: 100,
          hierarchy_level: 2,
          parent_skill_ids: ["root-mental"],
          state: "activated",
          user_blocked: false,
        },
      ],
      isLoading: false,
      error: null,
    });
  });

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

  it("filters my skills by selected theme", async () => {
    const user = userEvent.setup();
    const queryClient = new QueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <ThemesSkills />
      </QueryClientProvider>
    );

    expect(screen.getByText("Running")).toBeInTheDocument();
    expect(screen.getByText("Meditation")).toBeInTheDocument();

    await user.click(screen.getAllByRole("combobox")[1]);
    await user.click(await screen.findByRole("option", { name: "Physical" }));

    expect(screen.getByText("Running")).toBeInTheDocument();
    expect(screen.queryByText("Meditation")).not.toBeInTheDocument();
  });

  it("does not crash when a theme has no related skill names array", async () => {
    const user = userEvent.setup();
    mockUseThemes.mockReturnValue({
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
          related_skills_count: 0,
          related_skill_names: undefined,
          created_at: "2026-03-10T00:00:00Z",
          updated_at: "2026-03-10T00:00:00Z",
        },
      ],
      isLoading: false,
      error: null,
    });
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
