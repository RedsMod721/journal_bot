import { render, screen } from "@testing-library/react";
import { SkillList } from "@/components/skills/SkillList";
import type { Skill } from "@/types/skill";

vi.mock("@/components/skills/SkillCard", () => ({
  SkillCard: ({
    skill,
    showParents,
  }: {
    skill: Skill;
    showParents?: boolean;
  }) => (
    <div>
      <span>{skill.canonical_name}</span>
      <span>{showParents ? "show-parents" : "hide-parents"}</span>
    </div>
  ),
}));

describe("SkillList", () => {
  it("passes showParents through to each skill card", () => {
    render(
      <SkillList
        skills={[
          {
            skill_id: "skill-1",
            canonical_name: "Running",
            category: "Physical",
            total_xp: 100,
            current_level: 1,
          },
        ]}
        showParents
      />
    );

    expect(screen.getByText("Running")).toBeInTheDocument();
    expect(screen.getByText("show-parents")).toBeInTheDocument();
  });
});
