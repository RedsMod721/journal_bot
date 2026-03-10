import { JournalEditor } from "@/components/journal/JournalEditor";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useJournalSubmit } from "@/hooks/useJournalSubmit";
import { useUser } from "@/contexts/UserContext";
import { useJournalEntryStatus } from "@/hooks/useJournalEntryStatus";
import { UserIdSelector } from "@/components/user/UserIdSelector";
import { Loader2 } from "lucide-react";
import { useState } from "react";

export function Journal() {
  const { user } = useUser();
  const submitMutation = useJournalSubmit();
  const [latestEntryId, setLatestEntryId] = useState<string | null>(null);

  const statusQuery = useJournalEntryStatus(
    latestEntryId || "",
    user?.id || "",
    !!latestEntryId && !!user?.id
  );

  const handleSubmit = async (text: string) => {
    if (!user) return;

    try {
      const response = await submitMutation.mutateAsync({
        user_id: user.id,
        raw_text: text,
      });
      setLatestEntryId(response.entry_id);
    } catch {
      // Error handled by mutation's onError toast — prevent JournalEditor
      // from also showing an inline error for the same failure.
    }
  };

  if (!user) {
    return (
      <div className="max-w-4xl mx-auto space-y-6">
        <h1 className="text-3xl font-display font-bold">Journal Entry</h1>
        <UserIdSelector />
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      <div>
        <h1 className="text-3xl font-display font-bold mb-2">Journal Entry</h1>
        <p className="text-muted-foreground">
          Write about your day. The AI will process your entry and award XP.
        </p>
      </div>

      <JournalEditor
        onSubmit={handleSubmit}
        isLoading={submitMutation.isPending}
        minWords={2}
        maxWords={10000}
      />

      {latestEntryId && (
        <Card>
          <CardHeader>
            <CardTitle>Processing Status</CardTitle>
            <CardDescription>
              Entry ID: {latestEntryId}
            </CardDescription>
            {statusQuery.isLoading && (
              <div className="flex items-center gap-2 text-muted-foreground text-sm">
                <Loader2 className="h-4 w-4 animate-spin" />
                Checking status...
              </div>
            )}
            {statusQuery.data && (
              <div className="text-sm space-y-1">
                <p>
                  Status: <span className="font-semibold">{statusQuery.data.status}</span>
                </p>
                <p>Word count: {statusQuery.data.word_count}</p>
                {statusQuery.data.processing_duration_ms ? (
                  <p>Duration: {statusQuery.data.processing_duration_ms} ms</p>
                ) : null}
                {statusQuery.data.error_message ? (
                  <p className="text-destructive">{statusQuery.data.error_message}</p>
                ) : null}
              </div>
            )}
            {statusQuery.error && (
              <p className="text-sm text-destructive">
                Failed to fetch status: {(statusQuery.error as Error).message}
              </p>
            )}
          </CardHeader>
        </Card>
      )}

      <Card className="border-dashed">
        <CardHeader>
          <CardTitle>Previous Entries</CardTitle>
          <CardDescription>Entry history coming in Week 9</CardDescription>
        </CardHeader>
      </Card>
    </div>
  );
}
