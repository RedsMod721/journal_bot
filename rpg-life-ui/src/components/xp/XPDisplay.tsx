import { Progress } from "@/components/ui/progress";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Zap } from "lucide-react";
import { cn } from "@/lib/utils";
import { useEffect, useState } from "react";

interface XPDisplayProps {
  currentXP: number;
  currentLevel: number;
  nextLevelXP: number;
  recentGain?: number;
  showAnimation?: boolean;
  variant?: "default" | "compact";
  className?: string;
}

export function XPDisplay({
  currentXP,
  currentLevel,
  nextLevelXP,
  recentGain,
  showAnimation = true,
  variant = "default",
  className,
}: XPDisplayProps) {
  const [animateGain, setAnimateGain] = useState(false);

  const progressPercent = Math.min((currentXP / nextLevelXP) * 100, 100);

  useEffect(() => {
    if (recentGain && showAnimation) {
      setAnimateGain(true);
      const timer = setTimeout(() => setAnimateGain(false), 1000);
      return () => clearTimeout(timer);
    }
  }, [recentGain, showAnimation]);

  if (variant === "compact") {
    return (
      <div className={cn("flex items-center gap-3", className)}>
        <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
          <Zap className="w-5 h-5 text-primary" />
        </div>
        <div className="flex-1">
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold">Level {currentLevel}</span>
            <span className="text-sm text-muted-foreground">
              {currentXP.toLocaleString()} / {nextLevelXP.toLocaleString()} XP
            </span>
          </div>
          <Progress value={progressPercent} className="h-2 mt-1" />
        </div>
      </div>
    );
  }

  return (
    <Card className={className}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-4xl font-display font-bold">
              Level {currentLevel}
            </CardTitle>
            <CardDescription className="mt-1">
              {currentXP.toLocaleString()} / {nextLevelXP.toLocaleString()} XP
            </CardDescription>
          </div>
          <div className="w-12 h-12 rounded-lg bg-primary/10 flex items-center justify-center">
            <Zap className="w-6 h-6 text-primary" />
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Progress value={progressPercent} className="h-3" />
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>{progressPercent.toFixed(1)}% to next level</span>
            <span>{(nextLevelXP - currentXP).toLocaleString()} XP needed</span>
          </div>
        </div>

        {recentGain && (
          <div
            className={cn(
              "flex items-center justify-center py-2 px-4 rounded-lg bg-accent/10 border border-accent/20 transition-all duration-500",
              animateGain && "scale-110 shadow-lg shadow-accent/20"
            )}
          >
            <span className="text-accent font-bold">
              +{recentGain.toLocaleString()} XP
            </span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
