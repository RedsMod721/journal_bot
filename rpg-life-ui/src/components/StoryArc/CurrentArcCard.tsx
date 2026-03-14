import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { TrendingUp, TrendingDown, Zap, Calendar } from "lucide-react";
import { useCurrentArc, useEndArc } from "@/hooks/useArcs";
import { Arc, ARC_TYPE_COLORS, ARC_TYPE_LABELS, ArcType } from "@/types/arc";

interface CurrentArcCardProps {
  userId: string;
  onCreateEvent?: () => void;
}

function MultiplierStat({
  label,
  value,
  icon,
}: {
  label: string;
  value: number;
  icon: React.ReactNode;
}) {
  const isAbove = value > 1;
  const isBelow = value < 1;
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-1 text-xs text-muted-foreground">
        {icon}
        {label}
      </div>
      <div
        className={cn(
          "text-2xl font-bold",
          isAbove && "text-green-500",
          isBelow && "text-red-500"
        )}
      >
        {value.toFixed(2)}x
      </div>
    </div>
  );
}

function ActiveArcContent({
  arc,
  userId,
}: {
  arc: Arc;
  userId: string;
}) {
  const endArc = useEndArc();
  const arcTypeColor = ARC_TYPE_COLORS[arc.arc_type as ArcType];
  const arcLabel =
    arc.arc_type === "event" && arc.event_name
      ? arc.event_name
      : ARC_TYPE_LABELS[arc.arc_type as ArcType] ?? arc.arc_type;

  const isVacation = arc.event_name === "vacation_mode";

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between">
          <CardTitle>Active Story Arc</CardTitle>
          <Badge variant="outline" className={cn("capitalize", arcTypeColor)}>
            {arcLabel}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Multipliers */}
        <div className="grid grid-cols-3 gap-4">
          <MultiplierStat
            label="Quest Rewards"
            value={arc.xp_reward_multiplier}
            icon={<TrendingUp className="w-3 h-3" />}
          />
          <MultiplierStat
            label="Requirements"
            value={arc.xp_requirement_multiplier}
            icon={<Zap className="w-3 h-3" />}
          />
          <MultiplierStat
            label="Decay Rate"
            value={arc.decay_rate_multiplier}
            icon={<TrendingDown className="w-3 h-3" />}
          />
        </div>

        {/* Duration / start */}
        <div className="flex items-center gap-4 text-sm text-muted-foreground">
          <div className="flex items-center gap-1">
            <Calendar className="w-3.5 h-3.5" />
            Started {new Date(arc.started_at).toLocaleDateString()}
          </div>
          {arc.duration_days && (
            <span>{arc.duration_days} day duration</span>
          )}
        </div>

        {/* Actions — only event (non-vacation) arcs can be ended manually */}
        {arc.arc_type === "event" && !isVacation && (
          <Button
            variant="outline"
            size="sm"
            disabled={endArc.isPending}
            onClick={() => endArc.mutate({ userId, arcId: arc.id })}
          >
            {endArc.isPending ? "Ending…" : "End Arc Early"}
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

export function CurrentArcCard({ userId, onCreateEvent }: CurrentArcCardProps) {
  const { data, isLoading, error } = useCurrentArc(userId);

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-40" />
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-3 gap-4">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-14" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Story Arc</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-destructive text-sm">{(error as Error).message}</p>
        </CardContent>
      </Card>
    );
  }

  if (!data?.active || !data.arc) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>No Active Story Arc</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-muted-foreground text-sm">
            You're not in any story arc. Arcs apply multipliers to XP rewards,
            requirements, and skill decay.
          </p>
          {onCreateEvent && (
            <Button variant="outline" size="sm" onClick={onCreateEvent}>
              Create Event Arc
            </Button>
          )}
        </CardContent>
      </Card>
    );
  }

  return <ActiveArcContent arc={data.arc} userId={userId} />;
}
