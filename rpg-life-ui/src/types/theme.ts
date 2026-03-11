export type BaseThemeName =
  | "Physical"
  | "Mental"
  | "Professional"
  | "Social"
  | "Creative"
  | "Emotional"
  | "Practical"
  | "Intellectual"
  | "Spiritual"
  | "Adventure"
  | "Discipline"
  | "Rest";

export interface Theme {
  theme_id: string;
  user_id: string;
  name: BaseThemeName | string;
  description?: string | null;
  rank?: string | null;
  total_xp: number;
  current_level: number;
  current_level_xp: number;
  next_level_xp: number;
  related_skills_count: number;
  related_skill_names: string[];
  created_at: string;
  updated_at: string;
}
