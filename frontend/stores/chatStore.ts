import { create } from 'zustand';
import { ChatThread, Message, ChatResponse } from '@/types';
import { api } from '@/lib/api';

interface ChatState {
  threads: ChatThread[];
  currentThread: ChatThread | null;
  loading: boolean;
  error: string | null;
  processingStatus: string;
  searchProgress: number;
  currentStreamingContent: string;
  isStreaming: boolean;
  fetchThreads: () => Promise<void>;
  createThread: (title?: string) => Promise<void>;
  setCurrentThread: (thread: ChatThread) => Promise<void>;
  deleteThread: (threadId: string) => Promise<void>;
  sendMessage: (content: string) => Promise<void>;
  appendMessage: (message: Message) => void;
  appendStreamToken: (content: string) => void;
  setProcessingStatus: (status: string) => void;
  setSearchProgress: (progress: number) => void;
  loadThreadMessages: (threadId: string) => Promise<void>;
}

export const useChatStore = create<ChatState>((set, get) => ({
  threads: [],
  currentThread: null,
  loading: false,
  error: null,
  processingStatus: '',
  searchProgress: 0,
  currentStreamingContent: '',
  isStreaming: false,

  setProcessingStatus: (status: string) => {
    set({ processingStatus: status });
  },

  setSearchProgress: (progress: number) => {
    set({ searchProgress: progress });
  },

  fetchThreads: async () => {
    set({ loading: true, error: null });
    try {
      const threads = await api.getThreads();
      set({ threads, loading: false });
    } catch (error) {
      set({ error: (error as Error).message, loading: false });
    }
  },

  createThread: async (title = 'New Chat') => {
    set({ loading: true, error: null });
    try {
      const thread = await api.createThread(title);
      set(state => ({
        threads: [thread, ...state.threads],
        currentThread: thread,
        loading: false
      }));
    } catch (error) {
      console.error('Error creating thread:', error);
      set({ 
        error: error instanceof Error ? error.message : 'Failed to create thread',
        loading: false 
      });
    }
  },

  setCurrentThread: async (thread: ChatThread) => {
    set({ currentThread: thread, loading: true, error: null });
    
    try {
      // Lazy load messages for the selected thread
      const messages = await api.getThreadMessages(thread.id);
      
      // Update the thread with loaded messages
      const updatedThread = {
        ...thread,
        messages: messages.map((msg: any) => ({
          role: msg.role,
          content: msg.content,
          timestamp: msg.created_at,
          sources: msg.sources || []
        }))
      };
      
      set(state => ({
        currentThread: updatedThread,
        threads: state.threads.map(t =>
          t.id === updatedThread.id ? updatedThread : t
        ),
        loading: false
      }));
    } catch (error: any) {
      console.error('Error loading thread messages:', error);
      set({ 
        error: error.message || 'Failed to load chat messages. Please refresh the page and try again.',
        loading: false 
      });
      
      // Still set the thread but with empty messages so user can see the error
      set({ currentThread: { ...thread, messages: [] } });
    }
  },

  deleteThread: async (threadId: string) => {
    set({ loading: true, error: null });
    try {
      await api.deleteThread(threadId);
      set(state => ({
        threads: state.threads.filter(t => t.id !== threadId),
        currentThread: state.currentThread?.id === threadId ? null : state.currentThread,
        loading: false
      }));
    } catch (error) {
      set({ error: (error as Error).message, loading: false });
    }
  },

  sendMessage: async (content: string) => {
    const { currentThread, setProcessingStatus, setSearchProgress } = get();

    try {
      // Add user message immediately
      const userMessage: Message = {
        role: 'user',
        content,
        timestamp: new Date().toISOString()
      };
      get().appendMessage(userMessage);
      
      // Create assistant message placeholder
      const assistantMessage: Message = {
        role: 'assistant',
        content: '',
        timestamp: new Date().toISOString()
      };
      get().appendMessage(assistantMessage);

      set({ isStreaming: true, searchProgress: 0 });

      try {
        setProcessingStatus('Searching documents...');
        
        // Flag to control the progress simulation
        let isSearching = true;
        
        // Simulate incremental search progress that continues until we get a response
        const simulateSearchProgress = async () => {
          let progress = 0;
          
          // Initial fast progress up to 30%
          while (progress < 30 && isSearching) {
            await new Promise(resolve => setTimeout(resolve, 200));
            progress += 5;
            setSearchProgress(progress);
          }
          
          // Slower progress from 30% to 50%
          while (progress < 50 && isSearching) {
            await new Promise(resolve => setTimeout(resolve, 300));
            progress += 3;
            setSearchProgress(progress);
          }
          
          // Very slow progress from 50% to 90%, ensuring we don't reach 100% before getting a response
          while (isSearching) {
            await new Promise(resolve => setTimeout(resolve, 500));
            // Gradually slow down the progress increments as we get higher
            const increment = Math.max(1, Math.floor(10 / (progress / 10)));
            progress = Math.min(90, progress + increment);
            setSearchProgress(progress);
          }
        };
        
        // Start the progress simulation
        simulateSearchProgress();

        for await (const chunk of api.streamMessage(content, currentThread?.id)) {
          if (chunk.content) {
            // Stop the search progress simulation when we get the first content chunk
            isSearching = false;
            
            if (get().processingStatus === 'Searching documents...') {
              setProcessingStatus('Analyzing context...');
              setSearchProgress(0); // Reset for next phase
            }
            if (get().processingStatus === 'Analyzing context...') {
              setProcessingStatus('Generating response...');
            }

            // Update immediately without accumulating
            set(state => {
              if (!state.currentThread) return state;
              const messages = [...state.currentThread.messages];
              const lastMessage = messages[messages.length - 1];
              if (lastMessage && lastMessage.role === 'assistant') {
                lastMessage.content += chunk.content;
                if (chunk.sources) {
                  lastMessage.sources = chunk.sources;
                }
              }
              return {
                currentThread: {
                  ...state.currentThread,
                  messages
                }
              };
            });
          }
        }
      } catch (error) {
        console.error('Error in message streaming:', error);
        throw error;
      }
    } catch (error: any) {
      console.error('Error in chat message flow:', {
        error,
        message: error.message,
        status: error.status,
        detail: error.detail
      });

      // Remove the assistant's placeholder message if there was an error
      set(state => {
        if (!state.currentThread) return state;
        const messages = state.currentThread.messages.slice(0, -1);
        const updatedThread = {
          ...state.currentThread,
          messages
        };
        return {
          currentThread: updatedThread,
          threads: state.threads.map(t =>
            t.id === updatedThread.id ? updatedThread : t
          ),
          error: error.detail || error.message || 'Failed to send message'
        };
      });
    } finally {
      set({ isStreaming: false, searchProgress: 0 });
      setProcessingStatus('');
    }
  },

  appendMessage: (message: Message) => {
    set(state => {
      if (!state.currentThread) return state;
      const updatedThread = {
        ...state.currentThread,
        messages: [...state.currentThread.messages, message]
      };
      return {
        currentThread: updatedThread,
        threads: state.threads.map(t =>
          t.id === updatedThread.id ? updatedThread : t
        )
      };
    });
  },

  appendStreamToken: (content: string) => {
    set(state => {
      if (!state.currentThread) return state;
      const messages = [...state.currentThread.messages];
      const lastMessage = messages[messages.length - 1];
      if (lastMessage && lastMessage.role === 'assistant') {
        lastMessage.content = content;
      }
      const updatedThread = {
        ...state.currentThread,
        messages
      };
      return {
        currentThread: updatedThread,
        threads: state.threads.map(t =>
          t.id === updatedThread.id ? updatedThread : t
        )
      };
    });
  },

  loadThreadMessages: async (threadId: string) => {
    set({ loading: true, error: null });
    try {
      const messages = await api.getThreadMessages(threadId);
      
      // Update the current thread with loaded messages
      set(state => {
        if (!state.currentThread || state.currentThread.id !== threadId) return state;
        
        const updatedThread = {
          ...state.currentThread,
          messages: messages.map((msg: any) => ({
            role: msg.role,
            content: msg.content,
            timestamp: msg.created_at,
            sources: msg.sources || []
          }))
        };
        
        return {
          currentThread: updatedThread,
          threads: state.threads.map(t =>
            t.id === updatedThread.id ? updatedThread : t
          ),
          loading: false
        };
      });
    } catch (error: any) {
      console.error('Error loading thread messages:', error);
      set({ 
        error: error.message || 'Failed to load chat messages. Please refresh the page and try again.',
        loading: false 
      });
    }
  }
})); 