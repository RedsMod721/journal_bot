import apiClient, { apiPath } from "@/lib/api";
import { Quest } from "@/types/quest";

export const questsService = {
  getQuests: async (userId: string, status?: string): Promise<Quest[]> => {
    const params: Record<string, string> = { user_id: userId };
    if (status) params.status = status;

    const { data } = await apiClient.get(apiPath("/quests"), { params });
    return data;
  },

  getQuestById: async (questId: string, userId: string): Promise<Quest> => {
    const { data } = await apiClient.get(apiPath(`/quests/${questId}`), {
      params: { user_id: userId },
    });
    return data;
  },

  completeQuest: async (questId: string, userId: string): Promise<void> => {
    await apiClient.post(apiPath(`/quests/${questId}/complete`), null, {
      params: { user_id: userId },
    });
  },
};
