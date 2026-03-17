import { BrowserRouter, Navigate, Routes, Route, useLocation } from "react-router-dom";
import { ThemeProvider } from "@/components/theme-provider";
import { UserProvider } from "@/contexts/UserContext";
import { useUser } from "@/contexts/UserContext";
import { RealmPreferencesProvider } from "@/contexts/RealmPreferencesContext";
import { Toaster } from "@/components/ui/toaster";
import { MainLayout } from "@/components/layout/MainLayout";
import { Account } from "@/pages/Account";
import { Dashboard } from "@/pages/Dashboard";
import { Journal } from "@/pages/Journal";
import { ThemesSkills } from "@/pages/ThemesSkills";
import { Quests } from "@/pages/Quests";
import { Profile } from "@/pages/Profile";
import { Settings } from "@/pages/Settings";

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useUser();
  const location = useLocation();
  if (isLoading) return null;
  if (!user) return <Navigate to="/account" state={{ from: location }} replace />;
  return <>{children}</>;
}

function App() {
  return (
    <ThemeProvider defaultTheme="dark" storageKey="rpg-life-ui-theme">
      <UserProvider>
        <RealmPreferencesProvider>
          <BrowserRouter>
            <Routes>
              <Route path="/account" element={<Account />} />
              <Route element={<RequireAuth><MainLayout /></RequireAuth>}>
                <Route index element={<Dashboard />} />
                <Route path="/journal" element={<Journal />} />
                <Route path="/skills" element={<ThemesSkills />} />
                <Route path="/quests" element={<Quests />} />
                <Route path="/profile" element={<Profile />} />
                <Route path="/settings" element={<Settings />} />
              </Route>
            </Routes>
            <Toaster />
          </BrowserRouter>
        </RealmPreferencesProvider>
      </UserProvider>
    </ThemeProvider>
  );
}

export default App;
