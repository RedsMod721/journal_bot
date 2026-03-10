export type QuestType = "one_time" | "cumulative" | "recursive" | "streak";

export type QuestStatus = "active" | "completed" | "failed" | "abandoned";
export type QuestScope = "instant" | "longterm";

export interface QuestSkillHierarchyRef {
  source_skill_id: string;
  canonical_name: string;
  hierarchy_level?: number | null;
}

export interface Quest {
  quest_id: string;
  user_id: string;
  quest_name: string;
  description?: string;
  related_skill_name?: string;
  related_skill_source_id?: string;
  related_skill_hierarchy_level?: number | null;
  related_skill_ancestor_skills?: QuestSkillHierarchyRef[];
  related_themes?: string[];
  quest_scope?: QuestScope;
  quest_type: QuestType;
  status: QuestStatus;
  success_criteria: Record<string, any>;
  current_value?: number;
  target_value?: number;
  created_at: string;
  completed_at?: string;

  // Future fields (optional)
  difficulty?: number;
  template_id?: string;
  user_preference?: string;
}

export const QUEST_TYPE_LABELS: Record<QuestType, string> = {
  one_time: "One-Time",
  cumulative: "Cumulative",
  recursive: "Recurring",
  streak: "Streak",
};

export const QUEST_TYPE_COLORS: Record<QuestType, string> = {
  one_time: "bg-blue-500/10 text-blue-500 border-blue-500/20",
  cumulative: "bg-purple-500/10 text-purple-500 border-purple-500/20",
  recursive: "bg-green-500/10 text-green-500 border-green-500/20",
  streak: "bg-orange-500/10 text-orange-500 border-orange-500/20",
};
