import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2, MessageSquareText, Send, Sparkles } from "lucide-react";
import { JournalEditor } from "@/components/journal/JournalEditor";
import { UserIdSelector } from "@/components/user/UserIdSelector";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { useJournalSubmit } from "@/hooks/useJournalSubmit";
import { useUser } from "@/contexts/UserContext";
import { useJournalEntryStatus } from "@/hooks/useJournalEntryStatus";
import { useEntryAnomaly } from "@/hooks/useEntryAnomaly";
import { useJournalEntries, useJournalEntryDetail } from "@/hooks/useJournalEntries";
import {
  usePersonalityFeedback,
  usePersonalityMessages,
} from "@/hooks/usePersonalityMessages";
import type {
  JournalEntryDetailResponse,
  JournalEntryListItem,
} from "@/services/journal.service";
import type { PersonalityMessageResponse } from "@/services/personality.service";

const PERSONALITY_LABELS: Record<string, string> = {
  observer: "Observer",
  therapist: "Therapist",
  coach: "Coach",
  sassy: "Sassy",
  wargod: "Wargod",
  raphael: "Raphael",
};

const PERSONALITY_SURFACES: Record<string, string> = {
  observer: "bg-cyan-500/10 text-cyan-700 border-cyan-500/20",
  therapist: "bg-blue-500/10 text-blue-700 border-blue-500/20",
  coach: "bg-orange-500/10 text-orange-700 border-orange-500/20",
  sassy: "bg-pink-500/10 text-pink-700 border-pink-500/20",
  wargod: "bg-amber-500/10 text-amber-700 border-amber-500/20",
  raphael: "bg-violet-500/10 text-violet-700 border-violet-500/20",
};

function buildPreviewText(text: string, limit = 160): string {
  const compact = text.trim().replace(/\s+/g, " ");
  if (compact.length <= limit) {
    return compact;
  }
  return `${compact.slice(0, limit - 1).trimEnd()}…`;
}

