import type {
  ForgivenessConfig,
  ForgivenessPreset,
} from "@/services/forgiveness.service";

export interface ForgivenessEditorState {
  skill_decay: number;
  skill_grace: number;
  insight_decay: number;
  insight_grace: number;
}

const MAX_SLIDER_VALUE = 100;

export const FORGIVENESS_PRESET_NAMES: Record<ForgivenessPreset, string> = {
  balanced: "Balanced",
  hardcore: "Hardcore",
  lenient: "Lenient",
  zen: "Zen",
  adaptive: "Adaptive",
  custom: "Custom",
};

export const FORGIVENESS_PRESET_DESCRIPTIONS: Record<ForgivenessPreset, string> = {
  balanced: "Standard forgiveness with moderate decay and grace periods.",
  hardcore: "Short grace periods and fast decay for a stricter mode.",
  lenient: "A softer mode with slower decay and more room to miss days.",
  zen: "Maximum forgiveness with the slowest decay and the longest grace periods.",
  adaptive: "Starts balanced and adjusts the effective decay rate from your recent activity.",
  custom: "Your own final forgiveness values.",
};

function clampSliderValue(value: number): number {
  return Math.max(0, Math.min(MAX_SLIDER_VALUE, Math.round(value)));
}

export function getForgivenessPresetName(preset: ForgivenessPreset): string {
  return FORGIVENESS_PRESET_NAMES[preset] ?? preset;
}

export function decayRateToForgivenessSliderValue(rate: number): number {
  return clampSliderValue((1 - rate) * MAX_SLIDER_VALUE);
}

export function forgivenessSliderValueToDecayRate(value: number): number {
  return clampSliderValue(MAX_SLIDER_VALUE - value) / MAX_SLIDER_VALUE;
}

export function graceDaysToSliderValue(days: number): number {
  return clampSliderValue(days);
}

export function sliderValueToGraceDays(value: number): number {
  return clampSliderValue(value);
}

export function halfLifeDaysFromDecayRate(rate: number): number | null {
  if (rate <= 0) {
    return null;
  }
  return Math.round(Math.LN2 / rate);
}

export function formatHalfLifeFromDecayRate(rate: number): string {
  const days = halfLifeDaysFromDecayRate(rate);
  if (days === null) {
    return "Never decays";
  }
  return days === 1 ? "1 day" : `${days} days`;
}

export function decaySliderLabel(value: number): string {
  const halfLife = formatHalfLifeFromDecayRate(
    forgivenessSliderValueToDecayRate(value),
  );
  return halfLife === "Never decays"
    ? "Half-life: never"
    : `Half-life: ${halfLife}`;
}

export function graceSliderLabel(value: number): string {
  const days = sliderValueToGraceDays(value);
  if (days === 0) {
    return "Decay starts immediately";
  }
  return `${days} ${days === 1 ? "day" : "days"} before decay starts`;
}

export function configToForgivenessEditorState(
  config: ForgivenessConfig,
): ForgivenessEditorState {
  return {
    skill_decay: decayRateToForgivenessSliderValue(config.skill_decay_rate),
    skill_grace: graceDaysToSliderValue(config.skill_grace_period_days),
    insight_decay: decayRateToForgivenessSliderValue(config.insight_decay_rate),
    insight_grace: graceDaysToSliderValue(config.insight_grace_period_days),
  };
}

export function getForgivenessLoadErrorMessage(error: unknown): string {
  const message = error instanceof Error ? error.message : "Unknown error";
  if (message === "Not Found") {
    return "Forgiveness API unavailable on the current backend. Restart the API server on port 8000.";
  }
  return message;
}
