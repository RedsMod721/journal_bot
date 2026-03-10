import { useEffect, useState } from "react";
import { useUser } from "@/contexts/UserContext";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

export function UserIdSelector() {
  const { user, availableUsers, setUserId, isLoading, error } = useUser();
  const [value, setValue] = useState(user?.id ?? "");
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setValue(user?.id ?? "");
  }, [user?.id]);

  const onSave = async () => {
    setSaveError(null);
    setSaved(false);
    setIsSaving(true);
    try {
      await setUserId(value);
      setSaved(true);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to select user");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Select Active User</CardTitle>
        <CardDescription>
          Choose the UUID used for API calls. This is persisted in local storage.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <Input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Paste user UUID"
          disabled={isLoading || isSaving}
        />
        <Button onClick={onSave} disabled={isLoading || isSaving || !value.trim()}>
          {isSaving ? "Saving..." : "Use This User"}
        </Button>
        {availableUsers.length > 0 && (
          <div className="text-sm text-muted-foreground">
            Available users: {availableUsers.map((u) => u.id).join(", ")}
          </div>
        )}
        {(error || saveError) && (
          <p className="text-sm text-destructive">{saveError || error}</p>
        )}
        {saved && !saveError && (
          <p className="text-sm text-accent">Active user updated.</p>
        )}
      </CardContent>
    </Card>
  );
}
