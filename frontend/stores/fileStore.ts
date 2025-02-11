import { create } from 'zustand';
import { api } from '@/lib/api';
import { FileUpload } from '@/types';

interface UploadProgress {
  currentFile: string;
  currentFileIndex: number;
  totalFiles: number;
  status: 'idle' | 'uploading' | 'processing' | 'complete' | 'error';
}

interface FileState {
  totalFiles: number | null;
  uploading: boolean;
  loading: boolean;
  error: string | null;
  uploadProgress: UploadProgress;
  fetchTotalFiles: () => Promise<void>;
  uploadFile: (file: File) => Promise<FileUpload>;
  clearError: () => void;
  setUploadProgress: (progress: Partial<UploadProgress>) => void;
}

export const useFileStore = create<FileState>((set) => ({
  totalFiles: null,
  uploading: false,
  loading: false,
  error: null,
  uploadProgress: {
    currentFile: '',
    currentFileIndex: 0,
    totalFiles: 0,
    status: 'idle'
  },
  clearError: () => set({ error: null }),
  setUploadProgress: (progress) => 
    set((state) => ({ 
      uploadProgress: { ...state.uploadProgress, ...progress } 
    })),

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
    set((state) => ({ 
      uploading: true, 
      error: null,
      uploadProgress: {
        ...state.uploadProgress,
        currentFile: file.name,
        status: 'uploading'
      }
    }));

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

      // Log if file is empty
      if (file.size === 0) {
        console.log(`Processing empty file: ${file.name}`);
      }

      set(state => ({
        uploadProgress: {
          ...state.uploadProgress,
          status: 'processing'
        }
      }));

      const response = await api.uploadFile(file);
      
      // Log the upload response
      console.log('File upload response:', {
        fileName: file.name,
        fileSize: file.size,
        status: response.status,
        embeddingStatus: response.embedding_status
      });

      set(state => ({
        uploading: false,
        uploadProgress: {
          ...state.uploadProgress,
          status: 'complete'
        }
      }));
      
      return response;
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to upload file';
      console.error('Error uploading file:', {
        fileName: file.name,
        fileSize: file.size,
        fileType: file.type,
        error
      });
      
      set(state => ({
        error: errorMessage,
        uploading: false,
        uploadProgress: {
          ...state.uploadProgress,
          status: 'error'
        }
      }));
      
      throw error;
    } finally {
      // Ensure uploading state is always reset
      set(state => ({ ...state, uploading: false }));
    }
  }
})); 