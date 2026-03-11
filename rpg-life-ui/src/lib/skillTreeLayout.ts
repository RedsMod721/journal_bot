import dagre from "@dagrejs/dagre";
import { type Edge, type Node, Position } from "@xyflow/react";
import type {
  SkillHierarchyNode,
  SkillTreeNodeData,
} from "@/types/skillHierarchy";
import { getCategoryFromSkillId } from "@/types/skillHierarchy";
import {
  buildL1SkillResolver,
  type L1SkillResolver,
} from "@/lib/skillHierarchyRoots";

const NODE_WIDTH = 168;
const NODE_HEIGHT = 52;
const LEVEL_VERTICAL_STEP = NODE_HEIGHT + 60;
const LEVEL_TOP_OFFSET = 40;

function toAbsoluteLevelY(level: number): number {
  const safeLevel = Number.isFinite(level) && level > 0 ? Math.floor(level) : 1;
  return LEVEL_TOP_OFFSET + (safeLevel - 1) * LEVEL_VERTICAL_STEP;
}

function isVisibleInTree(skill: SkillHierarchyNode): boolean {
  return (
    skill.state === undefined ||
    skill.state === "discovered" ||
    skill.state === "activated"
  );
}

function toDisplayState(skill: SkillHierarchyNode): "discovered" | "activated" {
  return skill.state === "discovered" ? "discovered" : "activated";
}

function getHierarchyLevel(
  skillById: Map<string, SkillHierarchyNode>,
  skillId: string
): number | null {
  const level = skillById.get(skillId)?.hierarchy_level;
  return typeof level === "number" ? level : null;
}

function isStrictDownwardHierarchyEdge(
  skillById: Map<string, SkillHierarchyNode>,
  parentId: string,
  childId: string
): boolean {
  const parentLevel = getHierarchyLevel(skillById, parentId);
  const childLevel = getHierarchyLevel(skillById, childId);
  if (parentLevel === null || childLevel === null) return true;
  return parentLevel < childLevel;
}

export function buildSkillTreeGraph(
  allSkills: SkillHierarchyNode[],
  l1SkillFilter: string | "all",
  l1SkillResolver: L1SkillResolver = buildL1SkillResolver(allSkills)
): { nodes: Node<SkillTreeNodeData>[]; edges: Edge[] } {
  const stateVisibleSkills = allSkills.filter(isVisibleInTree);

  // Build a lookup map from state-visible skills
  const byId = new Map<string, SkillHierarchyNode>();
  stateVisibleSkills.forEach((s) => byId.set(s.skill_id, s));

  // Filter visible skills by selected L1 roots
  const visible =
    l1SkillFilter === "all"
      ? stateVisibleSkills
      : stateVisibleSkills.filter(
          (s) => l1SkillResolver.getL1SkillIds(s.skill_id).includes(l1SkillFilter)
        );

  const visibleIds = new Set(visible.map((s) => s.skill_id));

  // Build child map for state-visible skills
  const childMap = new Map<string, string[]>();
  stateVisibleSkills.forEach((s) => {
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

  // Only add strict top-down hierarchy edges to dagre.
  // Same-level links are rendered later as dotted relations and should not
  // impact rank assignment (prevents row overlap after absolute-Y mapping).
  visible.forEach((skill) => {
    skill.parent_skill_ids.forEach((pid) => {
      if (
        visibleIds.has(pid) &&
        isStrictDownwardHierarchyEdge(byId, pid, skill.skill_id)
      ) {
        g.setEdge(pid, skill.skill_id);
      }
    });
  });

  dagre.layout(g);

  const nodes: Node<SkillTreeNodeData>[] = visible.map((skill) => {
    const pos = g.node(skill.skill_id) ?? { x: 0, y: 0 };
    const category = getCategoryFromSkillId(skill.skill_id) ?? "professional";
    const l1SkillIds = l1SkillResolver.getL1SkillIds(skill.skill_id);
    const l1SkillLabels = l1SkillIds
      .map((l1SkillId) => l1SkillResolver.getL1SkillLabel(l1SkillId) ?? l1SkillId)
      .filter((label) => label.length > 0);

    // Resolve parent / child names for tooltip
    const parentNames = skill.parent_skill_ids
      .filter((pid) => byId.has(pid))
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
        // Preserve absolute hierarchy depth under filtering:
        // nodes with hidden parents must stay on their own level row.
        y: toAbsoluteLevelY(skill.hierarchy_level),
      },
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
      data: {
        node: skill,
        category,
        l1SkillIds,
        l1SkillLabels,
        state: toDisplayState(skill),
        userBlocked: Boolean(skill.user_blocked),
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
      const parentLevel = getHierarchyLevel(byId, pid);
      const childLevel = getHierarchyLevel(byId, skill.skill_id);
      const isSameLevelRelation =
        parentLevel !== null && childLevel !== null && parentLevel === childLevel;
      edges.push({
        id: edgeId,
        source: pid,
        target: skill.skill_id,
        type: "smoothstep",
        style: isSameLevelRelation
          ? {
              stroke: "#64748b",
              strokeWidth: 1.6,
              opacity: 0.85,
              strokeDasharray: "4 4",
            }
          : { stroke: "#334155", strokeWidth: 1.5, opacity: 0.6 },
      });
    });
  });

  return { nodes, edges };
}
