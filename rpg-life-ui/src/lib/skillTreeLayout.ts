import dagre from "@dagrejs/dagre";
import { type Edge, type Node, Position } from "@xyflow/react";
import type {
  SkillHierarchyNode,
  SkillTreeCategory,
  SkillTreeNodeData,
} from "@/types/skillHierarchy";
import { getCategoryFromSkillId } from "@/types/skillHierarchy";

const NODE_WIDTH = 168;
const NODE_HEIGHT = 52;

export function buildSkillTreeGraph(
  allSkills: SkillHierarchyNode[],
  categoryFilter: SkillTreeCategory | "all"
): { nodes: Node<SkillTreeNodeData>[]; edges: Edge[] } {
  // Build a lookup map
  const byId = new Map<string, SkillHierarchyNode>();
  allSkills.forEach((s) => byId.set(s.skill_id, s));

  // Filter visible skills
  const visible =
    categoryFilter === "all"
      ? allSkills
      : allSkills.filter(
          (s) => getCategoryFromSkillId(s.skill_id) === categoryFilter
        );

  const visibleIds = new Set(visible.map((s) => s.skill_id));

  // Build child map for all skills
  const childMap = new Map<string, string[]>();
  allSkills.forEach((s) => {
    s.parent_skill_ids.forEach((pid) => {
      if (!childMap.has(pid)) childMap.set(pid, []);
      childMap.get(pid)!.push(s.skill_id);
    });
  });

  // Compute layout with dagre
  const g = new dagre.graphlib.Graph({ multigraph: false });
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({
    rankdir: "TB",
    ranksep: 80,
    nodesep: 20,
    marginx: 40,
    marginy: 40,
  });

  visible.forEach((skill) => {
    g.setNode(skill.skill_id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  });

  // Only add edges where both endpoints are visible
  visible.forEach((skill) => {
    skill.parent_skill_ids.forEach((pid) => {
      if (visibleIds.has(pid)) {
        g.setEdge(pid, skill.skill_id);
      }
    });
  });

  dagre.layout(g);

  const nodes: Node<SkillTreeNodeData>[] = visible.map((skill) => {
    const pos = g.node(skill.skill_id);
    const category = getCategoryFromSkillId(skill.skill_id) ?? "professional";
    const isRoot = skill.parent_skill_ids.length === 0;

    // Resolve parent / child names for tooltip
    const parentNames = skill.parent_skill_ids
      .map((pid) => byId.get(pid)?.canonical_name ?? pid)
      .filter(Boolean);

    const childIds = childMap.get(skill.skill_id) ?? [];
    const childNames = childIds
      .map((cid) => byId.get(cid)?.canonical_name ?? cid)
      .filter(Boolean);

    return {
      id: skill.skill_id,
      type: "skillNode",
      position: {
        x: pos.x - NODE_WIDTH / 2,
        y: pos.y - NODE_HEIGHT / 2,
      },
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
      data: {
        node: skill,
        category,
        unlockState: isRoot ? "available" : "locked",
        parentNames,
        childNames,
      },
    };
  });

  const edgeSet = new Set<string>();
  const edges: Edge[] = [];
  visible.forEach((skill) => {
    skill.parent_skill_ids.forEach((pid) => {
      if (!visibleIds.has(pid)) return;
      const edgeId = `${pid}→${skill.skill_id}`;
      if (edgeSet.has(edgeId)) return;
      edgeSet.add(edgeId);
      edges.push({
        id: edgeId,
        source: pid,
        target: skill.skill_id,
        type: "smoothstep",
        style: { stroke: "#334155", strokeWidth: 1.5, opacity: 0.6 },
      });
    });
  });

  return { nodes, edges };
}
