import { motion } from "framer-motion";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { CheckCircle2, Target, Flame } from "lucide-react";
import { Quest, QUEST_TYPE_LABELS, QUEST_TYPE_COLORS, QuestType } from "@/types/quest";

interface QuestCardProps {
  quest: Quest;
  variant?: "default" | "compact";
  onComplete?: () => void;

  // Future features (optional - Week 7)
  showTemplate?: boolean;
  difficulty?: number;
  userPreference?: string;

  className?: string;
}

export function QuestCard({
  quest,
  variant = "default",
  onComplete,
  className,
}: QuestCardProps) {
  const isCompleted = quest.status === "completed";
  const progressPercent = quest.target_value
    ? Math.min(((quest.current_value || 0) / quest.target_value) * 100, 100)
    : 0;

  const typeColor = QUEST_TYPE_COLORS[quest.quest_type as QuestType];
  const typeLabel = QUEST_TYPE_LABELS[quest.quest_type as QuestType];

  if (variant === "compact") {
    return (
      <div
        className={cn(
          "flex items-center gap-4 p-3 rounded-lg border border-border hover:bg-accent/50 transition-colors",
          isCompleted && "opacity-60",
          className
        )}
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h4 className={cn("font-semibold truncate", isCompleted && "line-through")}>
              {quest.quest_name}
            </h4>
            <Badge variant="outline" className={cn("text-xs", typeColor)}>
              {typeLabel}
            </Badge>
          </div>
          {quest.target_value && (
            <div className="flex items-center gap-2">
              <div className="flex-1 bg-secondary h-1.5 rounded-full overflow-hidden">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${progressPercent}%` }}
                  transition={{ duration: 1, ease: "easeOut" }}
                  className={cn("h-full bg-quest-active", isCompleted && "bg-quest-complete")}
                />
              </div>
              <span className="text-xs text-muted-foreground whitespace-nowrap">
                {quest.current_value || 0}/{quest.target_value}
              </span>
            </div>
          )}
        </div>
        {isCompleted && <CheckCircle2 className="w-5 h-5 text-quest-complete" />}
      </div>
    );
  }

  return (
    <Card
      className={cn(
        "hover:shadow-lg transition-all",
        isCompleted && "border-quest-complete bg-quest-complete/5",
        className
      )}
    >
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <Badge variant="outline" className={cn("text-xs", typeColor)}>
                {typeLabel}
              </Badge>
              {isCompleted && (
                <Badge variant="outline" className="text-xs bg-quest-complete/10 text-quest-complete border-quest-complete/20">
                  Completed
                </Badge>
              )}
            </div>
            <CardTitle className={cn("text-xl", isCompleted && "line-through text-muted-foreground")}>
              {quest.quest_name}
            </CardTitle>
            {quest.description && (
              <CardDescription className="mt-1">{quest.description}</CardDescription>
            )}
          </div>
          <div className="flex items-center gap-2">
            {quest.quest_type === "streak" ? (
              <Flame className="w-6 h-6 text-orange-500" />
            ) : (
              <Target className="w-6 h-6 text-primary" />
            )}
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Progress */}
        {quest.target_value && (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Progress</span>
              <span className="font-medium">
                {quest.current_value || 0} / {quest.target_value}
                {quest.quest_type === "streak" && " days"}
              </span>
            </div>
            <div className={cn("w-full bg-secondary h-2 rounded-full overflow-hidden", isCompleted && "bg-quest-complete/20")}>
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${progressPercent}%` }}
                transition={{ duration: 1, ease: "easeOut" }}
                className={cn("h-full bg-quest-active", isCompleted && "bg-quest-complete")}
              />
            </div>
            <div className="text-xs text-muted-foreground text-right">
              {progressPercent.toFixed(1)}% complete
            </div>
          </div>
        )}

        {/* Actions */}
        {!isCompleted && onComplete && (
          <Button
            variant="outline"
            className="w-full"
            onClick={onComplete}
            disabled={progressPercent < 100}
          >
            {progressPercent >= 100 ? "Mark Complete" : "In Progress"}
          </Button>
        )}

        {isCompleted && quest.completed_at && (
          <div className="flex items-center gap-2 text-sm text-quest-complete">
            <CheckCircle2 className="w-4 h-4" />
            <span>Completed {new Date(quest.completed_at).toLocaleDateString()}</span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
