import { useQuery } from "@tanstack/react-query";
import { themesService } from "@/services/themes.service";

export function useThemes(userId: string) {
  return useQuery({
    queryKey: ["themes", userId],
    queryFn: async () => {
      const themes = await themesService.getThemes(userId);
      return themes.map((theme) => ({
        ...theme,
        related_skill_names: Array.isArray(theme.related_skill_names)
          ? theme.related_skill_names.filter(
              (name): name is string => typeof name === "string" && name.trim().length > 0
            )
          : [],
      }));
    },
    enabled: !!userId,
    staleTime: 5 * 60 * 1000,
  });
}
