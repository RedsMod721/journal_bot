import { BrowserRouter, Routes, Route } from "react-router-dom";
import { ThemeProvider } from "@/components/theme-provider";
import { UserProvider } from "@/contexts/UserContext";
import { Toaster } from "@/components/ui/toaster";
import { MainLayout } from "@/components/layout/MainLayout";
import { Dashboard } from "@/pages/Dashboard";
import { Journal } from "@/pages/Journal";
import { Skills } from "@/pages/Skills";
import { Quests } from "@/pages/Quests";
import { Profile } from "@/pages/Profile";

function App() {
  return (
    <ThemeProvider defaultTheme="dark" storageKey="rpg-life-ui-theme">
      <UserProvider>
        <BrowserRouter>
          <Routes>
            <Route element={<MainLayout />}>
              <Route index element={<Dashboard />} />
              <Route path="/journal" element={<Journal />} />
              <Route path="/skills" element={<Skills />} />
              <Route path="/quests" element={<Quests />} />
              <Route path="/profile" element={<Profile />} />
            </Route>
          </Routes>
          <Toaster />
        </BrowserRouter>
      </UserProvider>
    </ThemeProvider>
  );
}

export default App;
