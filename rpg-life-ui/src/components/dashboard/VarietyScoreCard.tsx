import { useQuery } from "@tanstack/react-query";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import apiClient from "@/lib/api";
import { useUser } from "@/contexts/UserContext";

interface StrategyCountsResponse {
  social: number;
  study: number;
  mundane: number;
  troll: number;
  grind: number;
  harmony: number;
}

interface VarietyMetricsResponse {
  variety_score: number;
  variety_bonus_pct: number;
  strategy_counts: StrategyCountsResponse;
  window_start_date: string | null;
  window_end_date: string | null;
}

function getBonusTier(bonusFraction: number): string {
  const pct = bonusFraction * 100;
  if (pct >= 25) return "Excellent";
  if (pct >= 15) return "Great";
  if (pct >= 10) return "Good";
  if (pct >= 5) return "Fair";
  return "Low";
}

const STRATEGY_LABELS: Record<keyof StrategyCountsResponse, string> = {
  social: "Social Risk",
  study: "Study Burst",
  mundane: "Mundane Focus",
  troll: "Troll Mode",
  grind: "Daily Grind",
  harmony: "Harmony",
};

export function VarietyScoreCard() {
  const { user } = useUser();

  const { data: variety, isLoading } = useQuery({
    queryKey: ["varietyMetrics", user?.id],
    queryFn: async () => {
      const { data } = await apiClient.get<VarietyMetricsResponse>(
        "/balance/variety",
        { params: { user_id: user?.id } }
      );
      return data;
    },
    enabled: !!user?.id,
  });

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Variety Bonus</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-2 w-full" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (!variety) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Variety Bonus</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground text-center py-8">
            No variety data yet — journal across different activities to earn a bonus!
          </p>
        </CardContent>
      </Card>
    );
  }

  const bonusPct = (variety.variety_bonus_pct * 100).toFixed(1);
  const tier = getBonusTier(variety.variety_bonus_pct);
  const scorePercent = Math.round(variety.variety_score * 100);

  const strategyCounts = variety.strategy_counts;
  const strategyEntries = (
    Object.keys(STRATEGY_LABELS) as (keyof StrategyCountsResponse)[]
  ).map((key) => ({ key, label: STRATEGY_LABELS[key], count: strategyCounts[key] }));

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Variety Bonus</CardTitle>
          <Badge>+{bonusPct}% XP</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Score bar */}
        <div>
          <div className="flex justify-between text-sm mb-2">
            <span className="text-muted-foreground">Variety Score</span>
            <span className="font-semibold">{tier}</span>
          </div>
          <Progress
            value={scorePercent}
            className="h-2"
            aria-label={`Variety score: ${scorePercent}% — ${tier}`}
          />
          <div className="flex justify-between text-xs text-muted-foreground mt-1">
            <span>0%</span>
            <span>{scorePercent}%</span>
            <span>100%</span>
          </div>
        </div>

        {/* Strategy breakdown */}
        <div>
          <div className="text-xs text-muted-foreground mb-2">
            30-day strategy distribution
          </div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
            {strategyEntries.map(({ key, label, count }) => (
              <div key={key} className="flex justify-between">
                <span className="text-muted-foreground">{label}</span>
                <span className="font-semibold">{count}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Window dates */}
        {variety.window_start_date && variety.window_end_date && (
          <div className="text-xs text-muted-foreground text-center">
            {variety.window_start_date} – {variety.window_end_date}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
