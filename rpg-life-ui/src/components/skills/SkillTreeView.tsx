import { useMemo } from "react";
import { SkillTree } from "./SkillTree";
import type { Skill } from "@/types/skill";
import type { SkillHierarchyNode } from "@/types/skillHierarchy";

interface SkillTreeViewProps {
  /** Full hierarchy skills from /api/skills/hierarchy */
  skills: Skill[];
}

function isVisibleTreeState(state?: Skill["state"]): boolean {
  return state === undefined || state === "discovered" || state === "activated";
}

/**
 * Adapter wrapper that converts Skill[] (live API data) into
 * SkillHierarchyNode[] and passes it to the existing SkillTree canvas.
 *
 * Skills without hierarchy metadata (hierarchy_level / parent_skill_ids)
 * are filtered out so the dagre layout only processes complete nodes.
 * Only discovered + activated nodes are visible in the tree. For legacy
 * data without state, nodes remain visible as activated by default.
 */
export function SkillTreeView({ skills }: SkillTreeViewProps) {
  const hasHierarchyData = useMemo(
    () =>
      skills.some(
        (s) => s.hierarchy_level !== undefined && s.parent_skill_ids !== undefined
      ),
    [skills]
  );

  const hierarchyNodes = useMemo<SkillHierarchyNode[]>(
    () =>
      skills
        .filter(
          (s): s is Skill & { hierarchy_level: number; parent_skill_ids: string[] } =>
            s.hierarchy_level !== undefined &&
            s.parent_skill_ids !== undefined &&
            isVisibleTreeState(s.state)
        )
        .map((s) => ({
          skill_id: s.skill_id,
          canonical_name: s.canonical_name,
          hierarchy_level: s.hierarchy_level,
          parent_skill_ids: s.parent_skill_ids,
          category: s.category,
          state: s.state,
          user_blocked: s.user_blocked,
        })),
    [skills]
  );

  if (hierarchyNodes.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <p>
          {hasHierarchyData
            ? "No discovered or activated skills to display yet."
            : "No hierarchy data available."}
        </p>
        <p className="text-sm mt-2">
          {hasHierarchyData
            ? "Discover skills through journal entries to reveal them in the tree."
            : "Skills appear here once the global hierarchy is seeded."}
        </p>
      </div>
    );
  }

  return <SkillTree skills={hierarchyNodes} />;
}
