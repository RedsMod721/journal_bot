import { useMutation, useQuery, useQueryClient, useInfiniteQuery } from "@tanstack/react-query";
import { arcsService, CreateEventArcData } from "@/services/arcs.service";
import { useToast } from "@/hooks/use-toast";

export function useCurrentArc(userId: string) {
  return useQuery({
    queryKey: ["arcs", "current", userId],
    queryFn: () => arcsService.getCurrent(userId),
    enabled: !!userId,
    staleTime: 60 * 1000,
  });
}

export function useArcHistory(userId: string) {
  return useInfiniteQuery({
    queryKey: ["arcs", "history", userId],
    queryFn: ({ pageParam }) =>
      arcsService.getHistory(userId, pageParam as string | undefined),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: !!userId,
    staleTime: 2 * 60 * 1000,
  });
}

export function useCreateEventArc() {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: ({ userId, data }: { userId: string; data: CreateEventArcData }) =>
      arcsService.createEvent(userId, data),
    onSuccess: (_arc, { userId }) => {
      queryClient.invalidateQueries({ queryKey: ["arcs", "current", userId] });
      queryClient.invalidateQueries({ queryKey: ["arcs", "history", userId] });
      toast({
        title: "Event Arc Created",
        description: "Your new event arc is now active.",
      });
    },
    onError: (error: Error) => {
      toast({
        variant: "destructive",
        title: "Failed to Create Arc",
        description: error.message,
      });
    },
  });
}

export function useActivateVacation() {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: ({ userId, duration_days }: { userId: string; duration_days?: number }) =>
      arcsService.activateVacation(userId, duration_days),
    onSuccess: (_arc, { userId }) => {
      queryClient.invalidateQueries({ queryKey: ["arcs", "current", userId] });
      toast({
        title: "Vacation Mode Activated",
        description: "Skill decay is paused. Enjoy your break!",
      });
    },
    onError: (error: Error) => {
      toast({
        variant: "destructive",
        title: "Failed to Activate Vacation",
        description: error.message,
      });
    },
  });
}

export function useEndVacation() {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: ({ userId }: { userId: string }) => arcsService.endVacation(userId),
    onSuccess: (_arc, { userId }) => {
      queryClient.invalidateQueries({ queryKey: ["arcs", "current", userId] });
      queryClient.invalidateQueries({ queryKey: ["arcs", "history", userId] });
      toast({
        title: "Vacation Ended",
        description: "Welcome back! Your previous arc has resumed.",
      });
    },
    onError: (error: Error) => {
      toast({
        variant: "destructive",
        title: "Failed to End Vacation",
        description: error.message,
      });
    },
  });
}

export function useEndArc() {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: ({ userId, arcId }: { userId: string; arcId: string }) =>
      arcsService.endArc(userId, arcId),
    onSuccess: (_arc, { userId }) => {
      queryClient.invalidateQueries({ queryKey: ["arcs", "current", userId] });
      queryClient.invalidateQueries({ queryKey: ["arcs", "history", userId] });
      toast({ title: "Arc Completed", description: "Great work!" });
    },
    onError: (error: Error) => {
      toast({
        variant: "destructive",
        title: "Failed to End Arc",
        description: error.message,
      });
    },
  });
}

export function useAbandonArc() {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: ({ userId, arcId }: { userId: string; arcId: string }) =>
      arcsService.abandonArc(userId, arcId),
    onSuccess: (_arc, { userId }) => {
      queryClient.invalidateQueries({ queryKey: ["arcs", "current", userId] });
      queryClient.invalidateQueries({ queryKey: ["arcs", "history", userId] });
      toast({ title: "Arc Abandoned" });
    },
    onError: (error: Error) => {
      toast({
        variant: "destructive",
        title: "Failed to Abandon Arc",
        description: error.message,
      });
    },
  });
}
