import { ThemeToggle } from "@/components/theme-toggle";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { useNavigate } from "react-router-dom";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Settings, LogOut, User } from "lucide-react";

interface HeaderProps {
  title?: string;
  user?: {
    name: string;
    avatar?: string;
    level: number;
  };
  onLogout?: () => void;
}

export function Header({ title, user, onLogout }: HeaderProps) {
  const navigate = useNavigate();

  return (
    <header className="border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 sticky top-0 z-50">
      <div className="flex items-center justify-between px-8 py-4">
        {/* Page Title */}
        <div>
          {title && (
            <h2 className="text-2xl font-bold">{title}</h2>
          )}
        </div>

        {/* Right Side - User Menu + Theme Toggle */}
        <div className="flex items-center gap-4">
          <ThemeToggle />

          {user && (
            <DropdownMenu>
              <DropdownMenuTrigger
                className="outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-md"
                aria-label={`User menu for ${user.name}`}
              >
                <div className="flex items-center gap-3 cursor-pointer hover:opacity-80 transition-opacity">
                  <div className="text-right">
                    <p className="text-sm font-medium">{user.name}</p>
                    <p className="text-xs text-muted-foreground">
                      Level {user.level}
                    </p>
                  </div>
                  <Avatar>
                    <AvatarImage src={user.avatar} alt={user.name} />
                    <AvatarFallback aria-hidden="true">
                      {user.name.substring(0, 2).toUpperCase()}
                    </AvatarFallback>
                  </Avatar>
                </div>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <DropdownMenuLabel>My Account</DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem onSelect={() => navigate("/profile")}>
                  <User className="mr-2 h-4 w-4" aria-hidden="true" />
                  <span>Profile</span>
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => navigate("/settings")}>
                  <Settings className="mr-2 h-4 w-4" aria-hidden="true" />
                  <span>Settings</span>
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  className="text-destructive focus:text-destructive"
                  onSelect={onLogout}
                >
                  <LogOut className="mr-2 h-4 w-4" aria-hidden="true" />
                  <span>Log out</span>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      </div>
    </header>
  );
}
