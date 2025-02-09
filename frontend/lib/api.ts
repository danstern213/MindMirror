import { ChatResponse, ChatThread, FileUpload, SearchResult, UserSettings } from '@/types';
import { supabase } from './supabase';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

class ApiClient {
  private async fetch(endpoint: string, options: RequestInit = {}) {
    const url = `${API_BASE}${endpoint}`;
    
    // Get the session from Supabase
    const { data: { session } } = await supabase.auth.getSession();
    
    if (!session?.access_token) {
      console.error('No active session found');
      throw new Error('No active session');
    }

    // Special handling for file uploads
    const isFileUpload = options.body instanceof FormData;
    
    const headers = isFileUpload ? {
      // For file uploads, only set Authorization header
      'Authorization': `Bearer ${session.access_token}`
    } : {
      // For all other requests, include Content-Type: application/json
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${session.access_token}`,
      ...options.headers,
    };

    try {
      console.log(`API Request: ${url}`, { 
        method: options.method || 'GET',
        isFileUpload,
        headers: {
          ...headers,
          Authorization: `Bearer ${session.access_token.substring(0, 10)}...`
        }
      });
      
      const response = await fetch(url, {
        ...options,
        headers,
        credentials: 'include',
      });

      if (!response.ok) {
        let errorMessage: string;
        try {
          const errorData = await response.json();
          errorMessage = errorData.detail || errorData.message || `HTTP error! status: ${response.status}`;
          
          // Log the full error response for debugging
          console.error('API Error Response:', {
            status: response.status,
            statusText: response.statusText,
            errorData
          });
          
          // For file upload errors, add more context
          if (endpoint === '/files/upload') {
            errorMessage = `File upload failed: ${errorMessage}`;
          }
        } catch {
          errorMessage = `Request failed with status: ${response.status} ${response.statusText}`;
        }

        // If unauthorized, try to refresh the session
        if (response.status === 401) {
          console.log('Unauthorized request, attempting to refresh session...');
          const { data: { session: newSession }, error: refreshError } = await supabase.auth.refreshSession();
          
          if (refreshError) {
            console.error('Session refresh failed:', refreshError);
            throw new Error('Session expired. Please log in again.');
          }
          
          if (newSession) {
            console.log('Session refreshed successfully, retrying request...');
            // Retry the request with the new token
            const retryHeaders = isFileUpload ? {
              'Authorization': `Bearer ${newSession.access_token}`
            } : {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${newSession.access_token}`,
              ...options.headers,
            };
            
            const retryResponse = await fetch(url, {
              ...options,
              headers: retryHeaders,
              credentials: 'include',
            });
            
            if (!retryResponse.ok) {
              throw new Error(errorMessage);
            }
            
            return retryResponse;
          }
        }
        
        throw new Error(errorMessage);
      }

      return response;
    } catch (error) {
      console.error('API request failed:', {
        url,
        method: options.method || 'GET',
        error: error instanceof Error ? error.message : 'Unknown error',
        fullError: error
      });
      
      // Ensure we always throw an Error object with a string message
      if (error instanceof Error) {
        throw error;
      } else if (typeof error === 'string') {
        throw new Error(error);
      } else {
        throw new Error('An unexpected error occurred');
      }
    }
  }

  // Chat endpoints
  async createThread(title: string = 'New Chat'): Promise<ChatThread> {
    const response = await this.fetch('/chat/threads', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ title })
    });
    return response.json();
  }

  async getThreads(): Promise<ChatThread[]> {
    try {
      const { data: { session } } = await supabase.auth.getSession();
      if (!session) {
        console.log('No active session found when fetching threads');
        return [];
      }
      console.log('Fetching threads with session:', {
        sessionId: session.access_token?.substring(0, 10) + '...',
        userId: session.user?.id
      });
      const response = await this.fetch('/chat/threads');
      return response.json();
    } catch (error: any) {
      console.error('Failed to fetch threads:', {
        message: error.message,
        status: error.status,
        name: error.name,
        stack: error.stack,
        response: error.response,
        supabaseError: error.error,
        supabaseErrorDescription: error.error_description
      });
      return [];
    }
  }

  async getThread(threadId: string): Promise<ChatThread> {
    const response = await this.fetch(`/chat/threads/${threadId}`);
    return response.json();
  }

  async deleteThread(threadId: string): Promise<void> {
    await this.fetch(`/chat/threads/${threadId}`, {
      method: 'DELETE',
    });
  }

  async *streamMessage(message: string, threadId?: string): AsyncGenerator<ChatResponse> {
    // Get the session to include user_id
    const { data: { session } } = await supabase.auth.getSession();
    if (!session?.user?.id) {
      throw new Error('No active session');
    }

    const response = await this.fetch('/chat/message', {
      method: 'POST',
      body: JSON.stringify({
        message,
        thread_id: threadId,
        user_id: session.user.id
      }),
    });

    const reader = response.body?.getReader();
    if (!reader) throw new Error('No response body');

    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6);
          if (data === '[DONE]') return;
          try {
            yield JSON.parse(data) as ChatResponse;
          } catch (e) {
            console.error('Error parsing SSE data:', e);
          }
        }
      }
    }
  }

  // File endpoints
  async uploadFile(file: File): Promise<FileUpload> {
    try {
      const formData = new FormData();
      formData.append('file', file, file.name);  // Explicitly include filename

      // Log file details for debugging
      console.log('Preparing file upload:', {
        name: file.name,
        type: file.type,
        size: file.size,
        formDataEntries: Array.from(formData.entries()).map(([key, value]) => ({
          key,
          type: value instanceof File ? 'File' : typeof value,
          fileName: value instanceof File ? value.name : null,
          size: value instanceof File ? value.size : null
        }))
      });

      const response = await this.fetch('/files/upload', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const errorDetail = await response.json();
        console.error('File upload failed:', {
          status: response.status,
          statusText: response.statusText,
          errorDetail
        });
        throw new Error(errorDetail.detail || 'File upload failed');
      }
      
      const result = await response.json();
      console.log('File upload successful:', result);
      return result;
    } catch (error) {
      console.error('File upload error:', {
        error,
        file: {
          name: file.name,
          type: file.type,
          size: file.size
        }
      });
      throw error;
    }
  }

  async listFiles(): Promise<FileUpload[]> {
    const response = await this.fetch('/files/list');
    return response.json();
  }

  async getFileCount(): Promise<number> {
    const response = await this.fetch('/files/count');
    const data = await response.json();
    return data.count;
  }

  // Search endpoints
  async search(query: string): Promise<SearchResult[]> {
    const response = await this.fetch('/search', {
      method: 'POST',
      body: JSON.stringify({ query }),
    });
    return response.json();
  }

  // Settings endpoints
  async getUserSettings(): Promise<UserSettings> {
    const response = await this.fetch('/settings');
    return response.json();
  }

  async updateUserSettings(settings: Partial<UserSettings>): Promise<UserSettings> {
    const response = await this.fetch('/settings', {
      method: 'PATCH',
      body: JSON.stringify(settings),
    });
    return response.json();
  }
}

export const api = new ApiClient(); 