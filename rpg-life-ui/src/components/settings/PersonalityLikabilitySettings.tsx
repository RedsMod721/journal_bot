import { useEffect, useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Slider } from "@/components/ui/slider";
import { useUser } from "@/contexts/UserContext";
import {
  usePersonalityState,
  useUpdateLikabilityScores,
} from "@/hooks/usePersonalityState";
import { useToast } from "@/hooks/use-toast";
import {
  PERSONALITY_IDS,
  type LikabilityScores,
  type PersonalityId,
} from "@/services/personality.service";

const DEFAULT_LIKABILITY_SCORES: LikabilityScores = {
  observer: 80,
  therapist: 70,
  coach: 60,
  sassy: 50,
  wargod: 40,
  raphael: 60,
};

const PERSONALITY_LABELS: Record<PersonalityId, string> = {
  observer: "Observer",
  therapist: "Therapist",
  coach: "Coach",
  sassy: "Sassy",
  wargod: "Wargod",
  raphael: "Raphael",
};

const PERSONALITY_DESCRIPTIONS: Record<PersonalityId, string> = {
  observer: "Neutral baseline voice for steady feedback.",
  therapist: "Supportive and reflective guidance when things feel heavy.",
  coach: "Achievement-focused momentum and encouragement.",
  sassy: "Playful pressure when you want sharper banter.",
  wargod: "High-intensity celebration for major wins.",
  raphael: "Philosophical framing for meaning and regression arcs.",
};

function getLoadErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Unknown error";
}

export function PersonalityLikabilitySettings() {
  const { user } = useUser();
  const userId = user?.id ?? "";
  const { toast } = useToast();
  const {
    data: state,
    isLoading,
    error,
  } = usePersonalityState(userId);
  const updateLikabilityMutation = useUpdateLikabilityScores(userId);

  const [savedScores, setSavedScores] = useState(DEFAULT_LIKABILITY_SCORES);
  const [pendingScores, setPendingScores] = useState(DEFAULT_LIKABILITY_SCORES);

  useEffect(() => {
    if (!state) {
      return;
    }

    setSavedScores(state.likability_scores);
    setPendingScores(state.likability_scores);
  }, [state]);

  const isBusy = updateLikabilityMutation.isPending;
  const isDirty =
    JSON.stringify(savedScores) !== JSON.stringify(pendingScores);

  if (!userId) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Personality Likability</CardTitle>
          <CardDescription>Select a user to edit likability settings.</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Personality Likability</CardTitle>
          <CardDescription>Loading your personality preferences...</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {PERSONALITY_IDS.map((personality) => (
            <div key={personality} className="space-y-2">
              <Skeleton className="h-4 w-36" />
              <Skeleton className="h-6 w-full" />
            </div>
          ))}
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Personality Likability</CardTitle>
          <CardDescription className="text-destructive">
            Failed to load likability settings: {getLoadErrorMessage(error)}
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Personality Likability</CardTitle>
        <CardDescription>
          Tune how strongly each personality influences future selection.
          Higher likability increases that personality&apos;s weighting.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <p className="text-sm text-muted-foreground">
          Sassy likability below 30 disables Sassy selection entirely.
        </p>

        <div className="space-y-5">
          {PERSONALITY_IDS.map((personality) => (
            <div key={personality} className="space-y-2">
              <div className="flex items-baseline justify-between gap-4">
                <div>
                  <Label>{PERSONALITY_LABELS[personality]}</Label>
                  <p className="text-sm text-muted-foreground">
                    {PERSONALITY_DESCRIPTIONS[personality]}
                  </p>
                </div>
                <span className="font-mono text-sm text-muted-foreground">
                  {pendingScores[personality]}
                </span>
              </div>
              <Slider
                min={0}
                max={100}
                step={1}
                value={[pendingScores[personality]]}
                onValueChange={([value = 0]) =>
                  setPendingScores((current) => ({
                    ...current,
                    [personality]: value,
                  }))
                }
                disabled={isBusy}
                aria-label={`${PERSONALITY_LABELS[personality]} likability`}
              />
              <div className="flex justify-between text-xs text-muted-foreground">
                <span>Less likely</span>
                <span>More likely</span>
              </div>
            </div>
          ))}
        </div>

        {isDirty && (
          <div className="flex gap-3 pt-2">
            <Button
              variant="outline"
              size="sm"
              disabled={isBusy}
              onClick={() => setPendingScores(savedScores)}
            >
              Cancel
            </Button>
            <Button
              size="sm"
              disabled={isBusy}
              onClick={() =>
                updateLikabilityMutation.mutate(pendingScores, {
                  onSuccess: (nextState) => {
                    setSavedScores(nextState.likability_scores);
                    setPendingScores(nextState.likability_scores);
                    toast({
                      title: "Likability Updated",
                      description: "Your personality likability settings have been saved.",
                    });
                  },
                  onError: (mutationError) => {
                    toast({
                      title: "Likability Update Failed",
                      description: getLoadErrorMessage(mutationError),
                      variant: "destructive",
                    });
                  },
                })
              }
            >
              {updateLikabilityMutation.isPending ? "Saving..." : "Save Likability"}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
