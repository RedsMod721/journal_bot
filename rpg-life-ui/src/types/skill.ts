export type SkillState =
  | "locked"
  | "discovered"
  | "unlocked_hidden"
  | "activated";

export interface Skill {
  skill_id: string;
  user_id?: string;
  canonical_name: string;
  category: string;
  total_xp: number;
  current_level: number;
  rank?: string | null;
  /** Present from /api/skills; may be absent from /api/skills/hierarchy */
  current_level_xp?: number;
  /** Present from /api/skills; may be absent from /api/skills/hierarchy */
  next_level_xp?: number;
  last_practiced_at?: string; // ISO datetime
  created_at?: string;

  // Hierarchy fields — present from /api/skills/hierarchy
  hierarchy_level?: number;
  parent_skill_ids?: string[];
  parent_skill_names?: string[];
  state?: SkillState;
  user_blocked?: boolean;
  discovered_at?: string;
  unlocked_at?: string;
  activated_at?: string;

  // Future fields (optional - will be used in Weeks 5-8)
  staleness_days?: number;
  retained_xp_pct?: number;
  decay_rate?: number;
}

export type SkillCategory =
  | "Adventure"
  | "Physical"
  | "Mental"
  | "Professional"
  | "Creative"
  | "Social"
  | "Rest"
  | "Growth";

export const SKILL_CATEGORY_COLORS: Record<SkillCategory, string> = {
  Adventure: "bg-orange-500/10 text-orange-500 border-orange-500/20",
  Physical: "bg-red-500/10 text-red-500 border-red-500/20",
  Mental: "bg-blue-500/10 text-blue-500 border-blue-500/20",
  Professional: "bg-purple-500/10 text-purple-500 border-purple-500/20",
  Creative: "bg-pink-500/10 text-pink-500 border-pink-500/20",
  Social: "bg-green-500/10 text-green-500 border-green-500/20",
  Rest: "bg-cyan-500/10 text-cyan-500 border-cyan-500/20",
  Growth: "bg-yellow-500/10 text-yellow-500 border-yellow-500/20",
};
