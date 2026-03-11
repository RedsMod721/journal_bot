import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Slider } from "@/components/ui/slider";
import { useUser } from "@/contexts/UserContext";
import { useForgivenessConfig, useForgivenessPresets } from "@/hooks/useForgiveness";
import { useToast } from "@/hooks/use-toast";
import {
  configToForgivenessEditorState,
  decaySliderLabel,
  FORGIVENESS_PRESET_DESCRIPTIONS,
  getForgivenessLoadErrorMessage,
  getForgivenessPresetName,
  graceSliderLabel,
  type ForgivenessEditorState,
  forgivenessSliderValueToDecayRate,
  sliderValueToGraceDays,
} from "@/lib/forgiveness";
import {
  DEFAULT_FORGIVENESS_PRESET,
  forgivenessService,
  type ForgivenessConfig,
  type ForgivenessPreset,
} from "@/services/forgiveness.service";

const DEFAULT_SLIDERS: ForgivenessEditorState = {
  skill_decay: 95,
  skill_grace: 7,
  insight_decay: 90,
  insight_grace: 3,
};

export function ForgivenessSettings() {
  const { user } = useUser();
  const userId = user?.id ?? "";
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const {
    data: presets = [],
    isLoading: presetsLoading,
    error: presetsError,
  } = useForgivenessPresets();
  const {
    data: config,
    isLoading: configLoading,
    error: configError,
  } = useForgivenessConfig(userId);

  const [savedSliders, setSavedSliders] = useState(DEFAULT_SLIDERS);
  const [pendingSliders, setPendingSliders] = useState(DEFAULT_SLIDERS);

  useEffect(() => {
    if (!config) {
      return;
    }
    const sliders = configToForgivenessEditorState(config);
    setSavedSliders(sliders);
    setPendingSliders(sliders);
  }, [config]);

  const syncConfig = (nextConfig: ForgivenessConfig) => {
    queryClient.setQueryData(["forgivenessConfig", userId], nextConfig);
    void queryClient.invalidateQueries({
      queryKey: ["forgivenessConfig", userId],
    });
    const nextSliders = configToForgivenessEditorState(nextConfig);
    setSavedSliders(nextSliders);
    setPendingSliders(nextSliders);
  };

  const updatePresetMutation = useMutation({
    mutationFn: async (preset: ForgivenessPreset) =>
      forgivenessService.updatePreset(userId, preset),
    onSuccess: (nextConfig) => {
      syncConfig(nextConfig);
      const presetName = getForgivenessPresetName(nextConfig.preset);
      toast({
        title: "Preset Applied",
        description: `Switched to ${presetName}.`,
      });
    },
  });

  const saveCustomMutation = useMutation({
    mutationFn: async (params: ForgivenessEditorState) => {
      await forgivenessService.updatePreset(userId, "custom");
      return forgivenessService.updateCustomParams(userId, {
        skill_decay_rate: forgivenessSliderValueToDecayRate(params.skill_decay),
        skill_grace_days: sliderValueToGraceDays(params.skill_grace),
        insight_decay_rate: forgivenessSliderValueToDecayRate(params.insight_decay),
        insight_grace_days: sliderValueToGraceDays(params.insight_grace),
      });
    },
    onSuccess: (nextConfig) => {
      syncConfig(nextConfig);
      toast({
        title: "Custom Settings Saved",
        description: "Your forgiveness parameters have been updated.",
      });
    },
  });

  const isBusy = updatePresetMutation.isPending || saveCustomMutation.isPending;
  const isLoading = presetsLoading || configLoading;
  const error = presetsError ?? configError;
  const isDirty =
    JSON.stringify(savedSliders) !== JSON.stringify(pendingSliders);
  const activePreset = config?.preset ?? DEFAULT_FORGIVENESS_PRESET;
  const activePresetName =
    presets.find((item) => item.preset === activePreset)?.name ??
    getForgivenessPresetName(activePreset);

  if (!userId) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Forgiveness Settings</CardTitle>
          <CardDescription>Select a user to edit forgiveness settings.</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Forgiveness Settings</CardTitle>
          <CardDescription>Loading your forgiveness configuration...</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Skeleton className="h-10 w-56" />
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Forgiveness Settings</CardTitle>
          <CardDescription className="text-destructive">
            Failed to load forgiveness settings: {getForgivenessLoadErrorMessage(error)}
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Forgiveness Settings</CardTitle>
        <CardDescription>
          Adjust how much progress the system preserves when you miss time.
          Moving right always means more forgiveness.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="space-y-2">
          <Label htmlFor="forgiveness-preset">Preset</Label>
          <Select
            value={activePreset}
            disabled={isBusy}
            onValueChange={(value) => {
              const preset = value as ForgivenessPreset;
              if (preset !== activePreset) {
                updatePresetMutation.mutate(preset);
              }
            }}
          >
            <SelectTrigger id="forgiveness-preset" className="w-56">
              <SelectValue placeholder={activePresetName} />
            </SelectTrigger>
            <SelectContent>
              {presets.map((preset) => (
                <SelectItem key={preset.preset} value={preset.preset}>
                  {preset.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-sm text-muted-foreground">
            {FORGIVENESS_PRESET_DESCRIPTIONS[activePreset]}
          </p>
        </div>

        <div className="space-y-5">
          <div className="space-y-2">
            <div className="flex items-baseline justify-between">
              <Label>Skill Decay Rate</Label>
              <span className="font-mono text-sm text-muted-foreground">
                {decaySliderLabel(pendingSliders.skill_decay)}
              </span>
            </div>
            <Slider
              min={0}
              max={100}
              step={1}
              value={[pendingSliders.skill_decay]}
              onValueChange={([value]) =>
                setPendingSliders((current) => ({
                  ...current,
                  skill_decay: value,
                }))
              }
              disabled={isBusy}
              aria-label="Skill decay forgiveness"
            />
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>Fast decay</span>
              <span>Never decays</span>
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex items-baseline justify-between">
              <Label>Skill Grace Period</Label>
              <span className="font-mono text-sm text-muted-foreground">
                {graceSliderLabel(pendingSliders.skill_grace)}
              </span>
            </div>
            <Slider
              min={0}
              max={100}
              step={1}
              value={[pendingSliders.skill_grace]}
              onValueChange={([value]) =>
                setPendingSliders((current) => ({
                  ...current,
                  skill_grace: value,
                }))
              }
              disabled={isBusy}
              aria-label="Skill grace period forgiveness"
            />
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>No grace</span>
              <span>100 days</span>
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex items-baseline justify-between">
              <Label>Insight Decay Rate</Label>
              <span className="font-mono text-sm text-muted-foreground">
                {decaySliderLabel(pendingSliders.insight_decay)}
              </span>
            </div>
            <Slider
              min={0}
              max={100}
              step={1}
              value={[pendingSliders.insight_decay]}
              onValueChange={([value]) =>
                setPendingSliders((current) => ({
                  ...current,
                  insight_decay: value,
                }))
              }
              disabled={isBusy}
              aria-label="Insight decay forgiveness"
            />
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>Fast decay</span>
              <span>Never decays</span>
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex items-baseline justify-between">
              <Label>Insight Grace Period</Label>
              <span className="font-mono text-sm text-muted-foreground">
                {graceSliderLabel(pendingSliders.insight_grace)}
              </span>
            </div>
            <Slider
              min={0}
              max={100}
              step={1}
              value={[pendingSliders.insight_grace]}
              onValueChange={([value]) =>
                setPendingSliders((current) => ({
                  ...current,
                  insight_grace: value,
                }))
              }
              disabled={isBusy}
              aria-label="Insight grace period forgiveness"
            />
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>No grace</span>
              <span>100 days</span>
            </div>
          </div>
        </div>

        {isDirty && (
          <div className="flex gap-3 pt-2">
            <Button
              variant="outline"
              size="sm"
              disabled={isBusy}
              onClick={() => setPendingSliders(savedSliders)}
            >
              Cancel
            </Button>
            <Button
              size="sm"
              disabled={isBusy}
              onClick={() => saveCustomMutation.mutate(pendingSliders)}
            >
              {saveCustomMutation.isPending ? "Saving..." : "Save Custom"}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
