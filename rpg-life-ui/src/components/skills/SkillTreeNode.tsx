import { memo, useState } from "react";
import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { Eye, Lock, Star, Zap } from "lucide-react";
import type { SkillTreeNodeData } from "@/types/skillHierarchy";
import { TREE_CATEGORY_STYLES } from "@/types/skillHierarchy";

const UNLOCK_RANK_REQUIRED = 5; // placeholder until backend drives this

// Concrete node type for react-flow generic constraints
export type SkillNode = Node<SkillTreeNodeData, "skillNode">;

interface TooltipProps {
  data: SkillTreeNodeData;
}

function formatL1SkillLine(labels: string[]): string {
  if (labels.length === 0) return "Unclassified";
  if (labels.length === 1) return labels[0];
  return `${labels[0]} +${labels.length - 1}`;
}

function SkillTooltip({ data }: TooltipProps) {
  const { node, category, l1SkillLabels, parentNames, childNames } = data;
  const style = TREE_CATEGORY_STYLES[category];

  return (
    <div
      className="absolute z-50 bottom-[calc(100%+12px)] left-1/2 -translate-x-1/2 w-72 rounded-xl border border-white/10 shadow-2xl text-sm pointer-events-none"
      style={{ background: "#0f172a" }}
    >
      {/* Header */}
      <div className="rounded-t-xl px-4 py-3" style={{ background: style.bg }}>
        <div className="font-bold text-white text-base leading-tight">
          {node.canonical_name}
        </div>
        <div className="text-white/70 text-xs mt-0.5">
          {formatL1SkillLine(l1SkillLabels)} · Level {node.hierarchy_level} skill
        </div>
      </div>

      <div className="px-4 py-3 space-y-3">
        {/* State */}
        <div className="flex items-center gap-2">
          {data.state === "discovered" ? (
            <>
              <Eye className="w-3.5 h-3.5 text-slate-400 shrink-0" />
              <span className="text-slate-400">Discovered</span>
            </>
          ) : (
            <>
              <Zap className="w-3.5 h-3.5 text-green-400 shrink-0" />
              <span className="text-green-400">Activated</span>
            </>
          )}
        </div>

        {/* Requirements */}
        {parentNames.length > 0 && (
          <div>
            <div className="text-slate-500 text-xs uppercase tracking-wider mb-1">
              Requires (rank {UNLOCK_RANK_REQUIRED}+)
            </div>
            <ul className="space-y-0.5">
              {parentNames.map((name) => (
                <li
                  key={name}
                  className="flex items-center gap-1.5 text-slate-300"
                >
                  <span className="w-1 h-1 rounded-full bg-slate-500 shrink-0" />
                  {name}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Unlocks */}
        {childNames.length > 0 && (
          <div>
            <div className="text-slate-500 text-xs uppercase tracking-wider mb-1">
              Unlocks ({childNames.length})
            </div>
            <ul className="space-y-0.5">
              {childNames.slice(0, 5).map((name) => (
                <li
                  key={name}
                  className="flex items-center gap-1.5 text-slate-300"
                >
                  <span
                    className="w-1 h-1 rounded-full shrink-0"
                    style={{ background: style.bg }}
                  />
                  {name}
                </li>
              ))}
              {childNames.length > 5 && (
                <li className="text-slate-500 text-xs">
                  +{childNames.length - 5} more…
                </li>
              )}
            </ul>
          </div>
        )}
      </div>

      {/* Arrow */}
      <div
        className="absolute top-full left-1/2 -translate-x-1/2 w-0 h-0"
        style={{
          borderLeft: "8px solid transparent",
          borderRight: "8px solid transparent",
          borderTop: "8px solid #1e293b",
        }}
      />
    </div>
  );
}

export const SkillTreeNode = memo(function SkillTreeNode({
  data,
}: NodeProps<SkillNode>) {
  const [hovered, setHovered] = useState(false);
  const { node, category, state, userBlocked } = data;
  const style = TREE_CATEGORY_STYLES[category];
  const isDiscovered = state === "discovered";
  const isRoot = node.hierarchy_level === 1;

  const bg = isDiscovered ? style.dimBg : style.bg;
  const border = isDiscovered ? style.dimBorder : style.border;
  const opacity = isDiscovered ? 0.55 : 1;

  return (
    <div
      className="relative"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {hovered && <SkillTooltip data={data} />}

      <Handle type="target" position={Position.Top} className="!opacity-0" />

      {userBlocked && (
        <div
          className="absolute -top-1.5 -right-1.5 z-20 w-4 h-4 rounded-full border flex items-center justify-center pointer-events-none"
          style={{ background: "#7f1d1d", borderColor: "#ef4444" }}
          aria-label="Blocked skill"
          title="Blocked skill"
        >
          <Lock className="w-2.5 h-2.5 text-white" />
        </div>
      )}

      <div
        className="flex items-center gap-2 px-3 rounded-lg cursor-default select-none transition-all duration-150"
        style={{
          width: 168,
          height: 52,
          background: bg,
          border: `1.5px solid ${border}`,
          opacity,
          boxShadow:
            hovered && !isDiscovered
              ? `0 0 16px 2px ${style.bg}55`
              : isRoot
              ? `0 0 10px 1px ${style.bg}33`
              : "none",
        }}
      >
        <div className="shrink-0">
          {isDiscovered ? (
            <Eye className="w-3.5 h-3.5 text-white/40" />
          ) : isRoot ? (
            <Star className="w-4 h-4 text-white/90" />
          ) : (
            <Zap className="w-3.5 h-3.5 text-white/90" />
          )}
        </div>

        <span
          className="text-xs font-medium leading-tight line-clamp-2"
          style={{ color: isDiscovered ? "rgba(255,255,255,0.45)" : "#fff" }}
        >
          {node.canonical_name}
        </span>
      </div>

      <Handle type="source" position={Position.Bottom} className="!opacity-0" />
    </div>
  );
});
