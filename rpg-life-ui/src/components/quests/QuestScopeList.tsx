import { Quest, QUEST_TYPE_COLORS, QUEST_TYPE_LABELS, QuestType } from "@/types/quest";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { CheckCircle2, Flame, Target, Zap } from "lucide-react";
import { motion } from "framer-motion";

/**
 * Quest list broken down by scope (instant vs. longterm) and type (streak).
 * Complements the existing QuestList (which groups by status).
 * Used on the Story Arcs page to show quests in arc context.
 */

interface QuestScopeListProps {
  quests: Quest[];
  className?: string;
}

function ProgressBar({ current, target }: { current: number; target: number }) {
  const pct = Math.min((current / Math.max(target, 1)) * 100, 100);
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>{current.toLocaleString()} / {target.toLocaleString()}</span>
        <span>{pct.toFixed(0)}%</span>
      </div>
      <div className="w-full bg-secondary h-1.5 rounded-full overflow-hidden">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.8, ease: "easeOut" }}
          className={cn(
            "h-full rounded-full",
            pct >= 100 ? "bg-quest-complete" : "bg-quest-active"
          )}
        />
      </div>
    </div>
  );
}

function QuestRow({ quest }: { quest: Quest }) {
  const typeColor = QUEST_TYPE_COLORS[quest.quest_type as QuestType];
  const typeLabel = QUEST_TYPE_LABELS[quest.quest_type as QuestType];
  const isCompleted = quest.status === "completed";

  return (
    <div
      className={cn(
        "flex items-start gap-3 p-3 rounded-lg border border-border",
        isCompleted && "opacity-60 bg-muted/30"
      )}
    >
      <div className="mt-0.5">
        {quest.quest_type === "streak" ? (
          <Flame className="w-4 h-4 text-orange-500" />
        ) : quest.quest_scope === "instant" ? (
          <Zap className="w-4 h-4 text-yellow-500" />
        ) : (
          <Target className="w-4 h-4 text-primary" />
        )}
      </div>

      <div className="flex-1 min-w-0 space-y-1.5">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={cn("text-sm font-medium", isCompleted && "line-through text-muted-foreground")}>
            {quest.quest_name}
          </span>
          <Badge variant="outline" className={cn("text-xs", typeColor)}>
            {typeLabel}
          </Badge>
          {isCompleted && (
            <CheckCircle2 className="w-3.5 h-3.5 text-quest-complete" />
          )}
        </div>

        {quest.related_skill_name && (
          <p className="text-xs text-muted-foreground">{quest.related_skill_name}</p>
        )}

        {quest.target_value != null && quest.current_value != null && (
          <ProgressBar current={quest.current_value} target={quest.target_value} />
        )}
      </div>
    </div>
  );
}

function Section({
  title,
  quests,
  emptyMessage,
}: {
  title: string;
  quests: Quest[];
  emptyMessage: string;
}) {
  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
        {title}
      </h3>
      {quests.length === 0 ? (
        <p className="text-sm text-muted-foreground py-2">{emptyMessage}</p>
      ) : (
        <div className="space-y-2">
          {quests.map((q) => (
            <QuestRow key={q.quest_id} quest={q} />
          ))}
        </div>
      )}
    </div>
  );
}

export function QuestScopeList({ quests, className }: QuestScopeListProps) {
  const streakQuests = quests.filter((q) => q.quest_type === "streak");
  const instantQuests = quests.filter(
    (q) => q.quest_scope === "instant" && q.quest_type !== "streak"
  );
  const longtermQuests = quests.filter(
    (q) => q.quest_scope === "longterm" && q.quest_type !== "streak"
  );

  if (quests.length === 0) {
    return (
      <p className="text-sm text-muted-foreground py-4">
        No quests yet. Submit journal entries to unlock quests!
      </p>
    );
  }

  return (
    <div className={cn("space-y-6", className)}>
      {streakQuests.length > 0 && (
        <Section
          title="Streaks"
          quests={streakQuests}
          emptyMessage="No active streaks"
        />
      )}
      <Section
        title="Instant Completions"
        quests={instantQuests}
        emptyMessage="No instant quests"
      />
      <Section
        title="Long-term Goals"
        quests={longtermQuests}
        emptyMessage="No long-term quests"
      />
    </div>
  );
}
