import { create } from "zustand";
import {
  apiGetMe,
  apiLogin,
  apiLogout,
  apiRegister,
  type User,
} from "@/lib/api";

interface AuthState {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;

  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name?: string) => Promise<void>;
  logout: () => Promise<void>;
  checkSession: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isLoading: true,
  isAuthenticated: false,

  login: async (email, password) => {
    const { user } = await apiLogin(email, password);
    set({ user, isAuthenticated: true });
    const { useOcrStore } = await import("@/store/ocr-store");
    useOcrStore.setState({ isHydrated: false, isHydrating: false });
    void useOcrStore.getState().hydrateFromServer();
  },

  register: async (email, password, name) => {
    const { user } = await apiRegister(email, password, name);
    set({ user, isAuthenticated: true });
    const { useOcrStore } = await import("@/store/ocr-store");
    useOcrStore.setState({ isHydrated: false, isHydrating: false });
    void useOcrStore.getState().hydrateFromServer();
  },

  logout: async () => {
    await apiLogout();
    set({ user: null, isAuthenticated: false });
  },

  checkSession: async () => {
    set({ isLoading: true });
    try {
      const { user } = await apiGetMe();
      set({ user, isAuthenticated: !!user, isLoading: false });
    } catch {
      set({ user: null, isAuthenticated: false, isLoading: false });
    }
  },
}));
