import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemesList } from "@/components/skills/ThemesList";
import type { Theme } from "@/types/theme";

vi.mock("@/hooks/useRealmPreferences", () => ({
  useRealmPreferences: () => ({
    getRankLabel: (rank?: string | null) => {
      const labels: Record<string, string> = {
        F: "Beginner",
        E: "Amateur",
        D: "Apprentice",
      };
      return rank ? labels[rank] ?? null : null;
    },
  }),
}));

describe("ThemesList", () => {
  it("renders canonical theme cards from theme entities", () => {
    const themes: Theme[] = [
      {
        theme_id: "theme-1",
        user_id: "user-1",
        name: "Physical",
        description: "Exercise and health",
        rank: "F",
        total_xp: 250,
        current_level: 2,
        current_level_xp: 109,
        next_level_xp: 123,
        related_skills_count: 2,
        related_skill_names: ["Running", "Mobility"],
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
      {
        theme_id: "theme-2",
        user_id: "user-1",
        name: "Mental",
        description: "Learning and cognition",
        rank: null,
        total_xp: 0,
        current_level: 0,
        current_level_xp: 0,
        next_level_xp: 141,
        related_skills_count: 0,
        related_skill_names: [],
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    ];

    render(<ThemesList themes={themes} />);

    expect(screen.getByText("Physical")).toBeInTheDocument();
    expect(screen.getByText("Mental")).toBeInTheDocument();
    expect(screen.getByText("2 related skills")).toBeInTheDocument();
    expect(screen.getByText("0 related skills")).toBeInTheDocument();
    expect(screen.getAllByRole("progressbar")).toHaveLength(1);
    expect(screen.queryByText("0 / 141 XP")).not.toBeInTheDocument();
  });

  it("shows empty-state text when no theme entities are returned", () => {
    render(<ThemesList themes={[]} />);
    expect(screen.getByText("No themes available yet.")).toBeInTheDocument();
  });

  it("shows realm rank wording on hover based on theme level", async () => {
    const user = userEvent.setup();
    const themes: Theme[] = [
      {
        theme_id: "theme-3",
        user_id: "user-1",
        name: "Emotional",
        description: "Emotional skills",
        rank: null,
        total_xp: 9000,
        current_level: 10,
        current_level_xp: 100,
        next_level_xp: 500,
        related_skills_count: 1,
        related_skill_names: ["Journaling"],
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    ];

    render(<ThemesList themes={themes} />);

    expect(screen.queryByText("E - Amateur")).not.toBeInTheDocument();
    expect(screen.queryByText("Journaling")).not.toBeInTheDocument();
    await user.hover(screen.getByText("Emotional"));
    expect(await screen.findByText("E - Amateur")).toBeInTheDocument();
    expect(screen.getByText("Journaling")).toBeInTheDocument();
    expect(screen.queryByText("1 related skill")).not.toBeInTheDocument();
    expect(screen.getByText("Lv")).toBeInTheDocument();
  });

  it("falls back to the related skill count on hover when names are missing", async () => {
    const user = userEvent.setup();
    const themes = [
      {
        theme_id: "theme-4",
        user_id: "user-1",
        name: "Professional",
        description: "Professional skills",
        rank: "D",
        total_xp: 1200,
        current_level: 4,
        current_level_xp: 200,
        next_level_xp: 400,
        related_skills_count: 2,
        related_skill_names: undefined,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    ] as unknown as Theme[];

    render(<ThemesList themes={themes} />);

    expect(screen.getByText("2 related skills")).toBeInTheDocument();
    await user.hover(screen.getByText("Professional"));
    expect(screen.getByText("2 related skills")).toBeInTheDocument();
    expect(screen.queryByText("No related skills yet.")).not.toBeInTheDocument();
  });
});
