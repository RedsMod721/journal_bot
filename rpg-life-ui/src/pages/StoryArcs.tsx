import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Plus, History } from "lucide-react";
import { CurrentArcCard } from "@/components/StoryArc/CurrentArcCard";
import { ArcHistoryList } from "@/components/StoryArc/ArcHistoryList";
import { VacationToggle } from "@/components/StoryArc/VacationToggle";
import { CreateEventArcDialog } from "@/components/StoryArc/CreateEventArcDialog";
import { QuestScopeList } from "@/components/quests/QuestScopeList";
import { useQuests } from "@/hooks/useQuests";
import { useUser } from "@/contexts/UserContext";
import { UserIdSelector } from "@/components/user/UserIdSelector";

export function StoryArcs() {
  const { user } = useUser();
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const { data: quests = [], isLoading: questsLoading } = useQuests(
    user?.id ?? "",
    "active"
  );

  if (!user) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-display font-bold">Story Arcs</h1>
        <UserIdSelector />
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-display font-bold mb-1">Story Arcs</h1>
          <p className="text-muted-foreground">
            Active narrative contexts that modify XP rewards, requirements, and
            skill decay.
          </p>
        </div>
        <Button onClick={() => setCreateDialogOpen(true)}>
          <Plus className="w-4 h-4 mr-2" />
          New Event Arc
        </Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left column: current arc + vacation */}
        <div className="lg:col-span-2 space-y-6">
          <CurrentArcCard
            userId={user.id}
            onCreateEvent={() => setCreateDialogOpen(true)}
          />

          {/* Active quests in arc context */}
          <Card>
            <CardHeader>
              <CardTitle>Active Quests</CardTitle>
            </CardHeader>
            <CardContent>
              {questsLoading ? (
                <div className="space-y-2">
                  {[1, 2, 3].map((i) => (
                    <Skeleton key={i} className="h-14" />
                  ))}
                </div>
              ) : (
                <QuestScopeList quests={quests} />
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right column: vacation + history */}
        <div className="space-y-6">
          <VacationToggle userId={user.id} />

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <History className="w-4 h-4" />
                Arc History
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ArcHistoryList userId={user.id} />
            </CardContent>
          </Card>
        </div>
      </div>

      <CreateEventArcDialog
        userId={user.id}
        open={createDialogOpen}
        onOpenChange={setCreateDialogOpen}
      />
    </div>
  );
}
