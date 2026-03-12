import apiClient, { apiPath } from "@/lib/api";
import { Theme } from "@/types/theme";

function missingRelatedSkillNames(themes: Theme[]): boolean {
  return (
    themes.length > 0 &&
    themes.some((theme) => theme.related_skills_count > 0) &&
    themes.every((theme) => !Array.isArray(theme.related_skill_names))
  );
}

async function fetchThemesFromLocalFallback(userId: string): Promise<Theme[] | null> {
  const baseURL = String(apiClient.defaults.baseURL ?? "");
  const isLocal8000 =
    baseURL.includes("localhost:8000") || baseURL.includes("127.0.0.1:8000");

  if (!isLocal8000) {
    return null;
  }

  const fallbackBaseURL = baseURL.replace(":8000", ":8002");
  if (fallbackBaseURL === baseURL) {
    return null;
  }

  try {
    const { data } = await apiClient.get<Theme[]>(`${fallbackBaseURL}${apiPath("/themes")}`, {
      params: { user_id: userId },
    });
    return Array.isArray(data) ? data : null;
  } catch {
    return null;
  }
}

export const themesService = {
  getThemes: async (userId: string): Promise<Theme[]> => {
    const { data } = await apiClient.get<Theme[]>(apiPath("/themes"), {
      params: { user_id: userId },
    });

    if (missingRelatedSkillNames(data)) {
      const fallbackData = await fetchThemesFromLocalFallback(userId);
      if (fallbackData && !missingRelatedSkillNames(fallbackData)) {
        return fallbackData;
      }
    }

    return data;
  },
};
