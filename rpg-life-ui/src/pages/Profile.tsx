import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { useUser } from "@/contexts/UserContext";
import { useUserStats } from "@/hooks/useUserStats";
import { UserIdSelector } from "@/components/user/UserIdSelector";
import { HarmonyRadarChart } from "@/components/dashboard/HarmonyRadarChart";
import { VarietyScoreCard } from "@/components/dashboard/VarietyScoreCard";
import { ForgivenessProfileCard } from "@/components/profile/ForgivenessProfileCard";

export function Profile() {
  const { user } = useUser();
  const { data: stats, isLoading, error } = useUserStats(user?.id ?? "");

  if (!user) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-display font-bold">Profile</h1>
        <UserIdSelector />
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-display font-bold">Profile</h1>
        <p className="text-destructive">Error loading profile: {(error as Error).message}</p>
      </div>
    );
  }

  if (isLoading || !stats) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-display font-bold">Profile</h1>
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      <div>
        <h1 className="text-3xl font-display font-bold mb-2">Profile</h1>
        <p className="text-muted-foreground">Your account and statistics</p>
      </div>

      {/* User Info */}
      <Card>
        <div className="p-6 flex items-center gap-6">
          <Avatar className="w-20 h-20">
            <AvatarFallback className="text-2xl">
              {user.name.substring(0, 2).toUpperCase()}
            </AvatarFallback>
          </Avatar>
          <div className="space-y-2">
            <div>
              <h3 className="text-2xl font-bold">{user.name}</h3>
              <p className="text-muted-foreground">Level {stats.current_level}</p>
            </div>
            <div className="flex items-center gap-4 text-sm">
              <div>
                <span className="text-muted-foreground">Total XP: </span>
                <span className="font-semibold text-primary">
                  {stats.total_xp.toLocaleString()}
                </span>
              </div>
              <Separator orientation="vertical" className="h-4" />
              <div>
                <span className="text-muted-foreground">Streak: </span>
                <span className="font-semibold">
                  {stats.current_streak > 0 ? `🔥 ${stats.current_streak} days` : "—"}
                </span>
              </div>
            </div>
          </div>
        </div>
      </Card>

      {/* Statistics */}
      <Card>
        <div className="p-6">
          <div className="text-lg font-semibold mb-4">Statistics</div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            <div>
              <div className="text-2xl font-bold text-primary">
                {stats.journal_entries}
              </div>
              <div className="text-sm text-muted-foreground">Journal Entries</div>
            </div>
            <div>
              <div className="text-2xl font-bold text-accent">
                {stats.skills_practiced}
              </div>
              <div className="text-sm text-muted-foreground">Skills Practiced</div>
            </div>
            <div>
              <div className="text-2xl font-bold text-quest-active">
                {stats.active_quests}
              </div>
              <div className="text-sm text-muted-foreground">Active Quests</div>
            </div>
            <div>
              <div className="text-2xl font-bold">
                {stats.xp_today.toLocaleString()}
              </div>
              <div className="text-sm text-muted-foreground">XP Today</div>
            </div>
          </div>
        </div>
      </Card>

      {/* Balance & Harmony — Week 5 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <HarmonyRadarChart />
        <VarietyScoreCard />
      </div>

      <ForgivenessProfileCard />

      {/* Future Features */}
      <Card className="border-dashed">
        <CardHeader>
          <CardTitle>Personality Selection</CardTitle>
          <CardDescription>AI personality archetypes (Coming in Week 6)</CardDescription>
        </CardHeader>
      </Card>
    </div>
  );
}
