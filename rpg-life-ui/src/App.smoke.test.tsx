import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import App from "@/App";

vi.mock("@/contexts/UserContext", () => ({
  UserProvider: ({ children }: { children: ReactNode }) => children,
  useUser: () => ({
    user: { id: "11111111-1111-1111-1111-111111111111", name: "Test User" },
    setUser: vi.fn(),
    setUserId: vi.fn(),
    availableUsers: [],
    isLoading: false,
    error: null,
  }),
}));
vi.mock("@/contexts/RealmPreferencesContext", () => ({
  RealmPreferencesProvider: ({ children }: { children: ReactNode }) => children,
}));

vi.mock("@/pages/Dashboard", () => ({ Dashboard: () => <div>Dashboard Page</div> }));
vi.mock("@/pages/Journal", () => ({ Journal: () => <div>Journal Page</div> }));
vi.mock("@/pages/ThemesSkills", () => ({
  ThemesSkills: () => <div>Themes & Skills Page</div>,
}));
vi.mock("@/pages/Quests", () => ({ Quests: () => <div>Quests Page</div> }));
vi.mock("@/pages/Profile", () => ({ Profile: () => <div>Profile Page</div> }));
vi.mock("@/pages/Settings", () => ({ Settings: () => <div>Settings Page</div> }));
vi.mock("@/hooks/useUserStats", () => ({
  useUserStats: () => ({
    data: { current_level: 7 },
    isLoading: false,
    error: null,
  }),
}));

describe("App routing smoke test", () => {
  it("renders default route", () => {
    const client = new QueryClient();
    render(
      <QueryClientProvider client={client}>
        <App />
      </QueryClientProvider>
    );

    expect(screen.getByText("Dashboard Page")).toBeInTheDocument();
  });
});
