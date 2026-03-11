import { useMemo, useState, useCallback } from "react";
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  MiniMap,
  BackgroundVariant,
  type NodeTypes,
  type Node,
} from "@xyflow/react";

import { SkillTreeNode } from "./SkillTreeNode";
import type { SkillNode } from "./SkillTreeNode";
import { buildSkillTreeGraph } from "@/lib/skillTreeLayout";
import type {
  SkillHierarchyNode,
  SkillTreeNodeData,
} from "@/types/skillHierarchy";
import {
  TREE_CATEGORY_STYLES,
  getCategoryFromSkillId,
} from "@/types/skillHierarchy";
import { buildL1SkillResolver } from "@/lib/skillHierarchyRoots";

const NODE_TYPES: NodeTypes = { skillNode: SkillTreeNode };

type L1SkillFilter = "all" | string;

function getL1FilterColor(l1SkillId: string): string {
  if (l1SkillId === "skill_physical_adventure") {
    return "#f97316";
  }
  const category = getCategoryFromSkillId(l1SkillId) ?? "professional";
  return TREE_CATEGORY_STYLES[category].bg;
}

interface SkillTreeProps {
  skills: SkillHierarchyNode[];
}

export function SkillTree({ skills }: SkillTreeProps) {
  const [l1SkillFilter, setL1SkillFilter] = useState<L1SkillFilter>("all");
  const l1SkillResolver = useMemo(() => buildL1SkillResolver(skills), [skills]);
  const l1Filters = useMemo(
    () => [
      { value: "all" as const, label: "All", color: "#64748b" },
      ...l1SkillResolver.getL1SkillOptions().map((l1Skill) => ({
        value: l1Skill.skillId,
        label: l1Skill.label,
        color: getL1FilterColor(l1Skill.skillId),
      })),
    ],
    [l1SkillResolver]
  );

  const { nodes, edges } = useMemo(
    () => buildSkillTreeGraph(skills, l1SkillFilter, l1SkillResolver),
    [skills, l1SkillFilter, l1SkillResolver]
  );

  const miniMapNodeColor = useCallback((node: Node) => {
    const d = (node as SkillNode).data as SkillTreeNodeData;
    const style = TREE_CATEGORY_STYLES[d?.category ?? "professional"];
    return d?.state === "discovered" ? style.dimBg : style.bg;
  }, []);

  return (
    <div className="flex flex-col gap-4">
      {/* L1 skill filter pills */}
      <div className="flex items-center gap-2 flex-wrap">
        {l1Filters.map((l1Skill) => (
          <button
            key={l1Skill.value}
            onClick={() => setL1SkillFilter(l1Skill.value)}
            className="px-3 py-1.5 rounded-full text-xs font-medium transition-all duration-150 border"
            style={
              l1SkillFilter === l1Skill.value
                ? {
                    background: l1Skill.color,
                    borderColor: l1Skill.color,
                    color: "#fff",
                    boxShadow: `0 0 12px 2px ${l1Skill.color}55`,
                  }
                : {
                    background: "transparent",
                    borderColor: `${l1Skill.color}55`,
                    color: l1Skill.color,
                  }
            }
          >
            {l1Skill.label}
          </button>
        ))}
        <span className="ml-2 text-xs text-muted-foreground">
          {nodes.length} skills · {edges.length} connections
        </span>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 text-xs text-muted-foreground flex-wrap">
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-3 rounded-sm" style={{ background: TREE_CATEGORY_STYLES.professional.bg }} />
          Full color = activated
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-3 rounded-sm" style={{
            background: TREE_CATEGORY_STYLES.professional.dimBg,
            border: `1px solid ${TREE_CATEGORY_STYLES.professional.dimBorder}`,
          }} />
          Dimmed = discovered
        </div>
        <div className="flex items-center gap-1.5">
          <div
            className="w-5 h-0"
            style={{ borderTop: "2px dashed #64748b", opacity: 0.9 }}
          />
          Dotted line = same-level relation
        </div>
        <span>Hover a node to see requirements &amp; unlocks</span>
      </div>

      {/* Canvas — key on provider so the whole context resets when L1 filter changes */}
      <div style={{ width: "100%", height: 640, borderRadius: 12, overflow: "hidden", border: "1px solid hsl(var(--border))", background: "#080f1a" }}>
        <ReactFlowProvider key={l1SkillFilter}>
          <ReactFlow
            defaultNodes={nodes}
            defaultEdges={edges}
            nodeTypes={NODE_TYPES}
            colorMode="dark"
            fitView
            fitViewOptions={{ padding: 0.12 }}
            minZoom={0.05}
            maxZoom={2}
            nodesDraggable={false}
            nodesConnectable={false}
            elementsSelectable={false}
            panOnScroll
            panOnDrag
            zoomOnScroll
            zoomOnPinch
            proOptions={{ hideAttribution: true }}
            style={{ background: "transparent" }}
          >
            <Background variant={BackgroundVariant.Dots} gap={24} size={1} color="#1e293b" />
            <Controls showInteractive={false} />
            <MiniMap
              nodeColor={miniMapNodeColor}
              maskColor="rgba(0,0,0,0.75)"
              style={{ background: "#0f172a", border: "1px solid #1e293b" }}
            />
          </ReactFlow>
        </ReactFlowProvider>
      </div>
    </div>
  );
}
