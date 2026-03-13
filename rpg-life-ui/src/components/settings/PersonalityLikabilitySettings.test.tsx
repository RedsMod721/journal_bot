import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { PersonalityLikabilitySettings } from "@/components/settings/PersonalityLikabilitySettings";
import { personalityService } from "@/services/personality.service";

const toastMock = vi.fn();

vi.mock("@/contexts/UserContext", () => ({
  useUser: () => ({
    user: { id: "11111111-1111-1111-1111-111111111111", name: "Test User" },
  }),
}));

vi.mock("@/hooks/use-toast", () => ({
  useToast: () => ({
    toast: toastMock,
  }),
}));

describe("PersonalityLikabilitySettings", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    toastMock.mockReset();
  });

  it("tracks dirty state, restores canceled changes, and saves updated likability scores", async () => {
    const initialState = {
      active_personality: "coach" as const,
      likability_scores: {
        observer: 80,
        therapist: 70,
        coach: 60,
        sassy: 50,
        wargod: 40,
        raphael: 60,
      },
      switch_cooldown_seconds: 600,
      multi_personality_annotations: 0,
    };
    const updatedState = {
      ...initialState,
      likability_scores: {
        ...initialState.likability_scores,
        observer: 81,
      },
    };

    vi.spyOn(personalityService, "getState")
      .mockResolvedValueOnce(initialState)
      .mockResolvedValue(updatedState);
    const updateSpy = vi
      .spyOn(personalityService, "updateLikabilityScores")
      .mockResolvedValue(updatedState);

    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    const user = userEvent.setup();

    render(
      <QueryClientProvider client={client}>
        <PersonalityLikabilitySettings />
      </QueryClientProvider>
    );

    const observerSlider = await screen.findByRole("slider", {
      name: "Observer likability",
    });
    expect(observerSlider).toHaveAttribute("aria-valuenow", "80");
    expect(
      screen.queryByRole("button", { name: "Save Likability" })
    ).not.toBeInTheDocument();

    fireEvent.keyDown(observerSlider, {
      key: "ArrowRight",
      code: "ArrowRight",
    });
    expect(await screen.findByRole("button", { name: "Save Likability" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => {
      expect(
        screen.queryByRole("button", { name: "Save Likability" })
      ).not.toBeInTheDocument();
    });
    expect(
      screen.getByRole("slider", { name: "Observer likability" })
    ).toHaveAttribute("aria-valuenow", "80");

    fireEvent.keyDown(screen.getByRole("slider", { name: "Observer likability" }), {
      key: "ArrowRight",
      code: "ArrowRight",
    });
    await user.click(screen.getByRole("button", { name: "Save Likability" }));

    await waitFor(() => {
      expect(updateSpy).toHaveBeenCalledWith(
        "11111111-1111-1111-1111-111111111111",
        {
          observer: 81,
          therapist: 70,
          coach: 60,
          sassy: 50,
          wargod: 40,
          raphael: 60,
        }
      );
    });

    await waitFor(() => {
      expect(
        screen.queryByRole("button", { name: "Save Likability" })
      ).not.toBeInTheDocument();
    });
    expect(
      screen.getByRole("slider", { name: "Observer likability" })
    ).toHaveAttribute("aria-valuenow", "81");
    expect(toastMock).toHaveBeenCalledWith({
      title: "Likability Updated",
      description: "Your personality likability settings have been saved.",
    });
  });
});
