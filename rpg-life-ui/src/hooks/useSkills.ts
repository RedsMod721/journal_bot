import { useQuery } from "@tanstack/react-query";
import { skillsService } from "@/services/skills.service";

export function useSkills(userId: string) {
  return useQuery({
    queryKey: ["skills", userId],
    queryFn: () => skillsService.getSkills(userId),
    enabled: !!userId,
    staleTime: 5 * 60 * 1000,
  });
}

export function useSkill(skillId: string, userId: string) {
  return useQuery({
    queryKey: ["skill", skillId, userId],
    queryFn: () => skillsService.getSkillById(skillId, userId),
    enabled: !!skillId && !!userId,
  });
}
