import {
  decayRateToForgivenessSliderValue,
  decaySliderLabel,
  forgivenessSliderValueToDecayRate,
  graceSliderLabel,
} from "@/lib/forgiveness";

describe("forgiveness slider helpers", () => {
  it("maps larger decay slider values to more forgiveness", () => {
    expect(decayRateToForgivenessSliderValue(0.15)).toBe(85);
    expect(decayRateToForgivenessSliderValue(0.05)).toBe(95);
    expect(forgivenessSliderValueToDecayRate(0)).toBe(1);
    expect(forgivenessSliderValueToDecayRate(100)).toBe(0);
    expect(decaySliderLabel(0)).toBe("Half-life: 1 day");
    expect(decaySliderLabel(100)).toBe("Half-life: never");
  });

  it("keeps grace labels increasing with larger values", () => {
    expect(graceSliderLabel(0)).toBe("Decay starts immediately");
    expect(graceSliderLabel(7)).toBe("7 days before decay starts");
  });
});
