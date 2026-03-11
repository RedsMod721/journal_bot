import { useMutation, useQueryClient } from "@tanstack/react-query";
import apiClient from "@/lib/api";
import { useToast } from "@/hooks/use-toast";

interface BlockSkillParams {
  skill_id: string;
  user_id: string;
  blocked: boolean;
}

export function useBlockSkill() {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: async ({ skill_id, user_id, blocked }: BlockSkillParams) => {
      const { data } = await apiClient.post(
        `/api/skills/${skill_id}/block`,
        { blocked },
        { params: { user_id } }
      );
      return data;
    },
    onSuccess: (data, variables) => {
      queryClient.invalidateQueries({ queryKey: ["skillHierarchy"] });
      queryClient.invalidateQueries({ queryKey: ["skills"] });

      toast({
        title: variables.blocked ? "Skill Blocked" : "Skill Unblocked",
        description: data.message,
      });
    },
    onError: (error: Error) => {
      toast({
        variant: "destructive",
        title: "Failed to Update Skill",
        description: error.message,
      });
    },
  });
}
