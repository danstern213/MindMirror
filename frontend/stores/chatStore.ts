import { create } from 'zustand';
import { ChatThread, Message } from '@/types';
import { api } from '@/lib/api';

interface ChatState {
  threads: ChatThread[];
  currentThread: ChatThread | null;
  loading: boolean;
  error: string | null;
  processingStatus: string;
  fetchThreads: () => Promise<void>;
  createThread: (title?: string) => Promise<void>;
  setCurrentThread: (thread: ChatThread) => void;
  deleteThread: (threadId: string) => Promise<void>;
  sendMessage: (content: string) => Promise<void>;
  appendMessage: (message: Message) => void;
  appendStreamToken: (content: string) => void;
  setProcessingStatus: (status: string) => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
  threads: [],
  currentThread: null,
  loading: false,
  error: null,
  processingStatus: '',

  setProcessingStatus: (status: string) => {
    set({ processingStatus: status });
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

  setCurrentThread: (thread: ChatThread) => {
    set({ currentThread: thread });
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
    const { currentThread, setProcessingStatus } = get();
    
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

      try {
        // Stream the response
        setProcessingStatus('Searching documents...');
        await new Promise(resolve => setTimeout(resolve, 500));

        for await (const chunk of api.streamMessage(content, currentThread?.id)) {
          if (chunk.content) {
            if (get().processingStatus === 'Searching documents...') {
              setProcessingStatus('Analyzing context...');
              await new Promise(resolve => setTimeout(resolve, 500));
            }
            if (get().processingStatus === 'Analyzing context...') {
              setProcessingStatus('Generating response...');
              await new Promise(resolve => setTimeout(resolve, 500));
            }
            get().appendStreamToken(chunk.content);
          }
          if (chunk.done && chunk.sources) {
            // Update the last message with sources
            set(state => {
              if (!state.currentThread) return state;
              const messages = [...state.currentThread.messages];
              const lastMessage = messages[messages.length - 1];
              if (lastMessage && lastMessage.role === 'assistant') {
                lastMessage.sources = chunk.sources;
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
          }
        }
      } catch (error) {
        // Handle streaming error but keep the messages
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
        const messages = state.currentThread.messages.slice(0, -1); // Remove last message
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
        lastMessage.content += content;
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
  }
})); 