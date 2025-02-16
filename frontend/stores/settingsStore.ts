import { create } from 'zustand';
import { UserSettings } from '@/types';
import { api } from '@/lib/api';

interface SettingsState {
  settings: UserSettings | null;
  loading: boolean;
  error: string | null;
  fetchSettings: () => Promise<void>;
  updateSettings: (settings: Partial<UserSettings>) => Promise<void>;
}

const DEFAULT_SETTINGS: UserSettings = {
  personal_info: '',
  model: 'gpt-4-0125-preview',
  excluded_folders: []
};

export const useSettingsStore = create<SettingsState>((set) => ({
  settings: null,
  loading: false,
  error: null,

  fetchSettings: async () => {
    set({ loading: true, error: null });
    try {
      const settings = await api.getUserSettings();
      set({ settings: { ...DEFAULT_SETTINGS, ...settings }, loading: false });
    } catch (error) {
      set({
        settings: DEFAULT_SETTINGS,
        error: (error as Error).message,
        loading: false
      });
    }
  },

  updateSettings: async (newSettings: Partial<UserSettings>) => {
    set({ loading: true, error: null });
    try {
      const settings = await api.updateUserSettings(newSettings);
      set({ settings: { ...DEFAULT_SETTINGS, ...settings }, loading: false });
    } catch (error) {
      set({ error: (error as Error).message, loading: false });
    }
  }
})); 