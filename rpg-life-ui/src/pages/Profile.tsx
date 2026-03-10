import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Separator } from "@/components/ui/separator";
import { useUser } from "@/contexts/UserContext";
import { useUserStats } from "@/hooks/useUserStats";
import { UserIdSelector } from "@/components/user/UserIdSelector";

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
        <p className="text-muted-foreground">Loading profile...</p>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      <div>
        <h1 className="text-3xl font-display font-bold mb-2">Profile</h1>
        <p className="text-muted-foreground">
          Your account and statistics
        </p>
      </div>

      {/* User Info Card */}
      <Card>
        <CardHeader>
          <CardTitle>User Information</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-6">
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
                  <span className="text-muted-foreground">Member since: </span>
                  <span className="font-semibold">-</span>
                </div>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Statistics Card */}
      <Card>
        <CardHeader>
          <CardTitle>Statistics</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            <div>
              <div className="text-2xl font-bold text-primary">
                {stats.journal_entries}
              </div>
              <div className="text-sm text-muted-foreground">
                Journal Entries
              </div>
            </div>
            <div>
              <div className="text-2xl font-bold text-accent">
                {stats.skills_practiced}
              </div>
              <div className="text-sm text-muted-foreground">
                Skills Practiced
              </div>
            </div>
            <div>
              <div className="text-2xl font-bold text-quest-complete">
                {stats.active_quests}
              </div>
              <div className="text-sm text-muted-foreground">
                Active Quests
              </div>
            </div>
            <div>
              <div className="text-2xl font-bold text-xp-gain">
                {stats.current_streak}
              </div>
              <div className="text-sm text-muted-foreground">
                Day Streak
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Placeholder Cards for Future Features */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card className="border-dashed">
          <CardHeader>
            <CardTitle>Personality Selection</CardTitle>
            <CardDescription>Coming in Week 6/9</CardDescription>
          </CardHeader>
        </Card>

        <Card className="border-dashed">
          <CardHeader>
            <CardTitle>Forgiveness Settings</CardTitle>
            <CardDescription>Coming in Week 5/9</CardDescription>
          </CardHeader>
        </Card>

        <Card className="border-dashed">
          <CardHeader>
            <CardTitle>Balance Strategy</CardTitle>
            <CardDescription>Coming in Week 5/9</CardDescription>
          </CardHeader>
        </Card>

        <Card className="border-dashed">
          <CardHeader>
            <CardTitle>Harmony Score</CardTitle>
            <CardDescription>Coming in Week 5/9</CardDescription>
          </CardHeader>
        </Card>
      </div>
    </div>
  );
}