function formatTimestamp(value?: string | null): string {
  if (!value) {
    return "Unknown time";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function formatStatus(value?: string): string {
  if (!value) {
    return "Unknown";
  }
  return value.replace(/_/g, " ");
}

function compareMessages(
  left: PersonalityMessageResponse,
  right: PersonalityMessageResponse
): number {
  const leftTime = new Date(left.created_at).getTime();
  const rightTime = new Date(right.created_at).getTime();

  if (leftTime !== rightTime) {
    return leftTime - rightTime;
  }

  if (left.multi_personality.is_primary !== right.multi_personality.is_primary) {
    return left.multi_personality.is_primary ? -1 : 1;
  }

  if (left.logical_slot_key !== right.logical_slot_key) {
    return left.logical_slot_key.localeCompare(right.logical_slot_key);
  }

  return left.id.localeCompare(right.id);
}

function MessageBubble({
  title,
  subtitle,
  text,
  bubbleClassName,
  avatarClassName,
  avatarLabel,
  footer,
}: {
  title: string;
  subtitle: string;
  text: string;
  bubbleClassName: string;
  avatarClassName: string;
  avatarLabel: string;
  footer?: ReactNode;
}) {
  return (
    <div className="flex items-start gap-3">
      <Avatar className={cn("h-10 w-10 border", avatarClassName)}>
        <AvatarFallback className="text-sm font-semibold">
          {avatarLabel}
        </AvatarFallback>
      </Avatar>
      <div className="min-w-0 flex-1 space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold">{title}</span>
          <span className="text-xs text-muted-foreground">{subtitle}</span>
        </div>
        <div className={cn("rounded-2xl border px-4 py-3 text-sm leading-6", bubbleClassName)}>
          <p className="whitespace-pre-wrap break-words">{text}</p>
        </div>
        {footer}
      </div>
    </div>
  );
}

export function Journal() {
  const { user } = useUser();
  const queryClient = useQueryClient();
  const submitMutation = useJournalSubmit();
  const [selectedEntryId, setSelectedEntryId] = useState<string | null>(null);
  const [latestSubmission, setLatestSubmission] = useState<{
    entryId: string;
    jobId: string;
  } | null>(null);

  const entriesQuery = useJournalEntries(user?.id || "", !!user?.id);
  const recentEntries = entriesQuery.data ?? [];
  const selectedListEntry = useMemo(
    () => recentEntries.find((entry) => entry.entry_id === selectedEntryId) ?? null,
    [recentEntries, selectedEntryId]
  );

  useEffect(() => {
    if (!recentEntries.length) {
      return;
    }

    if (!selectedEntryId) {
      setSelectedEntryId(recentEntries[0].entry_id);
      return;
    }

    const stillExists = recentEntries.some((entry) => entry.entry_id === selectedEntryId);
    if (!stillExists) {
      setSelectedEntryId(recentEntries[0].entry_id);
    }
  }, [recentEntries, selectedEntryId]);

  const detailQuery = useJournalEntryDetail(
    selectedEntryId || "",
    user?.id || "",
    !!selectedEntryId && !!user?.id
  );
  const selectedEntry = detailQuery.data;
  const selectedEntryStatus = selectedEntry?.status || selectedListEntry?.status || null;
  const isSelectedProcessing =
    selectedEntryStatus === "pending" || selectedEntryStatus === "processing";

  const selectedJobId =
    latestSubmission?.entryId === selectedEntryId ? latestSubmission.jobId : "";
  const statusQuery = useJournalEntryStatus(
    selectedJobId,
    user?.id || "",
    !!selectedJobId && !!user?.id && isSelectedProcessing
  );

  const anomalyQuery = useEntryAnomaly(
    selectedEntryId || "",
    user?.id || "",
    !!selectedEntryId && !!user?.id && selectedEntryStatus === "completed"
  );
  const personalityMessagesQuery = usePersonalityMessages(user?.id || "", selectedEntryId || undefined, {
    enabled: !!selectedEntryId && !!user?.id,
    limit: 100,
    refetchInterval: isSelectedProcessing ? 2000 : false,
  });
  const feedbackMutation = usePersonalityFeedback(user?.id || "");

  const transcriptMessages = useMemo(
    () => [...(personalityMessagesQuery.data ?? [])].sort(compareMessages),
    [personalityMessagesQuery.data]
  );

  const handleSubmit = async (text: string) => {
    if (!user) return;

    const response = await submitMutation.mutateAsync({
      user_id: user.id,
      content: text,
    });

    const createdAt = new Date().toISOString();
    const optimisticDetail: JournalEntryDetailResponse = {
      entry_id: response.entry_id,
      content: text,
      status: "processing",
      question_state: "none",
      created_at: createdAt,
      processed_at: null,
      processing_duration_ms: null,
      error_message: null,
    };
    const optimisticListEntry: JournalEntryListItem = {
      entry_id: response.entry_id,
      status: "processing",
      word_count: text.trim().split(/\s+/).filter(Boolean).length,
      preview_text: buildPreviewText(text),
      question_state: "none",
      created_at: createdAt,
      processed_at: null,
    };

    queryClient.setQueryData(
      ["journalEntryDetail", user.id, response.entry_id],
      optimisticDetail
    );
    queryClient.setQueryData<JournalEntryListItem[]>(
      ["journalEntries", user.id],
      (current) => {
        const existing = current ?? [];
        return [
          optimisticListEntry,
          ...existing.filter((entry) => entry.entry_id !== response.entry_id),
        ];
      }
    );

    setLatestSubmission({ entryId: response.entry_id, jobId: response.job_id });
    setSelectedEntryId(response.entry_id);
  };

  if (!user) {
    return (
      <div className="mx-auto max-w-4xl space-y-6">
        <h1 className="text-3xl font-display font-bold">Journal Entry</h1>
        <UserIdSelector />
      </div>
    );
  }

  const statusLabel = statusQuery.data?.status ?? selectedEntryStatus ?? "unknown";

  return (
    <div className="mx-auto max-w-7xl space-y-8">
      <div>
        <h1 className="mb-2 text-3xl font-display font-bold">Journal Entry</h1>
        <p className="text-muted-foreground">
          Write about your day, then review the entry thread and every personality reply in one place.
        </p>
      </div>

      <JournalEditor
        onSubmit={handleSubmit}
        isLoading={submitMutation.isPending}
        minWords={2}
        maxWords={10000}
      />

      <div className="grid gap-6 lg:grid-cols-[320px,minmax(0,1fr)] lg:items-start">
        <Card className="order-1">
          <CardHeader>
            <CardTitle>Recent Threads</CardTitle>
            <CardDescription>Select an entry to reopen its transcript.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {entriesQuery.isLoading && recentEntries.length === 0 && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading recent entries...
              </div>
            )}

            {recentEntries.map((entry) => {
              const isSelected = entry.entry_id === selectedEntryId;
              return (
                <button
                  key={entry.entry_id}
                  type="button"
                  onClick={() => setSelectedEntryId(entry.entry_id)}
                  className={cn(
                    "w-full rounded-2xl border px-4 py-3 text-left transition-colors",
                    isSelected
                      ? "border-primary bg-primary/5"
                      : "border-border bg-background hover:bg-muted/60"
                  )}
                >
                  <div className="mb-2 flex items-center justify-between gap-3">
                    <span className="text-sm font-semibold">
                      {formatTimestamp(entry.created_at)}
                    </span>
                    <Badge variant={isSelected ? "default" : "outline"} className="capitalize">
                      {formatStatus(entry.status)}
                    </Badge>
                  </div>
                  <p className="line-clamp-3 text-sm leading-6 text-foreground">
                    {entry.preview_text}
                  </p>
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    <span>{entry.word_count} words</span>
                    <span>Question state: {formatStatus(entry.question_state)}</span>
                  </div>
                </button>
              );
            })}

            {!entriesQuery.isLoading && recentEntries.length === 0 && (
              <div className="rounded-2xl border border-dashed px-4 py-6 text-sm text-muted-foreground">
                Submit your first entry to start a thread.
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="order-2 min-h-[640px]">
          <CardHeader className="space-y-4">
            <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
              <div>
                <CardTitle>Entry Transcript</CardTitle>
                <CardDescription>
                  {selectedEntry
                    ? `Started ${formatTimestamp(selectedEntry.created_at)}`
                    : "Select a recent entry to inspect the thread."}
                </CardDescription>
              </div>

              {selectedEntryId && (
                <div className="flex flex-wrap gap-2">
                  <Badge variant="secondary" className="capitalize">
                    {formatStatus(statusLabel)}
                  </Badge>
                  {selectedEntry && (
                    <Badge variant="outline" className="capitalize">
                      Question {formatStatus(selectedEntry.question_state)}
                    </Badge>
                  )}
                  {anomalyQuery.data && !anomalyQuery.data.missing && (
                    <Badge variant="outline">
                      Anomaly {anomalyQuery.data.score.toFixed(2)}/10
                    </Badge>
                  )}
                </div>
              )}
            </div>

            {selectedEntryId === latestSubmission?.entryId && selectedJobId && (
              <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                <span>Job ID: {selectedJobId}</span>
                {statusQuery.data && (
                  <span>Attempt count: {statusQuery.data.attempt_count}</span>
                )}
                {statusQuery.data?.last_error_code && (
                  <span className="text-destructive">
                    Last error: {statusQuery.data.last_error_code}
                  </span>
                )}
              </div>
            )}

            {detailQuery.isLoading && !selectedEntry && selectedEntryId && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading entry detail...
              </div>
            )}

            {statusQuery.error && (
              <p className="text-sm text-destructive">
                Failed to fetch job status: {(statusQuery.error as Error).message}
              </p>
            )}
            {detailQuery.error && (
              <p className="text-sm text-destructive">
                Failed to fetch entry detail: {(detailQuery.error as Error).message}
              </p>
            )}
          </CardHeader>

          <CardContent className="space-y-6">
            {!selectedEntryId && (
              <div className="rounded-2xl border border-dashed px-6 py-12 text-center text-sm text-muted-foreground">
                Pick an entry from the thread list to open the transcript.
              </div>
            )}

            {selectedEntry && (
              <>
                <div className="space-y-5">
                  <MessageBubble
                    title={user.name || "You"}
                    subtitle={formatTimestamp(selectedEntry.created_at)}
                    text={selectedEntry.content}
                    avatarLabel="ME"
                    avatarClassName="border-primary/20 bg-primary/10 text-primary"
                    bubbleClassName="border-primary/20 bg-primary/5"
                    footer={
                      selectedEntry.error_message ? (
                        <p className="text-xs text-destructive">
                          Processing error: {selectedEntry.error_message}
                        </p>
                      ) : null
                    }
                  />

                  {transcriptMessages.map((message) => {
                    const personalityLabel =
                      PERSONALITY_LABELS[message.personality] || message.personality;
                    const scopeLabel = message.multi_personality.is_primary
                      ? "Primary"
                      : `Secondary to ${message.multi_personality.primary_personality}`;

                    return (
                      <MessageBubble
                        key={message.id}
                        title={personalityLabel}
                        subtitle={`${scopeLabel} • ${formatTimestamp(message.created_at)}`}
                        text={message.message_text}
                        avatarLabel={personalityLabel.slice(0, 2).toUpperCase()}
                        avatarClassName={cn(
                          "border",
                          PERSONALITY_SURFACES[message.personality] ||
                            "bg-muted text-foreground border-border"
                        )}
                        bubbleClassName={cn(
                          "border",
                          PERSONALITY_SURFACES[message.personality] ||
                            "bg-muted text-foreground border-border"
                        )}
                        footer={
                          <div className="flex flex-wrap items-center gap-2">
                            <Badge variant="outline" className="capitalize">
                              {formatStatus(message.message_type)}
                            </Badge>
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              disabled={feedbackMutation.isPending}
                              onClick={() =>
                                feedbackMutation.mutate({
                                  message_id: message.id,
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
                                  message_id: message.id,
                                  feedback_type: "thumbs_down",
                                })
                              }
                            >
                              Off target
                            </Button>
                          </div>
                        }
                      />
                    );
                  })}

                  {isSelectedProcessing && !transcriptMessages.length && (
                    <div className="flex items-start gap-3">
                      <Avatar className="h-10 w-10 border border-border bg-muted">
                        <AvatarFallback>
                          <Loader2 className="h-4 w-4 animate-spin" />
                        </AvatarFallback>
                      </Avatar>
                      <div className="flex-1 rounded-2xl border border-dashed px-4 py-3 text-sm text-muted-foreground">
                        Waiting for personality replies to be committed to this thread...
                      </div>
                    </div>
                  )}

                  {!isSelectedProcessing && !transcriptMessages.length && (
                    <div className="flex items-start gap-3">
                      <Avatar className="h-10 w-10 border border-border bg-muted">
                        <AvatarFallback>
                          <MessageSquareText className="h-4 w-4" />
                        </AvatarFallback>
                      </Avatar>
                      <div className="flex-1 rounded-2xl border border-dashed px-4 py-3 text-sm text-muted-foreground">
                        No personality replies were found for this entry.
                      </div>
                    </div>
                  )}
                </div>

                <div className="rounded-2xl border border-dashed px-4 py-4">
                  <div className="mb-3 flex items-center gap-2 text-sm font-semibold">
                    <Sparkles className="h-4 w-4" />
                    Future Question Responses
                  </div>
                  <Textarea
                    disabled
                    className="min-h-[120px] resize-none"
                    placeholder="Follow-up replies will land here once the question-response API is wired into the thread."
                  />
                  <div className="mt-3 flex flex-col gap-3 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
                    <p>
                      This composer is intentionally disabled in this slice. The thread is read-only until the backend interaction API exists.
                    </p>
                    <Button type="button" size="sm" disabled>
                      <Send className="mr-2 h-4 w-4" />
                      Reply unavailable
                    </Button>
                  </div>
                </div>
              </>
            )}

            {selectedEntry && isSelectedProcessing && (
              <div className="rounded-2xl border border-dashed px-4 py-3 text-xs text-muted-foreground">
                The entry is still processing. The transcript refreshes automatically until the final replies and scores are available.
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
