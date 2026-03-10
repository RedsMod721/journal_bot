import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { TrendingUp } from "lucide-react";

interface XPStatsCardProps {
  totalXP: number;
  xpToday?: number;
  xpThisWeek?: number;
  className?: string;
}

export function XPStatsCard({
  totalXP,
  xpToday = 0,
  xpThisWeek = 0,
  className,
}: XPStatsCardProps) {
  return (
    <Card className={className}>
      <CardHeader className="pb-3">
        <CardDescription>Total XP</CardDescription>
        <CardTitle className="text-4xl font-display text-primary">
          {totalXP.toLocaleString()}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-1 text-sm">
          {xpToday > 0 && (
            <div className="flex items-center gap-2 text-accent">
              <TrendingUp className="w-4 h-4" />
              <span>+{xpToday.toLocaleString()} XP today</span>
            </div>
          )}
          {xpThisWeek > 0 && (
            <div className="text-muted-foreground">
              {xpThisWeek.toLocaleString()} XP this week
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
