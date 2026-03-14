import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Palmtree } from "lucide-react";
import { useActivateVacation, useEndVacation, useCurrentArc } from "@/hooks/useArcs";

interface VacationToggleProps {
  userId: string;
}

export function VacationToggle({ userId }: VacationToggleProps) {
  const { data } = useCurrentArc(userId);
  const activateVacation = useActivateVacation();
  const endVacation = useEndVacation();
  const [durationDays, setDurationDays] = useState("");

  const isVacationActive =
    data?.active &&
    data.arc?.arc_type === "event" &&
    data.arc?.event_name === "vacation_mode";

  const handleActivate = () => {
    const days = durationDays ? parseFloat(durationDays) : undefined;
    activateVacation.mutate({ userId, duration_days: days });
  };

  const handleEnd = () => {
    endVacation.mutate({ userId });
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Palmtree className="w-5 h-5 text-yellow-500" />
            Vacation Mode
          </CardTitle>
          {isVacationActive && (
            <Badge className="bg-yellow-500/10 text-yellow-500 border-yellow-500/20">
              Active
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">
          Pauses skill decay while you're away. Your previous arc resumes when
          vacation ends.
        </p>

        {isVacationActive ? (
          <Button
            variant="outline"
            disabled={endVacation.isPending}
            onClick={handleEnd}
          >
            {endVacation.isPending ? "Ending…" : "End Vacation"}
          </Button>
        ) : (
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="vacation-duration">Duration (days, optional)</Label>
              <Input
                id="vacation-duration"
                type="number"
                min="0.1"
                max="365"
                step="0.5"
                placeholder="e.g. 7"
                value={durationDays}
                onChange={(e) => setDurationDays(e.target.value)}
                className="w-32"
              />
            </div>
            <Button
              disabled={activateVacation.isPending}
              onClick={handleActivate}
            >
              {activateVacation.isPending ? "Activating…" : "Start Vacation"}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
