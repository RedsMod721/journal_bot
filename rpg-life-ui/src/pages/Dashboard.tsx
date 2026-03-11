import { XPDisplay } from "@/components/xp/XPDisplay";
import { XPStatsCard } from "@/components/xp/XPStatsCard";
import { SkillList } from "@/components/skills/SkillList";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { HarmonyRadarChart } from "@/components/dashboard/HarmonyRadarChart";
import { VarietyScoreCard } from "@/components/dashboard/VarietyScoreCard";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { ArrowRight, TrendingUp } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useUserStats, DEFAULT_STATS } from "@/hooks/useUserStats";
import { useSkills } from "@/hooks/useSkills";
import { useQuests } from "@/hooks/useQuests";
import { useUser } from "@/contexts/UserContext";
import { useKeyboardShortcuts } from "@/hooks/useKeyboardNav";
import { LiveRegion } from "@/components/accessibility/LiveRegion";
import { UserIdSelector } from "@/components/user/UserIdSelector";

export function Dashboard() {
  const navigate = useNavigate();
  const { user } = useUser();

  const {
    data: userStats = DEFAULT_STATS,
    isLoading: statsLoading,
    error: statsError,
  } = useUserStats(user?.id || "");
  const {
    data: allSkills = [],
    isLoading: skillsLoading,
    error: skillsError,
  } = useSkills(user?.id || "");
  const {
    data: allQuests = [],
    isLoading: questsLoading,
    error: questsError,
  } = useQuests(user?.id || "");

  useKeyboardShortcuts([
    { key: "j", callback: () => navigate("/journal"), description: "Go to Journal" },
    { key: "s", callback: () => navigate("/skills"), description: "Go to Skills" },
    { key: "q", callback: () => navigate("/quests"), description: "Go to Quests" },
    { key: "p", callback: () => navigate("/profile"), description: "Go to Profile" },
  ]);

  // Get top 5 skills by XP
  const topSkills = [...allSkills]
    .sort((a, b) => b.total_xp - a.total_xp)
    .slice(0, 5);

  // Get active quests (limit to 3 for dashboard)
  const activeQuests = allQuests
    .filter((q) => q.status === "active")
    .slice(0, 3);

  if (!user) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-display font-bold">Dashboard</h1>
        <UserIdSelector />
      </div>
    );
  }

  if (statsError || skillsError || questsError) {
    const firstError = (statsError || skillsError || questsError) as Error;
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-display font-bold">Dashboard</h1>
        <p className="text-destructive">
          Failed to load dashboard data: {firstError.message}
        </p>
      </div>
    );
  }

  if (statsLoading || skillsLoading || questsLoading) {
    return (
      <div className="space-y-8">
        <LiveRegion message="Loading your progress..." />
        <div>
          <h1 className="text-3xl font-display font-bold mb-2">Dashboard</h1>
          <p className="text-muted-foreground">Loading your progress...</p>
        </div>
        <Skeleton className="h-48" aria-hidden="true" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <Skeleton className="h-32" aria-hidden="true" />
          <Skeleton className="h-32" aria-hidden="true" />
          <Skeleton className="h-32" aria-hidden="true" />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      <LiveRegion message={`Dashboard loaded. Welcome back, ${user?.name}.`} />
      {/* Welcome Header */}
      <div>
        <h1 className="text-3xl font-display font-bold mb-2">
          Welcome back, {user?.name}! 👋
        </h1>
        <p className="text-muted-foreground">
          Here's your progress overview. Keep up the great work!
        </p>
      </div>

      {/* XP Progress - Full Width */}
      <XPDisplay
        currentXP={userStats.current_level_xp}
        currentLevel={userStats.current_level}
        nextLevelXP={userStats.next_level_xp}
        recentGain={userStats.recent_gain > 0 ? userStats.recent_gain : undefined}
      />

      {/* Overview Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <XPStatsCard
          totalXP={userStats.total_xp}
          xpToday={userStats.xp_today}
          xpThisWeek={userStats.xp_this_week}
        />

        <Card>
          <CardHeader className="pb-3">
            <CardDescription>Skills Practiced</CardDescription>
            <CardTitle className="text-4xl text-accent">
              {userStats.skills_practiced}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <TrendingUp className="w-4 h-4" />
              <span>{topSkills.length} active this week</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardDescription>Active Quests</CardDescription>
            <CardTitle className="text-4xl text-quest-active">
              {userStats.active_quests}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-sm text-muted-foreground">
              {activeQuests.filter(q =>
                ((q.current_value || 0) / (q.target_value || 1)) > 0.7
              ).length} near completion
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Streak Card */}
      {userStats.current_streak > 0 && (
        <Card className="border-accent bg-accent/5">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-2xl">
                  🔥 {userStats.current_streak} Day Streak!
                </CardTitle>
                <CardDescription className="mt-1">
                  Keep it going! You're building great habits.
                </CardDescription>
              </div>
            </div>
          </CardHeader>
        </Card>
      )}

      {/* Top Skills & Active Quests - Side by Side */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Top Skills */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Top Skills</CardTitle>
                <CardDescription>Your most practiced skills</CardDescription>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => navigate("/skills")}
              >
                View All
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {topSkills.length > 0 ? (
              <SkillList
                skills={topSkills}
                variant="compact"
                onSkillClick={() => navigate("/skills")}
              />
            ) : (
              <div className="text-center py-8 text-muted-foreground">
                <p>No skills yet!</p>
                <p className="text-sm mt-2">
                  Submit a journal entry to start tracking.
                </p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Active Quests */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Active Quests</CardTitle>
                <CardDescription>Your current goals</CardDescription>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => navigate("/quests")}
              >
                View All
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {activeQuests.length > 0 ? (
              <div className="space-y-3">
                {activeQuests.map((quest) => {
                  const progressPercent = Math.min(
                    Math.round(((quest.current_value || 0) / (quest.target_value || 1)) * 100),
                    100
                  );
                  return (
                    <div key={quest.quest_id}>
                      <div className="flex items-center justify-between mb-1">
                        <h4 className="font-medium text-sm">{quest.quest_name}</h4>
                        <span className="text-xs text-muted-foreground" aria-hidden="true">
                          {quest.current_value || 0}/{quest.target_value}
                        </span>
                      </div>
                      <div
                        role="progressbar"
                        aria-label={`${quest.quest_name} progress`}
                        aria-valuenow={progressPercent}
                        aria-valuemin={0}
                        aria-valuemax={100}
                        className="w-full bg-secondary h-2 rounded-full overflow-hidden"
                      >
                        <div
                          className="h-full bg-quest-active transition-all duration-300"
                          style={{ width: `${progressPercent}%` }}
                          aria-hidden="true"
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="text-center py-8 text-muted-foreground">
                <p>No active quests</p>
                <p className="text-sm mt-2">
                  Create a quest to start tracking goals!
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Balance & Harmony Widgets */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <HarmonyRadarChart />
        <VarietyScoreCard />
      </div>
    </div>
  );
}
