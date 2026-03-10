import { QuestCard } from "./QuestCard";
import { Quest } from "@/types/quest";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

interface QuestListProps {
  quests: Quest[];
  variant?: "default" | "compact";
  onQuestComplete?: (quest: Quest) => void;
  className?: string;
}

export function QuestList({
  quests,
  variant = "default",
  onQuestComplete,
  className,
}: QuestListProps) {
  const activeQuests = quests.filter((q) => q.status === "active");
  const completedQuests = quests.filter((q) => q.status === "completed");
  const failedQuests = quests.filter((q) => q.status === "failed");

  if (quests.length === 0) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">No quests yet.</p>
        <p className="text-sm text-muted-foreground mt-2">
          Create a quest to start tracking your goals!
        </p>
      </div>
    );
  }

  return (
    <Tabs defaultValue="all" className={className}>
      <TabsList className="grid w-full grid-cols-4">
        <TabsTrigger value="all">
          All ({quests.length})
        </TabsTrigger>
        <TabsTrigger value="active">
          Active ({activeQuests.length})
        </TabsTrigger>
        <TabsTrigger value="completed">
          Completed ({completedQuests.length})
        </TabsTrigger>
        <TabsTrigger value="failed">
          Failed ({failedQuests.length})
        </TabsTrigger>
      </TabsList>

      <TabsContent value="all" className="mt-6">
        {quests.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            No quests
          </div>
        ) : (
          <div className="space-y-4">
            {quests.map((quest) => (
              <QuestCard
                key={quest.quest_id}
                quest={quest}
                variant={variant}
                onComplete={
                  quest.status === "active"
                    ? () => onQuestComplete?.(quest)
                    : undefined
                }
              />
            ))}
          </div>
        )}
      </TabsContent>

      <TabsContent value="active" className="mt-6">
        {activeQuests.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            No active quests
          </div>
        ) : (
          <div className="space-y-4">
            {activeQuests.map((quest) => (
              <QuestCard
                key={quest.quest_id}
                quest={quest}
                variant={variant}
                onComplete={() => onQuestComplete?.(quest)}
              />
            ))}
          </div>
        )}
      </TabsContent>

      <TabsContent value="completed" className="mt-6">
        {completedQuests.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            No completed quests yet
          </div>
        ) : (
          <div className="space-y-4">
            {completedQuests.map((quest) => (
              <QuestCard
                key={quest.quest_id}
                quest={quest}
                variant={variant}
              />
            ))}
          </div>
        )}
      </TabsContent>

      <TabsContent value="failed" className="mt-6">
        {failedQuests.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            No failed quests
          </div>
        ) : (
          <div className="space-y-4">
            {failedQuests.map((quest) => (
              <QuestCard
                key={quest.quest_id}
                quest={quest}
                variant={variant}
              />
            ))}
          </div>
        )}
      </TabsContent>
    </Tabs>
  );
}
