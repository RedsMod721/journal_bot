import { JournalEditor } from "@/components/journal/JournalEditor";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useJournalSubmit } from "@/hooks/useJournalSubmit";
import { useUser } from "@/contexts/UserContext";
import { useJournalEntryStatus } from "@/hooks/useJournalEntryStatus";
import { useEntryAnomaly } from "@/hooks/useEntryAnomaly";
import {
  usePersonalityFeedback,
  usePersonalityMessages,
} from "@/hooks/usePersonalityMessages";
import { UserIdSelector } from "@/components/user/UserIdSelector";
import { Loader2 } from "lucide-react";
import { useState } from "react";

export function Journal() {
  const { user } = useUser();
  const submitMutation = useJournalSubmit();
  const [latestJobId, setLatestJobId] = useState<string | null>(null);
  const [latestEntryId, setLatestEntryId] = useState<string | null>(null);

  const statusQuery = useJournalEntryStatus(
    latestJobId || "",
    user?.id || "",
    !!latestJobId && !!user?.id
  );
  const isTerminal = statusQuery.data?.status === "completed";
  const anomalyQuery = useEntryAnomaly(
    latestEntryId || "",
    user?.id || "",
    !!latestEntryId && !!user?.id && isTerminal
  );
  const personalityMessagesQuery = usePersonalityMessages(
    user?.id || "",
    latestEntryId || undefined,
    !!latestEntryId && !!user?.id && isTerminal
  );
  const feedbackMutation = usePersonalityFeedback(user?.id || "");
  const latestMessage = personalityMessagesQuery.data?.[0];

  const handleSubmit = async (text: string) => {
    if (!user) return;
    const response = await submitMutation.mutateAsync({
      user_id: user.id,
      content: text,
    });
    setLatestJobId(response.job_id);
    setLatestEntryId(response.entry_id);
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
              Job ID: {latestJobId}
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
                <p>Entry ID: {statusQuery.data.entry_id}</p>
                <p>Attempt count: {statusQuery.data.attempt_count}</p>
                {statusQuery.data.last_error_code ? (
                  <p className="text-destructive">
                    Last error: {statusQuery.data.last_error_code}
                  </p>
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

      {isTerminal && anomalyQuery.data && !anomalyQuery.data.missing && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              Anomaly Score
              <Badge variant="secondary">{anomalyQuery.data.score.toFixed(2)}/10</Badge>
            </CardTitle>
            <CardDescription>
              Troll multiplier: x{anomalyQuery.data.troll_multiplier.toFixed(3)}
            </CardDescription>
          </CardHeader>
        </Card>
      )}

      {isTerminal && latestMessage && (
        <Card>
          <CardHeader className="space-y-4">
            <div>
              <CardTitle className="capitalize">
                {latestMessage.personality} feedback
              </CardTitle>
              <CardDescription>{latestMessage.message_type}</CardDescription>
            </div>
            <p className="text-sm leading-6">{latestMessage.message_text}</p>
            <div className="flex gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={feedbackMutation.isPending}
                onClick={() =>
                  feedbackMutation.mutate({
                    message_id: latestMessage.id,
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
                    message_id: latestMessage.id,
                    feedback_type: "thumbs_down",
                  })
                }
              >
                Off target
              </Button>
            </div>
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
