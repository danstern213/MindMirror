import { create } from 'zustand';
import { api } from '@/lib/api';

interface FileState {
  totalFiles: number | null;
  uploading: boolean;
  loading: boolean;
  error: string | null;
  fetchTotalFiles: () => Promise<void>;
  uploadFile: (file: File) => Promise<void>;
  clearError: () => void;
}

export const useFileStore = create<FileState>((set) => ({
  totalFiles: null,
  uploading: false,
  loading: false,
  error: null,
  clearError: () => set({ error: null }),

  fetchTotalFiles: async () => {
    set({ loading: true, error: null });
    try {
      const count = await api.getFileCount();
      set({ totalFiles: count, loading: false });
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to fetch file count';
      console.error('Error fetching file count:', error);
      set({ error: errorMessage, loading: false });
    }
  },

  uploadFile: async (file: File) => {
    set({ uploading: true, error: null });
    try {
      // Validate file size (10MB limit)
      const maxSize = 10 * 1024 * 1024; // 10MB in bytes
      if (file.size > maxSize) {
        throw new Error(`File size exceeds 10MB limit. Current size: ${(file.size / (1024 * 1024)).toFixed(2)}MB`);
      }

      // Validate file type
      const allowedTypes = ['.txt', '.pdf', '.md', '.doc', '.docx'];
      const fileExt = '.' + file.name.split('.').pop()?.toLowerCase();
      if (!allowedTypes.includes(fileExt)) {
        throw new Error(`File type ${fileExt} is not supported. Allowed types: ${allowedTypes.join(', ')}`);
      }

      await api.uploadFile(file);
      set({ uploading: false });
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to upload file';
      console.error('Error uploading file:', {
        fileName: file.name,
        fileSize: file.size,
        fileType: file.type,
        error
      });
      set({ error: errorMessage, uploading: false });
    }
  }
})); 