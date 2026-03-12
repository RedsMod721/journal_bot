import { useState } from "react";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Loader2, CheckCircle2, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";

interface JournalEditorProps {
  onSubmit?: (text: string) => Promise<void>;
  isLoading?: boolean;
  minWords?: number;
  maxWords?: number;
  className?: string;
}

export function JournalEditor({
  onSubmit,
  isLoading = false,
  minWords = 2,
  maxWords = 10000,
  className,
}: JournalEditorProps) {
  const [text, setText] = useState("");
  const [wordCount, setWordCount] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const handleTextChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const newText = e.target.value;
    setText(newText);

    const words = newText.trim().split(/\s+/).filter(Boolean);
    setWordCount(words.length);

    if (error) setError(null);
    if (success) setSuccess(false);
  };

  const handleSubmit = async () => {
    if (wordCount < minWords) {
      setError(`Entry too short. Minimum ${minWords} words required.`);
      return;
    }

    if (wordCount > maxWords) {
      setError(`Entry too long. Maximum ${maxWords} words allowed.`);
      return;
    }

    try {
      if (onSubmit) {
        await onSubmit(text);
        setSuccess(true);
        setText("");
        setWordCount(0);
      }
    } catch {
      setSuccess(false);
    }
  };

  const isValid = wordCount >= minWords && wordCount <= maxWords;

  const wordCountColor =
    wordCount === 0
      ? "text-muted-foreground"
      : wordCount < minWords || wordCount > maxWords
        ? "text-destructive"
        : "text-accent";

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>New Journal Entry</CardTitle>
        <CardDescription>
          Write about your day. What did you learn? What skills did you
          practice?
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        <Textarea
          value={text}
          onChange={handleTextChange}
          placeholder="Today I practiced..."
          className="min-h-[300px] resize-none font-sans"
          disabled={isLoading}
        />

        {error && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {success && (
          <Alert className="border-accent bg-accent/10">
            <CheckCircle2 className="h-4 w-4 text-accent" />
            <AlertDescription className="text-accent">
              Entry submitted successfully! Processing in background...
            </AlertDescription>
          </Alert>
        )}
      </CardContent>

      <CardFooter className="flex items-center justify-between">
        <div className="flex items-center gap-4 text-sm">
          <div className={cn("font-medium", wordCountColor)}>
            {wordCount} {wordCount === 1 ? "word" : "words"}
          </div>
          {wordCount > 0 && (
            <div className="text-muted-foreground">
              {wordCount < minWords && `${minWords - wordCount} more needed`}
              {wordCount >= minWords &&
                wordCount <= maxWords &&
                "✓ Valid"}
              {wordCount > maxWords &&
                `${wordCount - maxWords} over limit`}
            </div>
          )}
        </div>

        <Button onClick={handleSubmit} disabled={!isValid || isLoading}>
          {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          {isLoading ? "Submitting..." : "Submit Entry"}
        </Button>
      </CardFooter>
    </Card>
  );
}
