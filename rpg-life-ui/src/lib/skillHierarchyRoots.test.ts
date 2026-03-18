import { buildL1SkillResolver } from "@/lib/skillHierarchyRoots";

describe("buildL1SkillResolver", () => {
  it("resolves L1 ancestors and keeps multi-root skills discoverable under Adventure", () => {
    const resolver = buildL1SkillResolver([
      {
        skill_id: "skill_adventure_adventure",
        canonical_name: "Adventure",
        hierarchy_level: 1,
        parent_skill_ids: [],
      },
      {
        skill_id: "skill_mental_mental_wellbeing",
        canonical_name: "Mental Wellbeing",
        hierarchy_level: 1,
        parent_skill_ids: [],
      },
      {
        skill_id: "skill_adventure_exploration",
        canonical_name: "Exploration",
        hierarchy_level: 2,
        parent_skill_ids: ["skill_adventure_adventure"],
      },
      {
        skill_id: "skill_adventure_adaptability",
        canonical_name: "Adaptability",
        hierarchy_level: 3,
        parent_skill_ids: [
          "skill_adventure_exploration",
          "skill_mental_mental_wellbeing",
        ],
      },
    ]);

    expect(resolver.getL1SkillIds("skill_adventure_adaptability")).toEqual([
      "skill_adventure_adventure",
      "skill_mental_mental_wellbeing",
    ]);

    expect(resolver.getL1SkillOptions()).toEqual([
      { skillId: "skill_adventure_adventure", label: "Adventure" },
      { skillId: "skill_mental_mental_wellbeing", label: "Mental Wellbeing" },
    ]);
  });
});
