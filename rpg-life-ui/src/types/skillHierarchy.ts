import type { SkillState } from "@/types/skill";

export type SkillTreeCategory =
  | "adventure"
  | "creative"
  | "mental"
  | "physical"
  | "professional"
  | "social";

export interface SkillHierarchyNode {
  skill_id: string;
  canonical_name: string;
  hierarchy_level: number;
  parent_skill_ids: string[];
  category?: string;
  state?: SkillState;
  user_blocked?: boolean;
}

export type SkillTreeDisplayState = "discovered" | "activated";

// Must extend Record<string, unknown> for @xyflow/react Node<TData> constraint
export interface SkillTreeNodeData extends Record<string, unknown> {
  node: SkillHierarchyNode;
  category: SkillTreeCategory;
  l1SkillIds: string[];
  l1SkillLabels: string[];
  state: SkillTreeDisplayState;
  userBlocked: boolean;
  /** Names of parent skills required to unlock this */
  parentNames: string[];
  /** Names of skills this unlocks */
  childNames: string[];
}

// Colors indexed by category — used as inline styles so they work inside react-flow
export const TREE_CATEGORY_STYLES: Record<
  SkillTreeCategory,
  { bg: string; border: string; text: string; dimBg: string; dimBorder: string }
> = {
  adventure: {
    bg: "#f97316",
    border: "#c2410c",
    text: "#fff",
    dimBg: "#431407",
    dimBorder: "#9a3412",
  },
  creative: {
    bg: "#db2777",
    border: "#9d174d",
    text: "#fff",
    dimBg: "#4a0d29",
    dimBorder: "#831843",
  },
  mental: {
    bg: "#2563eb",
    border: "#1e40af",
    text: "#fff",
    dimBg: "#0d1f4a",
    dimBorder: "#1e3a8a",
  },
  physical: {
    bg: "#dc2626",
    border: "#991b1b",
    text: "#fff",
    dimBg: "#450a0a",
    dimBorder: "#7f1d1d",
  },
  professional: {
    bg: "#7c3aed",
    border: "#5b21b6",
    text: "#fff",
    dimBg: "#2d1b69",
    dimBorder: "#4c1d95",
  },
  social: {
    bg: "#16a34a",
    border: "#14532d",
    text: "#fff",
    dimBg: "#052e16",
    dimBorder: "#14532d",
  },
};

export const CATEGORY_LABELS: Record<SkillTreeCategory, string> = {
  adventure: "Adventure",
  creative: "Creative",
  mental: "Mental",
  physical: "Physical",
  professional: "Professional",
  social: "Social",
};

export function normalizeSkillTreeCategory(
  category: string | null | undefined
): SkillTreeCategory | null {
  const value = (category ?? "").trim().toLowerCase();
  if (
    value === "adventure" ||
    value === "creative" ||
    value === "mental" ||
    value === "physical" ||
    value === "professional" ||
    value === "social"
  ) {
    return value as SkillTreeCategory;
  }
  return null;
}

export function getCategoryFromSkillId(
  skillId: string
): SkillTreeCategory | null {
  const prefix = skillId.replace(/^skill_/, "").split("_")[0];
  if (
    prefix === "adventure" ||
    prefix === "creative" ||
    prefix === "mental" ||
    prefix === "physical" ||
    prefix === "professional" ||
    prefix === "social"
  ) {
    return prefix as SkillTreeCategory;
  }
  return null;
}
