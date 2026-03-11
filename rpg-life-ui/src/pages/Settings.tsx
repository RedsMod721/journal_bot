import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { useRealmPreferences } from "@/hooks/useRealmPreferences";
import { ForgivenessSettings } from "@/components/settings/ForgivenessSettings";

export function Settings() {
  const {
    presets,
    currentPreset,
    isLoading,
    error,
    isUpdating,
    isUpdatingSkillHierarchy,
    setPreset,
    defaultBlockedPreference,
    setDefaultBlockedPreference,
  } = useRealmPreferences();

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-display font-bold mb-2">Settings</h1>
          <p className="text-muted-foreground">Loading your preferences…</p>
        </div>
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-display font-bold mb-2">Settings</h1>
          <p className="text-destructive">
            Failed to load settings: {error}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-display font-bold mb-2">Settings</h1>
        <p className="text-muted-foreground">
          Choose how rank names are displayed across your realm.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Realm Rank Wording</CardTitle>
          <CardDescription>
            Toggle your active realm style. This preference is saved to your account.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2" aria-label="Realm preset toggle group">
            {presets.map((preset) => (
              <Button
                key={preset.preset}
                type="button"
                variant={preset.preset === currentPreset ? "default" : "outline"}
                disabled={isUpdating}
                onClick={() => void setPreset(preset.preset)}
              >
                {preset.name}
              </Button>
            ))}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2 text-sm">
            {(presets.find((item) => item.preset === currentPreset)?.ranks ?? []).map(
              (row) => (
                <div
                  key={row.rank}
                  className="rounded border border-border px-3 py-2 text-muted-foreground"
                >
                  <span className="font-medium text-foreground">{row.rank}</span>{" "}
                  - {row.wording}
                </div>
              )
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Skill Unlock Defaults</CardTitle>
          <CardDescription>
            Control whether newly available skills start blocked or immediately active.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center justify-between rounded border border-border p-3">
            <div className="space-y-1">
              <Label htmlFor="default-blocked-preference">Block new skills by default</Label>
              <p className="text-sm text-muted-foreground">
                When enabled, newly discovered/unlocked skills start blocked and redirect XP.
              </p>
            </div>
            <Switch
              id="default-blocked-preference"
              checked={defaultBlockedPreference}
              disabled={isUpdatingSkillHierarchy}
              onCheckedChange={(checked) => void setDefaultBlockedPreference(checked)}
            />
          </div>
        </CardContent>
      </Card>

      <ForgivenessSettings />
    </div>
  );
}
