import { useQuery } from "@tanstack/react-query";
import { forgivenessService } from "@/services/forgiveness.service";

export function useForgivenessPresets() {
  return useQuery({
    queryKey: ["forgivenessPresets"],
    queryFn: forgivenessService.getPresets,
    staleTime: Infinity,
  });
}

export function useForgivenessConfig(userId?: string) {
  return useQuery({
    queryKey: ["forgivenessConfig", userId],
    queryFn: () => forgivenessService.getConfig(userId!),
    enabled: !!userId,
    staleTime: 2 * 60 * 1000,
    refetchOnMount: "always",
    refetchOnWindowFocus: true,
  });
}
