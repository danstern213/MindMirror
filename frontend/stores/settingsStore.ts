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
  memory: '',
  model: 'gpt-4-0125-preview',
  excluded_folders: [],
  suggested_prompts: [
    "What are three small wins I can aim for today?",
    "Help me reflect on my day. What went well, and what could have gone better?",
    "Write a draft of my weekly review for this week",
    "Summarize me as a person, including my strengths and growth opportunities",
    "Let's gratitude journal together",
    "Generate 5 creative writing prompts for me.",
    "Summarize a concept or book I wrote about recently",
    "Ask me a relevant thought-provoking question to journal about"
  ]
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