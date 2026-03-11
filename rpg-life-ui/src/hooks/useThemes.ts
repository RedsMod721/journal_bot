import { useQuery } from "@tanstack/react-query";
import { themesService } from "@/services/themes.service";

export function useThemes(userId: string) {
  return useQuery({
    queryKey: ["themes", userId],
    queryFn: () => themesService.getThemes(userId),
    enabled: !!userId,
    staleTime: 5 * 60 * 1000,
  });
}
