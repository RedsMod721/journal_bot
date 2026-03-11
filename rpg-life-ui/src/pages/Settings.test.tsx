import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RealmPreferencesProvider } from "@/contexts/RealmPreferencesContext";
import { Settings } from "@/pages/Settings";
import { userService } from "@/services/user.service";

vi.mock("@/contexts/UserContext", () => ({
  useUser: () => ({
    user: { id: "11111111-1111-1111-1111-111111111111", name: "Test User" },
  }),
}));

vi.mock("@/components/settings/ForgivenessSettings", () => ({
  ForgivenessSettings: () => <div>Forgiveness Settings</div>,
}));

describe("Settings page preferences", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("loads realm presets and updates the selected preset", async () => {
    const presetsSpy = vi
      .spyOn(userService, "getRealmRankWordingPresets")
      .mockResolvedValue([
        {
          preset: "standard",
          name: "Standard",
          ranks: [{ rank: "F", wording: "Beginner" }],
        },
        {
          preset: "arcane_magic_system",
          name: "Arcane Magic System",
          ranks: [{ rank: "F", wording: "Novice" }],
        },
      ]);

    const preferencesSpy = vi
      .spyOn(userService, "getUserPreferences")
      .mockResolvedValue({
        user_id: "11111111-1111-1111-1111-111111111111",
        realm: {
          scope: {
            visual: true,
            naming: true,
            messages: false,
            llm: false,
          },
          ranks_wording: { preset: "standard" },
        },
        skill_hierarchy: {
          default_blocked_preference: false,
        },
      });

    const updateSpy = vi
      .spyOn(userService, "updateUserPreferences")
      .mockResolvedValue({
        user_id: "11111111-1111-1111-1111-111111111111",
        realm: {
          scope: {
            visual: true,
            naming: true,
            messages: false,
            llm: false,
          },
          ranks_wording: { preset: "arcane_magic_system" },
        },
        skill_hierarchy: {
          default_blocked_preference: false,
        },
      });

    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });

    const user = userEvent.setup();
    render(
      <QueryClientProvider client={client}>
        <RealmPreferencesProvider>
          <Settings />
        </RealmPreferencesProvider>
      </QueryClientProvider>
    );

    expect(await screen.findByText("Realm Rank Wording")).toBeInTheDocument();
    expect(presetsSpy).toHaveBeenCalledTimes(1);
    expect(preferencesSpy).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole("button", { name: "Arcane Magic System" }));

    await waitFor(() => {
      expect(updateSpy).toHaveBeenCalledWith(
        "11111111-1111-1111-1111-111111111111",
        {
          realm: {
            scope: {
              visual: true,
              naming: true,
              messages: false,
              llm: false,
            },
            ranks_wording: { preset: "arcane_magic_system" },
          },
        }
      );
    });
  });

  it("updates default blocked preference from settings toggle", async () => {
    vi.spyOn(userService, "getRealmRankWordingPresets").mockResolvedValue([
      {
        preset: "standard",
        name: "Standard",
        ranks: [{ rank: "F", wording: "Beginner" }],
      },
    ]);

    vi.spyOn(userService, "getUserPreferences").mockResolvedValue({
      user_id: "11111111-1111-1111-1111-111111111111",
      realm: {
        scope: {
          visual: true,
          naming: true,
          messages: false,
          llm: false,
        },
        ranks_wording: { preset: "standard" },
      },
      skill_hierarchy: {
        default_blocked_preference: false,
      },
    });

    const updateSpy = vi
      .spyOn(userService, "updateUserPreferences")
      .mockResolvedValue({
        user_id: "11111111-1111-1111-1111-111111111111",
        realm: {
          scope: {
            visual: true,
            naming: true,
            messages: false,
            llm: false,
          },
          ranks_wording: { preset: "standard" },
        },
        skill_hierarchy: {
          default_blocked_preference: true,
        },
      });

    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });

    const user = userEvent.setup();
    render(
      <QueryClientProvider client={client}>
        <RealmPreferencesProvider>
          <Settings />
        </RealmPreferencesProvider>
      </QueryClientProvider>
    );

    const toggle = await screen.findByRole("switch", {
      name: "Block new skills by default",
    });
    await user.click(toggle);

    await waitFor(() => {
      expect(updateSpy).toHaveBeenCalledWith(
        "11111111-1111-1111-1111-111111111111",
        {
          skill_hierarchy: {
            default_blocked_preference: true,
          },
        }
      );
    });
  });
});
