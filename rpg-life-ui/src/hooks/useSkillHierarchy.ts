import { useQuery } from "@tanstack/react-query";
import apiClient from "@/lib/api";
import { Skill } from "@/types/skill";
import {
  CATEGORY_LABELS,
  getCategoryFromSkillId,
  type SkillTreeCategory,
} from "@/types/skillHierarchy";

function toCategoryLabel(value: SkillTreeCategory | null): string {
  return value ? CATEGORY_LABELS[value] : "Growth";
}

export function useSkillHierarchy(userId: string) {
  return useQuery({
    queryKey: ["skillHierarchy", userId],
    queryFn: async () => {
      const { data } = await apiClient.get<Skill[]>("/api/skills/hierarchy", {
        params: { user_id: userId },
      });
      return data.map((skill) => ({
        ...skill,
        category:
          (skill.category ?? "").trim() ||
          toCategoryLabel(getCategoryFromSkillId(skill.skill_id)),
      }));
    },
    enabled: !!userId,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}
