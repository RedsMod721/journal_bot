import { Outlet, useLocation } from "react-router-dom";
import { AnimatePresence } from "framer-motion";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";
import { PageTransition } from "./PageTransition";
import { SkipLink } from "@/components/accessibility/SkipLink";
import { useUser } from "@/contexts/UserContext";
import { useUserStats } from "@/hooks/useUserStats";

export function MainLayout() {
  const { user, logout } = useUser();
  const { data: stats } = useUserStats(user?.id ?? "");

  const location = useLocation();

  return (
    <div className="flex h-screen bg-background">
      <SkipLink />
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header
          onLogout={logout}
          user={
            user
              ? {
                  name: user.name,
                  level: stats?.current_level ?? 1,
                  avatar: undefined,
                }
              : undefined
          }
        />
        <main className="flex-1 overflow-y-auto" id="main-content">
          <div className="container mx-auto p-8">
            <AnimatePresence mode="wait">
              <PageTransition key={location.pathname}>
                <Outlet />
              </PageTransition>
            </AnimatePresence>
          </div>
        </main>
      </div>
    </div>
  );
}
