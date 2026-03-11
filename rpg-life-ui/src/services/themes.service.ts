import apiClient, { apiPath } from "@/lib/api";
import { Theme } from "@/types/theme";

export const themesService = {
  getThemes: async (userId: string): Promise<Theme[]> => {
    const { data } = await apiClient.get<Theme[]>(apiPath("/themes"), {
      params: { user_id: userId },
    });
    return data;
  },
};
