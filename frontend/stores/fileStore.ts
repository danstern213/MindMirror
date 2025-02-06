import { create } from 'zustand';
import { api } from '@/lib/api';

interface FileState {
  totalFiles: number | null;
  uploading: boolean;
  loading: boolean;
  error: string | null;
  fetchTotalFiles: () => Promise<void>;
  uploadFile: (file: File) => Promise<void>;
}

export const useFileStore = create<FileState>((set) => ({
  totalFiles: null,
  uploading: false,
  loading: false,
  error: null,

  fetchTotalFiles: async () => {
    set({ loading: true, error: null });
    try {
      const count = await api.getFileCount();
      set({ totalFiles: count, loading: false });
    } catch (error) {
      set({ error: (error as Error).message, loading: false });
    }
  },

  uploadFile: async (file: File) => {
    set({ uploading: true, error: null });
    try {
      await api.uploadFile(file);
      set({ uploading: false });
    } catch (error) {
      set({ error: (error as Error).message, uploading: false });
    }
  }
})); 