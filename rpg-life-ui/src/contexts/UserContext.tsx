import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { userService, type UserListItem, type UserCreateRequest } from "@/services/user.service";

interface User {
  id: string;
  name: string;
  email?: string;
}

interface UserContextType {
  user: User | null;
  setUser: (user: User | null) => void;
  setUserId: (userId: string) => Promise<void>;
  createUser: (payload: UserCreateRequest) => Promise<void>;
  logout: () => void;
  availableUsers: UserListItem[];
  isLoading: boolean;
  error: string | null;
}

const UserContext = createContext<UserContextType | undefined>(undefined);
const USER_ID_STORAGE_KEY = "rpg_life_user_id";
const DEFAULT_USER_ID = import.meta.env.VITE_USER_ID || "";
const UUID_REGEX =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function UserProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [availableUsers, setAvailableUsers] = useState<UserListItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const setActiveUser = (picked: UserListItem) => {
    localStorage.setItem(USER_ID_STORAGE_KEY, picked.id);
    setUser({
      id: picked.id,
      name:
        picked.display_name ||
        picked.username ||
        picked.email ||
        `User ${picked.id.slice(0, 8)}`,
      email: picked.email ?? undefined,
    });
    setError(null);
  };

  const hydrateFromUsers = async (candidateUserId?: string) => {
    const users = await userService.listUsers();
    setAvailableUsers(users);

    if (users.length === 0) {
      setUser(null);
      setError("No users found in backend. Create a user first.");
      return;
    }

    const picked =
      users.find((u) => u.id === candidateUserId) ||
      users.find((u) => u.id === DEFAULT_USER_ID) ||
      users[0];
    setActiveUser(picked);
  };

  const setUserId = async (userId: string) => {
    const trimmed = userId.trim();
    if (!trimmed) return;
    if (!UUID_REGEX.test(trimmed)) {
      throw new Error("Invalid UUID format. Paste a valid user UUID.");
    }

    // Fast path: use already loaded users without requiring a network call.
    const localMatch = availableUsers.find((u) => u.id === trimmed);
    if (localMatch) {
      setActiveUser(localMatch);
      return;
    }

    // Validation path: check backend stats endpoint for this user.
    const stats = await userService.getUserStats(trimmed);
    localStorage.setItem(USER_ID_STORAGE_KEY, stats.user_id);
    setUser({
      id: stats.user_id,
      name: `User ${stats.user_id.slice(0, 8)}`,
    });
    setError(null);
  };

  const createUser = async (payload: UserCreateRequest) => {
    const newUser = await userService.createUser(payload);
    setAvailableUsers((prev) => [...prev, newUser]);
    setActiveUser(newUser);
  };

  const logout = () => {
    localStorage.removeItem(USER_ID_STORAGE_KEY);
    setUser(null);
    setError(null);
  };

  useEffect(() => {
    const loadUser = async () => {
      const storedUserId = localStorage.getItem(USER_ID_STORAGE_KEY) || DEFAULT_USER_ID;
      try {
        await hydrateFromUsers(storedUserId);
      } catch (err) {
        setUser(null);
        setAvailableUsers([]);
        setError(
          err instanceof Error
            ? err.message
            : "Failed to load users from backend. Check API availability."
        );
      } finally {
        setIsLoading(false);
      }
    };

    loadUser();
  }, []);

  return (
    <UserContext.Provider
      value={{ user, setUser, setUserId, createUser, logout, availableUsers, isLoading, error }}
    >
      {children}
    </UserContext.Provider>
  );
}

export function useUser() {
  const context = useContext(UserContext);
  if (context === undefined) {
    throw new Error("useUser must be used within a UserProvider");
  }
  return context;
}
