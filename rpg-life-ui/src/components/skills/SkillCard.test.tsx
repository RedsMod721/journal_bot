import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SkillCard } from "@/components/skills/SkillCard";
import type { Skill } from "@/types/skill";

vi.mock("@/hooks/useBlockSkill", () => ({
  useBlockSkill: () => ({
    mutateAsync: vi.fn(),
    isPending: false,
  }),
}));

vi.mock("@/hooks/useRealmPreferences", () => ({
  useRealmPreferences: () => ({
    getRankLabel: (rank?: string | null) => {
      const labels: Record<string, string> = {
        F: "Novice",
        SS: "High Sorcerer",
      };
      return rank ? labels[rank] ?? null : null;
    },
  }),
}));

const baseSkill: Skill = {
  skill_id: "skill_arcane_mastery",
  canonical_name: "Arcane Mastery",
  category: "Mental",
  total_xp: 3500,
  current_level: 22,
  current_level_xp: 500,
  next_level_xp: 1000,
  rank: "SS",
};

describe("SkillCard", () => {
  it("shows Lv label, Level tooltip, and realm rank on hover for default cards", async () => {
    const user = userEvent.setup();
    const { container } = render(<SkillCard skill={baseSkill} />);

    expect(screen.getByText("Lv")).toBeInTheDocument();
    expect(container.querySelector(".lucide-trophy")).not.toBeInTheDocument();

    await user.hover(screen.getByText("Arcane Mastery"));
    expect(await screen.findByText("SS - High Sorcerer")).toBeInTheDocument();

    await user.hover(screen.getByText("Lv"));
    await waitFor(() => {
      expect(screen.getAllByText("Level").length).toBeGreaterThan(0);
    });
  });

  it("reveals realm rank on hover for compact cards", async () => {
    const user = userEvent.setup();
    render(
      <SkillCard
        skill={{ ...baseSkill, rank: "F", current_level: 7 }}
        variant="compact"
      />
    );

    expect(screen.getByText("Lv")).toBeInTheDocument();
    expect(screen.queryByText("F - Novice")).not.toBeInTheDocument();

    await user.hover(screen.getByText("Arcane Mastery"));
    expect(await screen.findByText("F - Novice")).toBeInTheDocument();
  });

  it("shows parent skill names on hover", async () => {
    const user = userEvent.setup();
    render(
      <SkillCard
        skill={{
          ...baseSkill,
          parent_skill_names: ["Focus", "Study Habits"],
        }}
      />
    );

    expect(screen.queryByText("Parents: Focus, Study Habits")).not.toBeInTheDocument();

    await user.hover(screen.getByText("Arcane Mastery"));
    expect(await screen.findByText("Parents: Focus, Study Habits")).toBeInTheDocument();
  });

  it("hides level progression when current level is zero", () => {
    render(
      <SkillCard
        skill={{
          ...baseSkill,
          current_level: 0,
          current_level_xp: 50,
          next_level_xp: 100,
        }}
      />
    );

    expect(screen.queryByText("Level Progress")).not.toBeInTheDocument();
    expect(screen.queryByText("50 / 100 XP")).not.toBeInTheDocument();
  });
});
