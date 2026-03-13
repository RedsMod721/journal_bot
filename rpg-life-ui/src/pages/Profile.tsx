import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { useUser } from "@/contexts/UserContext";
import { useUserStats } from "@/hooks/useUserStats";
import {
  usePersonalityFeedback,
  usePersonalityMessages,
} from "@/hooks/usePersonalityMessages";
import { usePersonalityState } from "@/hooks/usePersonalityState";
import { useRecentAnomalies } from "@/hooks/useRecentAnomalies";
import { UserIdSelector } from "@/components/user/UserIdSelector";
import { HarmonyRadarChart } from "@/components/dashboard/HarmonyRadarChart";
import { VarietyScoreCard } from "@/components/dashboard/VarietyScoreCard";
import { ForgivenessProfileCard } from "@/components/profile/ForgivenessProfileCard";

export function Profile() {
  const { user } = useUser();
  const { data: stats, isLoading, error } = useUserStats(user?.id ?? "");
  const personalityStateQuery = usePersonalityState(user?.id ?? "", !!user?.id);
  const personalityMessagesQuery = usePersonalityMessages(user?.id ?? "", undefined, {
    enabled: !!user?.id,
  });
  const recentAnomaliesQuery = useRecentAnomalies(user?.id ?? "", !!user?.id);
  const feedbackMutation = usePersonalityFeedback(user?.id ?? "");

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

  const topMessage = personalityMessagesQuery.data?.[0];
  const likabilityScores = personalityStateQuery.data?.likability_scores
    ? Object.entries(personalityStateQuery.data.likability_scores).sort((a, b) => b[1] - a[1])
    : [];

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

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader className="space-y-4">
            <div>
              <CardTitle className="flex items-center gap-2">
                Personality System
                {personalityStateQuery.data ? (
                  <Badge className="capitalize">{personalityStateQuery.data.active_personality}</Badge>
                ) : null}
              </CardTitle>
              <CardDescription>
                Active voice, likability learning, and feedback controls
              </CardDescription>
            </div>
            {personalityStateQuery.isLoading ? (
              <Skeleton className="h-24 w-full" />
            ) : (
              <div className="grid grid-cols-2 gap-3 text-sm">
                {likabilityScores.map(([personality, score]) => (
                  <div key={personality} className="rounded-lg border p-3">
                    <div className="capitalize text-muted-foreground">{personality}</div>
                    <div className="text-lg font-semibold">{score}</div>
                  </div>
                ))}
              </div>
            )}
          </CardHeader>
        </Card>

        <Card>
          <CardHeader className="space-y-4">
            <div>
              <CardTitle>Recent Anomalies</CardTitle>
              <CardDescription>High-variance entries and their reward multipliers</CardDescription>
            </div>
            {recentAnomaliesQuery.isLoading ? (
              <Skeleton className="h-24 w-full" />
            ) : recentAnomaliesQuery.data?.anomalies.length ? (
              <div className="space-y-3 text-sm">
                {recentAnomaliesQuery.data.anomalies.map((anomaly) => (
                  <div key={anomaly.entry_id} className="rounded-lg border p-3">
                    <div className="font-medium">Entry {anomaly.entry_id.slice(0, 8)}</div>
                    <div className="text-muted-foreground">
                      Score {anomaly.score.toFixed(2)} / Multiplier x{anomaly.troll_multiplier.toFixed(3)}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No recent high-anomaly entries.</p>
            )}
          </CardHeader>
        </Card>
      </div>

      <Card>
        <CardHeader className="space-y-4">
          <div>
            <CardTitle>Latest Personality Message</CardTitle>
            <CardDescription>Persisted AI feedback with live likability updates</CardDescription>
          </div>
          {personalityMessagesQuery.isLoading ? (
            <Skeleton className="h-24 w-full" />
          ) : topMessage ? (
            <>
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <Badge className="capitalize">{topMessage.personality}</Badge>
                  <span className="text-sm text-muted-foreground">{topMessage.message_type}</span>
                </div>
                <p className="text-sm leading-6">{topMessage.message_text}</p>
              </div>
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={feedbackMutation.isPending}
                  onClick={() =>
                    feedbackMutation.mutate({
                      message_id: topMessage.id,
                      feedback_type: "thumbs_up",
                    })
                  }
                >
                  Helpful
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={feedbackMutation.isPending}
                  onClick={() =>
                    feedbackMutation.mutate({
                      message_id: topMessage.id,
                      feedback_type: "thumbs_down",
                    })
                  }
                >
                  Off target
                </Button>
              </div>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">No personality messages recorded yet.</p>
          )}
        </CardHeader>
      </Card>
    </div>
  );
}
