import { motion } from "framer-motion";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import { formatDistanceToNow } from "date-fns";
import { Trophy, Clock } from "lucide-react";
import { Skill, SKILL_CATEGORY_COLORS, SkillCategory } from "@/types/skill";

interface SkillCardProps {
  skill: Skill;
  variant?: "default" | "compact" | "detailed";
  onClick?: () => void;

  // Future features (optional - will be used in Weeks 5-8)
  showDecay?: boolean;
  decayPercentage?: number;
  forgivenessLevel?: number;
  harmonyDimension?: string;
  varietyBonus?: number;

  className?: string;
}

export function SkillCard({
  skill,
  variant = "default",
  onClick,
  showDecay = false,
  decayPercentage,
  className,
}: SkillCardProps) {
  const xpInCurrentLevel = Math.max(0, skill.current_level_xp);
  const xpNeededForNextLevel = Math.max(1, skill.next_level_xp);
  const progressPercent = Math.min(
    Math.max(0, (xpInCurrentLevel / xpNeededForNextLevel) * 100),
    100
  );

  const lastPracticedText = formatDistanceToNow(
    new Date(skill.last_practiced_at),
    { addSuffix: true }
  );

  const categoryColor =
    SKILL_CATEGORY_COLORS[skill.category as SkillCategory] ||
    "bg-muted text-muted-foreground";

  if (variant === "compact") {
    return (
      <motion.div
        whileHover={{ scale: 1.01, x: 4 }}
        whileTap={{ scale: 0.99 }}
        transition={{ type: "spring", stiffness: 300, damping: 20 }}
        className={cn(
          "flex items-center gap-4 p-3 rounded-lg border border-border hover:bg-accent/50 transition-colors cursor-pointer",
          className
        )}
        onClick={onClick}
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h4 className="font-semibold truncate">{skill.canonical_name}</h4>
            <Badge variant="outline" className={cn("text-xs", categoryColor)}>
              {skill.category}
            </Badge>
          </div>
          <Progress value={progressPercent} className="h-1.5" />
        </div>
        <div className="text-right shrink-0">
          <div className="text-lg font-bold text-primary">
            Lvl {skill.current_level}
          </div>
          <div className="text-xs text-muted-foreground">
            {skill.total_xp.toLocaleString()} XP
          </div>
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div
      whileHover={{ scale: 1.02, y: -4 }}
      whileTap={{ scale: 0.98 }}
      transition={{ type: "spring", stiffness: 300, damping: 20 }}
    >
      <Card
        className={cn(
          "hover:shadow-xl transition-shadow cursor-pointer group",
          showDecay && decayPercentage && decayPercentage > 0 && "border-destructive/40",
          className
        )}
        onClick={onClick}
      >
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div className="flex-1 min-w-0">
            <h3 className="font-semibold text-lg truncate group-hover:text-primary transition-colors">
              {skill.canonical_name}
            </h3>
            <Badge variant="outline" className={cn("mt-1 text-xs", categoryColor)}>
              {skill.category}
            </Badge>
          </div>
          <div className="flex items-center gap-2 shrink-0 ml-2">
            <Trophy className="w-5 h-5 text-primary" />
            <span className="text-2xl font-bold text-primary">
              {skill.current_level}
            </span>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-3">
        {/* XP Progress */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Level Progress</span>
            <span className="font-medium">
              {xpInCurrentLevel.toLocaleString()} /{" "}
              {xpNeededForNextLevel.toLocaleString()} XP
            </span>
          </div>
          <Progress value={progressPercent} className="h-2" />
          <div className="text-xs text-muted-foreground text-right">
            {progressPercent.toFixed(1)}% to Level {skill.current_level + 1}
          </div>
        </div>

        {/* Last Practiced */}
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Clock className="w-4 h-4" />
          <span>Practiced {lastPracticedText}</span>
        </div>

        {/* Total XP */}
        <div className="flex items-center justify-between pt-2 border-t border-border">
          <span className="text-sm text-muted-foreground">Total XP</span>
          <span className="font-semibold text-primary">
            {skill.total_xp.toLocaleString()}
          </span>
        </div>

        {/* Decay Warning (Future - Week 5) */}
        {showDecay && decayPercentage && decayPercentage > 0 && (
          <div className="flex items-center gap-2 p-2 rounded bg-destructive/10 border border-destructive/20">
            <span className="text-xs text-destructive font-medium">
              ⚠️ {decayPercentage}% staleness
            </span>
          </div>
        )}
      </CardContent>
      </Card>
    </motion.div>
  );
}
