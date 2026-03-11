import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { Header } from "@/components/layout/Header";

vi.mock("@/components/theme-toggle", () => ({
  ThemeToggle: () => <div data-testid="theme-toggle" />,
}));

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

describe("Header", () => {
  it("navigates to /settings from the user dropdown", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={["/"]}>
        <Header user={{ name: "Test User", level: 7 }} />
        <LocationProbe />
      </MemoryRouter>
    );

    await user.click(screen.getByLabelText("User menu for Test User"));
    await user.click(screen.getByRole("menuitem", { name: "Settings" }));

    expect(screen.getByTestId("location")).toHaveTextContent("/settings");
  });
});
