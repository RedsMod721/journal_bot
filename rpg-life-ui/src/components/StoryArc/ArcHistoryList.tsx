import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { useArcHistory } from "@/hooks/useArcs";
import {
  Arc,
  ARC_TYPE_COLORS,
  ARC_TYPE_LABELS,
  ARC_STATUS_COLORS,
  ArcType,
  ArcStatus,
} from "@/types/arc";

interface ArcHistoryListProps {
  userId: string;
}

function ArcRow({ arc }: { arc: Arc }) {
  const typeLabel =
    arc.arc_type === "event" && arc.event_name
      ? arc.event_name
      : ARC_TYPE_LABELS[arc.arc_type as ArcType] ?? arc.arc_type;
  const typeColor = ARC_TYPE_COLORS[arc.arc_type as ArcType];
  const statusColor = ARC_STATUS_COLORS[arc.status as ArcStatus];

  return (
    <div className="flex items-center gap-3 py-3 border-b border-border last:border-0">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <Badge variant="outline" className={cn("text-xs", typeColor)}>
            {typeLabel}
          </Badge>
          <Badge variant="outline" className={cn("text-xs capitalize", statusColor)}>
            {arc.status}
          </Badge>
        </div>
        <div className="text-xs text-muted-foreground mt-1">
          {new Date(arc.started_at).toLocaleDateString()}
          {arc.completed_at &&
            ` → ${new Date(arc.completed_at).toLocaleDateString()}`}
        </div>
      </div>
      <div className="text-right text-xs text-muted-foreground shrink-0 space-y-0.5">
        <div>+{arc.xp_reward_multiplier.toFixed(2)}x rewards</div>
        <div>{arc.decay_rate_multiplier.toFixed(2)}x decay</div>
      </div>
    </div>
  );
}

export function ArcHistoryList({ userId }: ArcHistoryListProps) {
  const { data, isLoading, isFetchingNextPage, hasNextPage, fetchNextPage } =
    useArcHistory(userId);

  if (isLoading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-14" />
        ))}
      </div>
    );
  }

  const allArcs = data?.pages.flatMap((page) => page.items) ?? [];

  if (allArcs.length === 0) {
    return (
      <p className="text-sm text-muted-foreground py-4">No arc history yet.</p>
    );
  }

  return (
    <div>
      <div>
        {allArcs.map((arc) => (
          <ArcRow key={arc.id} arc={arc} />
        ))}
      </div>
      {hasNextPage && (
        <Button
          variant="ghost"
          size="sm"
          className="mt-3 w-full"
          disabled={isFetchingNextPage}
          onClick={() => fetchNextPage()}
        >
          {isFetchingNextPage ? "Loading…" : "Load More"}
        </Button>
      )}
    </div>
  );
}
