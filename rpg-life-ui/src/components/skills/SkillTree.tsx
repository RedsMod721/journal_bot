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
import type { SkillHierarchyNode, SkillTreeCategory, SkillTreeNodeData } from "@/types/skillHierarchy";
import { TREE_CATEGORY_STYLES, CATEGORY_LABELS } from "@/types/skillHierarchy";

const NODE_TYPES: NodeTypes = { skillNode: SkillTreeNode };

type CategoryOption = SkillTreeCategory | "all";

const CATEGORIES: Array<{ value: CategoryOption; label: string; color: string }> = [
  { value: "all",          label: "All",                           color: "#64748b" },
  { value: "physical",    label: CATEGORY_LABELS.physical,    color: TREE_CATEGORY_STYLES.physical.bg    },
  { value: "mental",      label: CATEGORY_LABELS.mental,      color: TREE_CATEGORY_STYLES.mental.bg      },
  { value: "professional",label: CATEGORY_LABELS.professional,color: TREE_CATEGORY_STYLES.professional.bg},
  { value: "creative",    label: CATEGORY_LABELS.creative,    color: TREE_CATEGORY_STYLES.creative.bg    },
  { value: "social",      label: CATEGORY_LABELS.social,      color: TREE_CATEGORY_STYLES.social.bg      },
];

interface SkillTreeProps {
  skills: SkillHierarchyNode[];
}

export function SkillTree({ skills }: SkillTreeProps) {
  const [category, setCategory] = useState<CategoryOption>("professional");

  const { nodes, edges } = useMemo(
    () => buildSkillTreeGraph(skills, category),
    [skills, category]
  );

  const miniMapNodeColor = useCallback((node: Node) => {
    const d = (node as SkillNode).data as SkillTreeNodeData;
    const style = TREE_CATEGORY_STYLES[d?.category ?? "professional"];
    return d?.unlockState === "locked" ? style.dimBg : style.bg;
  }, []);

  return (
    <div className="flex flex-col gap-4">
      {/* Category filter pills */}
      <div className="flex items-center gap-2 flex-wrap">
        {CATEGORIES.map((cat) => (
          <button
            key={cat.value}
            onClick={() => setCategory(cat.value)}
            className="px-3 py-1.5 rounded-full text-xs font-medium transition-all duration-150 border"
            style={
              category === cat.value
                ? { background: cat.color, borderColor: cat.color, color: "#fff",
                    boxShadow: `0 0 12px 2px ${cat.color}55` }
                : { background: "transparent", borderColor: `${cat.color}55`, color: cat.color }
            }
          >
            {cat.label}
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
          Full color = available
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-3 rounded-sm" style={{
            background: TREE_CATEGORY_STYLES.professional.dimBg,
            border: `1px solid ${TREE_CATEGORY_STYLES.professional.dimBorder}`,
          }} />
          Dimmed = locked
        </div>
        <span>Hover a node to see requirements &amp; unlocks</span>
      </div>

      {/* Canvas — key on provider so the whole context resets when category changes */}
      <div style={{ width: "100%", height: 640, borderRadius: 12, overflow: "hidden", border: "1px solid hsl(var(--border))", background: "#080f1a" }}>
        <ReactFlowProvider key={category}>
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
