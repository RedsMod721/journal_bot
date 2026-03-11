import { useState } from "react";
import { motion } from "framer-motion";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { formatDistanceToNow } from "date-fns";
import { Clock, Lock, LockOpen, Eye } from "lucide-react";
import { Skill, SKILL_CATEGORY_COLORS, SkillCategory } from "@/types/skill";
import { useBlockSkill } from "@/hooks/useBlockSkill";
import { useRealmPreferences } from "@/hooks/useRealmPreferences";

interface SkillCardProps {
  skill: Skill;
  variant?: "default" | "compact" | "detailed";
  onClick?: () => void;

  /** Show parent skill badges (hierarchy-aware views) */
  showParents?: boolean;

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
  showParents = false,
  showDecay = false,
  decayPercentage,
  className,
}: SkillCardProps) {
  const [isHovered, setIsHovered] = useState(false);
  const blockMutation = useBlockSkill();
  const { getRankLabel } = useRealmPreferences();

  const hasLevelProgress =
    skill.current_level > 0 &&
    skill.current_level_xp !== undefined &&
    skill.next_level_xp !== undefined &&
    skill.next_level_xp > 0;
  const xpInCurrentLevel = Math.max(0, skill.current_level_xp ?? 0);
  const xpNeededForNextLevel = Math.max(1, skill.next_level_xp ?? 1);
  const progressPercent = Math.min(
    Math.max(0, (xpInCurrentLevel / xpNeededForNextLevel) * 100),
    100
  );

  const lastPracticedText = skill.last_practiced_at
    ? formatDistanceToNow(new Date(skill.last_practiced_at), { addSuffix: true })
    : null;

  const isDiscovered = skill.state === "discovered";
  const isBlocked = skill.user_blocked ?? false;
  const canToggleBlock = skill.current_level < 20;

  const stateClass = isDiscovered ? "opacity-60 grayscale-[40%]" : "";

  const categoryColor =
    SKILL_CATEGORY_COLORS[skill.category as SkillCategory] ||
    "bg-muted text-muted-foreground";
  const realmRankLabel = getRankLabel(skill.rank);
  const rankLine =
    skill.rank && realmRankLabel ? `${skill.rank} - ${realmRankLabel}` : null;

  const handleToggleBlock = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!canToggleBlock || !skill.user_id) return;
    await blockMutation.mutateAsync({
      skill_id: skill.skill_id,
      user_id: skill.user_id,
      blocked: !isBlocked,
    });
  };

  if (variant === "compact") {
    return (
      <motion.div
        whileHover={{ scale: 1.01, x: 4 }}
        whileTap={{ scale: 0.99 }}
        transition={{ type: "spring", stiffness: 300, damping: 20 }}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        className={cn(
          "group flex items-center gap-4 p-3 rounded-lg border border-border hover:bg-accent/50 transition-colors cursor-pointer relative",
          stateClass,
          isBlocked && "border-destructive/50 bg-destructive/5",
          className
        )}
        onClick={onClick}
      >
        {isBlocked && (
          <div className="absolute top-2 right-2">
            <Lock className="w-4 h-4 text-destructive" />
          </div>
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h4 className={cn("font-semibold truncate", isDiscovered && "text-muted-foreground")}>
              {skill.canonical_name}
            </h4>
            <Badge variant="outline" className={cn("text-xs", categoryColor)}>
              {skill.category}
            </Badge>
          </div>
          {hasLevelProgress && <Progress value={progressPercent} className="h-1.5" />}
        </div>
        <div className="text-right shrink-0">
          <div className="text-lg font-bold text-primary flex items-center justify-end gap-1">
            <TooltipProvider delayDuration={0}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <span className="text-sm cursor-help">Lv</span>
                </TooltipTrigger>
                <TooltipContent>
                  <p>Level</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
            <span>{skill.current_level}</span>
          </div>
          <div className="text-xs text-muted-foreground">
            {skill.total_xp.toLocaleString()} XP
          </div>
          {isHovered && rankLine && (
            <div className="text-[11px] text-muted-foreground">{rankLine}</div>
          )}
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div
      whileHover={{ scale: 1.02, y: -4 }}
      whileTap={{ scale: 0.98 }}
      transition={{ type: "spring", stiffness: 300, damping: 20 }}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      <Card
        className={cn(
          "hover:shadow-xl transition-shadow cursor-pointer group relative",
          showDecay && decayPercentage && decayPercentage > 0 && "border-destructive/40",
          stateClass,
          isBlocked && "border-destructive/50 bg-destructive/5",
          className
        )}
        onClick={onClick}
      >
        {/* Blocked icon overlay */}
        {isBlocked && (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <div className="absolute top-3 right-3 z-10 w-8 h-8 rounded-full bg-destructive/10 flex items-center justify-center border border-destructive/20">
                  <Lock className="w-4 h-4 text-destructive" />
                </div>
              </TooltipTrigger>
              <TooltipContent>
                <p>Skill is blocked — XP redirects to parents</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )}

        {/* Discovered badge */}
        {isDiscovered && (
          <div className="absolute top-3 left-3 z-10">
            <Badge variant="outline" className="bg-muted/80 text-muted-foreground border-dashed">
              <Eye className="w-3 h-3 mr-1" />
              Discovered
            </Badge>
          </div>
        )}

        <CardHeader className={cn("pb-3", isDiscovered && "pt-10")}>
          <div className="flex items-start justify-between">
            <div className="flex-1 min-w-0">
              <h3 className={cn(
                "font-semibold text-lg truncate group-hover:text-primary transition-colors",
                isDiscovered && "text-muted-foreground"
              )}>
                {skill.canonical_name}
              </h3>
              <div className="flex items-center gap-2 mt-1">
                <Badge variant="outline" className={cn("text-xs", categoryColor)}>
                  {skill.category}
                </Badge>
                {skill.hierarchy_level != null && (
                  <Badge variant="outline" className="text-xs">
                    L{skill.hierarchy_level}
                  </Badge>
                )}
              </div>
              {isHovered && rankLine && (
                <p className="text-xs text-muted-foreground mt-2">{rankLine}</p>
              )}
            </div>
            <div className="flex items-center gap-1 shrink-0 ml-2 text-primary">
              <TooltipProvider delayDuration={0}>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span className="text-sm font-semibold cursor-help">Lv</span>
                  </TooltipTrigger>
                  <TooltipContent>
                    <p>Level</p>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
              <span className="text-2xl font-bold">{skill.current_level}</span>
            </div>
          </div>
        </CardHeader>

        <CardContent className="space-y-3">
          {/* XP Progress */}
          {hasLevelProgress && (
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
          )}

          {/* Last Practiced */}
          {lastPracticedText && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Clock className="w-4 h-4" />
              <span>Practiced {lastPracticedText}</span>
            </div>
          )}

          {/* Parent Skills */}
          {showParents && skill.parent_skill_ids && skill.parent_skill_ids.length > 0 && (
            <div className="pt-2 border-t border-border">
              <div className="text-xs text-muted-foreground mb-1">Parent Skills:</div>
              <div className="flex flex-wrap gap-1">
                {skill.parent_skill_ids.map((parentId) => (
                  <Badge key={parentId} variant="secondary" className="text-xs">
                    {parentId.split("_").pop()}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          {/* Total XP */}
          <div className="flex items-center justify-between pt-2 border-t border-border">
            <span className="text-sm text-muted-foreground">Total XP</span>
            <span className="font-semibold text-primary">
              {skill.total_xp.toLocaleString()}
            </span>
          </div>

          {/* Block/Unblock Button */}
          {skill.user_id && canToggleBlock && (
            <Button
              variant={isBlocked ? "outline" : "ghost"}
              size="sm"
              className="w-full"
              onClick={handleToggleBlock}
              disabled={blockMutation.isPending}
            >
              {isBlocked ? (
                <>
                  <LockOpen className="w-4 h-4 mr-2" />
                  Unblock Skill
                </>
              ) : (
                <>
                  <Lock className="w-4 h-4 mr-2" />
                  Block Skill
                </>
              )}
            </Button>
          )}

          {!canToggleBlock && isBlocked && (
            <div className="text-xs text-muted-foreground text-center pt-1">
              Cannot unblock at Level 20+
            </div>
          )}

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
