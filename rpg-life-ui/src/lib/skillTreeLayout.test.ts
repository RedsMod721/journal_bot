import { buildSkillTreeGraph } from "@/lib/skillTreeLayout";
import type { SkillHierarchyNode } from "@/types/skillHierarchy";

describe("buildSkillTreeGraph", () => {
  it("shows only discovered/activated nodes and prunes edges to hidden nodes", () => {
    const skills: SkillHierarchyNode[] = [
      {
        skill_id: "skill_professional_root",
        canonical_name: "Root",
        hierarchy_level: 1,
        parent_skill_ids: [],
        state: "activated",
      },
      {
        skill_id: "skill_professional_discovered",
        canonical_name: "Discovered Child",
        hierarchy_level: 2,
        parent_skill_ids: ["skill_professional_root"],
        state: "discovered",
        user_blocked: true,
      },
      {
        skill_id: "skill_professional_locked",
        canonical_name: "Locked Child",
        hierarchy_level: 3,
        parent_skill_ids: ["skill_professional_discovered"],
        state: "locked",
      },
      {
        skill_id: "skill_professional_unlocked_hidden",
        canonical_name: "Unlocked Hidden Child",
        hierarchy_level: 2,
        parent_skill_ids: ["skill_professional_root"],
        state: "unlocked_hidden",
      },
      {
        skill_id: "skill_professional_grandchild",
        canonical_name: "Grandchild",
        hierarchy_level: 4,
        parent_skill_ids: ["skill_professional_locked"],
        state: "activated",
      },
      {
        skill_id: "skill_professional_legacy",
        canonical_name: "Legacy Node",
        hierarchy_level: 2,
        parent_skill_ids: ["skill_professional_root"],
      },
    ];

    const { nodes, edges } = buildSkillTreeGraph(skills, "all");

    const nodeIds = new Set(nodes.map((node) => node.id));
    expect(nodeIds).toEqual(
      new Set([
        "skill_professional_root",
        "skill_professional_discovered",
        "skill_professional_grandchild",
        "skill_professional_legacy",
      ])
    );

    const edgeIds = new Set(edges.map((edge) => edge.id));
    expect(edgeIds).toEqual(
      new Set([
        "skill_professional_root→skill_professional_discovered",
        "skill_professional_root→skill_professional_legacy",
      ])
    );

    const statesById = new Map(nodes.map((node) => [node.id, node.data.state]));
    expect(statesById.get("skill_professional_root")).toBe("activated");
    expect(statesById.get("skill_professional_discovered")).toBe("discovered");
    expect(statesById.get("skill_professional_grandchild")).toBe("activated");
    expect(statesById.get("skill_professional_legacy")).toBe("activated");

    const blockedById = new Map(nodes.map((node) => [node.id, node.data.userBlocked]));
    expect(blockedById.get("skill_professional_discovered")).toBe(true);
    expect(blockedById.get("skill_professional_legacy")).toBe(false);

    const yById = new Map(nodes.map((node) => [node.id, node.position.y]));
    expect(yById.get("skill_professional_root")).toBeLessThan(
      yById.get("skill_professional_discovered")!
    );
    expect(yById.get("skill_professional_discovered")).toBe(
      yById.get("skill_professional_legacy")
    );
    expect(yById.get("skill_professional_discovered")).toBeLessThan(
      yById.get("skill_professional_grandchild")!
    );
  });

  it("keeps absolute hierarchy height under L1 filtering when visible parent links are missing", () => {
    const skills: SkillHierarchyNode[] = [
      {
        skill_id: "skill_professional_root",
        canonical_name: "Root",
        hierarchy_level: 1,
        parent_skill_ids: [],
        state: "activated",
      },
      {
        skill_id: "skill_professional_hidden_parent",
        canonical_name: "Hidden Parent",
        hierarchy_level: 2,
        parent_skill_ids: ["skill_professional_root"],
        state: "locked",
      },
      {
        skill_id: "skill_professional_filtered_orphan",
        canonical_name: "Filtered Orphan",
        hierarchy_level: 4,
        parent_skill_ids: ["skill_professional_hidden_parent"],
        state: "discovered",
      },
    ];

    const { nodes } = buildSkillTreeGraph(skills, "skill_professional_root");
    const yById = new Map(nodes.map((node) => [node.id, node.position.y]));
    expect(yById.get("skill_professional_filtered_orphan")).toBeGreaterThan(
      yById.get("skill_professional_root")!
    );
  });

  it("renders same-level relationships as dotted edges and avoids overlapping rank constraints", () => {
    const skills: SkillHierarchyNode[] = [
      {
        skill_id: "skill_professional_root",
        canonical_name: "Root",
        hierarchy_level: 1,
        parent_skill_ids: [],
        state: "activated",
      },
      {
        skill_id: "skill_professional_sibling_a",
        canonical_name: "Sibling A",
        hierarchy_level: 2,
        parent_skill_ids: ["skill_professional_root"],
        state: "activated",
      },
      {
        skill_id: "skill_professional_sibling_b",
        canonical_name: "Sibling B",
        hierarchy_level: 2,
        parent_skill_ids: ["skill_professional_sibling_a"],
        state: "discovered",
      },
    ];

    const { nodes, edges } = buildSkillTreeGraph(skills, "all");

    const sameLevelEdge = edges.find(
      (edge) =>
        edge.id === "skill_professional_sibling_a→skill_professional_sibling_b"
    );
    expect(sameLevelEdge).toBeDefined();
    expect(sameLevelEdge?.style?.strokeDasharray).toBe("4 4");

    const yById = new Map(nodes.map((node) => [node.id, node.position.y]));
    expect(yById.get("skill_professional_sibling_a")).toBe(
      yById.get("skill_professional_sibling_b")
    );

    const xById = new Map(nodes.map((node) => [node.id, node.position.x]));
    expect(xById.get("skill_professional_sibling_a")).not.toBe(
      xById.get("skill_professional_sibling_b")
    );
  });
});
