import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { useCreateEventArc } from "@/hooks/useArcs";

interface CreateEventArcDialogProps {
  userId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CreateEventArcDialog({
  userId,
  open,
  onOpenChange,
}: CreateEventArcDialogProps) {
  const createEventArc = useCreateEventArc();

  const [eventName, setEventName] = useState("");
  const [durationDays, setDurationDays] = useState("");
  const [rewardMult, setRewardMult] = useState(1.0);
  const [requirementMult, setRequirementMult] = useState(1.0);
  const [decayMult, setDecayMult] = useState(1.0);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!eventName.trim()) return;

    createEventArc.mutate(
      {
        userId,
        data: {
          event_name: eventName.trim(),
          duration_days: durationDays ? parseFloat(durationDays) : undefined,
          xp_reward_multiplier: rewardMult,
          xp_requirement_multiplier: requirementMult,
          decay_rate_multiplier: decayMult,
        },
      },
      {
        onSuccess: () => {
          onOpenChange(false);
          setEventName("");
          setDurationDays("");
          setRewardMult(1.0);
          setRequirementMult(1.0);
          setDecayMult(1.0);
        },
      }
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Create Event Arc</DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-5">
          {/* Event name */}
          <div className="space-y-1.5">
            <Label htmlFor="event-name">Event Name *</Label>
            <Input
              id="event-name"
              placeholder="e.g. Conference Week"
              value={eventName}
              onChange={(e) => setEventName(e.target.value)}
              required
              maxLength={100}
            />
          </div>

          {/* Duration */}
          <div className="space-y-1.5">
            <Label htmlFor="event-duration">Duration (days, optional)</Label>
            <Input
              id="event-duration"
              type="number"
              min="0.1"
              max="365"
              step="0.5"
              placeholder="Leave blank for indefinite"
              value={durationDays}
              onChange={(e) => setDurationDays(e.target.value)}
            />
          </div>

          {/* XP Reward Multiplier */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>XP Reward Multiplier</Label>
              <span className="text-sm font-medium">{rewardMult.toFixed(2)}x</span>
            </div>
            <Slider
              min={0.1}
              max={5}
              step={0.05}
              value={[rewardMult]}
              onValueChange={([v]) => setRewardMult(v)}
            />
          </div>

          {/* XP Requirement Multiplier */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>XP Requirement Multiplier</Label>
              <span className="text-sm font-medium">{requirementMult.toFixed(2)}x</span>
            </div>
            <Slider
              min={0.1}
              max={5}
              step={0.05}
              value={[requirementMult]}
              onValueChange={([v]) => setRequirementMult(v)}
            />
          </div>

          {/* Decay Rate Multiplier */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>Decay Rate Multiplier</Label>
              <span className="text-sm font-medium">{decayMult.toFixed(2)}x</span>
            </div>
            <Slider
              min={0}
              max={2}
              step={0.05}
              value={[decayMult]}
              onValueChange={([v]) => setDecayMult(v)}
            />
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={!eventName.trim() || createEventArc.isPending}
            >
              {createEventArc.isPending ? "Creating…" : "Create Arc"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
