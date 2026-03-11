import { buildL1SkillResolver } from "@/lib/skillHierarchyRoots";

describe("buildL1SkillResolver", () => {
  it("resolves L1 ancestors and keeps multi-root skills discoverable under Adventure", () => {
    const resolver = buildL1SkillResolver([
      {
        skill_id: "skill_physical_adventure",
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
        skill_id: "skill_mental_exploration",
        canonical_name: "Exploration",
        hierarchy_level: 2,
        parent_skill_ids: ["skill_mental_mental_wellbeing"],
      },
      {
        skill_id: "skill_mental_adaptability",
        canonical_name: "Adaptability",
        hierarchy_level: 3,
        parent_skill_ids: [
          "skill_mental_exploration",
          "skill_physical_adventure",
        ],
      },
    ]);

    expect(resolver.getL1SkillIds("skill_mental_adaptability")).toEqual([
      "skill_physical_adventure",
      "skill_mental_mental_wellbeing",
    ]);

    expect(resolver.getL1SkillOptions()).toEqual([
      { skillId: "skill_physical_adventure", label: "Adventure" },
      { skillId: "skill_mental_mental_wellbeing", label: "Mental Wellbeing" },
    ]);
  });
});
