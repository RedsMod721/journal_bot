import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useUser } from "@/contexts/UserContext";
import { useForgivenessConfig } from "@/hooks/useForgiveness";
import {
  formatHalfLifeFromDecayRate,
  getForgivenessLoadErrorMessage,
  getForgivenessPresetName,
} from "@/lib/forgiveness";

export function ForgivenessProfileCard() {
  const { user } = useUser();
  const userId = user?.id ?? "";
  const { data, isLoading, error } = useForgivenessConfig(userId);

  if (!userId) {
    return null;
  }

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Forgiveness</CardTitle>
          <CardDescription>Loading your current preset...</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="h-6 w-40" />
          <Skeleton className="h-4 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (error || !data) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Forgiveness</CardTitle>
          <CardDescription className="text-destructive">
            Failed to load forgiveness details: {getForgivenessLoadErrorMessage(error)}
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  const presetName = getForgivenessPresetName(data.preset);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Forgiveness</CardTitle>
        <CardDescription>Your active forgiveness preset and final values.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <div className="text-sm text-muted-foreground">Preset</div>
          <div className="text-lg font-semibold">{presetName}</div>
        </div>

        {data.preset === "custom" && (
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded border border-border p-3">
              <div className="text-sm text-muted-foreground">Skill Half-life</div>
              <div className="font-medium">
                {formatHalfLifeFromDecayRate(data.skill_decay_rate)}
              </div>
            </div>
            <div className="rounded border border-border p-3">
              <div className="text-sm text-muted-foreground">Skill Grace Period</div>
              <div className="font-medium">
                {data.skill_grace_period_days} days before skill decay starts
              </div>
            </div>
            <div className="rounded border border-border p-3">
              <div className="text-sm text-muted-foreground">Insight Half-life</div>
              <div className="font-medium">
                {formatHalfLifeFromDecayRate(data.insight_decay_rate)}
              </div>
            </div>
            <div className="rounded border border-border p-3">
              <div className="text-sm text-muted-foreground">Insight Grace Period</div>
              <div className="font-medium">
                {data.insight_grace_period_days} days before insight decay starts
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
