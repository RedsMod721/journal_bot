import apiClient, { apiPath } from "@/lib/api";
import { Skill } from "@/types/skill";

export const skillsService = {
  getSkills: async (userId: string): Promise<Skill[]> => {
    const { data } = await apiClient.get(apiPath("/skills"), {
      params: { user_id: userId },
    });
    return data;
  },

  getSkillById: async (skillId: string, userId: string): Promise<Skill> => {
    const { data } = await apiClient.get(apiPath(`/skills/${skillId}`), {
      params: { user_id: userId },
    });
    return data;
  },
};
