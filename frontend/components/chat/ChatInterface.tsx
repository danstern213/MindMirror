import { useEffect, useState, useRef } from 'react';
import { useChatStore } from '@/stores/chatStore';
import { useAuth } from '@/contexts/AuthContext';
import { ChatMessage } from './ChatMessage';
import { ChatInput } from './ChatInput';
import { ChatThreadList } from './ChatThreadList';
import { FileUpload } from '../files/FileUpload';
import { SettingsPanel } from '../settings/SettingsPanel';
import { Dialog, Transition } from '@headlessui/react';
import { Fragment } from 'react';
import { Cog6ToothIcon, ChevronLeftIcon, ChevronRightIcon } from '@heroicons/react/24/outline';
import { Logo } from '../common/Logo';

// Processing status messages
const PROCESSING_STATES = {
  IDLE: '',
  SEARCHING: 'Searching documents...',
  ANALYZING: 'Analyzing context...',
  GENERATING: 'Generating response...'
};

export function ChatInterface() {
  const {
    threads,
    currentThread,
    loading,
    error,
    processingStatus,
    searchProgress,
    isStreaming,
    fetchThreads,
    createThread,
    setCurrentThread,
    deleteThread,
    sendMessage
  } = useChatStore();

  const { user, logout } = useAuth();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const hasInitialized = useRef(false);

  // Initialize chat when user is authenticated - only run once per session
  useEffect(() => {
    if (user && !loading && !hasInitialized.current) {
      hasInitialized.current = true;
      
      const initializeChat = async () => {
        try {
          // First fetch existing threads
          await fetchThreads();
          
          // Get the current state after fetching
          const currentState = useChatStore.getState();
          
          if (currentState.threads.length === 0) {
            // No existing threads, create a new one
            await createThread("New Chat");
          } else {
            // Set the first thread as current so user sees something
            const firstThread = currentState.threads[0];
            await setCurrentThread(firstThread);
          }
        } catch (error) {
          console.error('Error initializing chat:', error);
        }
      };
      
      initializeChat();
    }
  }, [user, loading, fetchThreads, createThread, setCurrentThread]);

  const handleCreateThread = async () => {
    try {
      await createThread("New Chat");
    } catch (error) {
      console.error('Error creating thread:', error);
    }
  };

  // Focus input on mount
  useEffect(() => {
    const inputElement = document.querySelector('textarea');
    if (inputElement) {
      inputElement.focus();
    }
  }, [currentThread]);

  if (!user) {
    return null;
  }

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-500"></div>
      </div>
    );
  }

  if (error) {
    const isTokenLimitError = error.includes("token limit");
    
    return (
      <div className="flex h-screen items-center justify-center">
        <div className={`max-w-md p-6 rounded-md border ${isTokenLimitError ? 'border-amber-300 bg-amber-50' : 'border-red-300 bg-red-50'}`}>
          <h3 className={`text-lg font-serif mb-2 ${isTokenLimitError ? 'text-amber-800' : 'text-red-800'}`}>
            {isTokenLimitError ? 'Token Limit Reached' : 'Error'}
          </h3>
          <p className={`${isTokenLimitError ? 'text-amber-700' : 'text-red-700'} font-serif`}>
            {error}
          </p>
          <button 
            onClick={() => window.location.reload()} 
            className="mt-4 px-4 py-2 bg-[var(--primary-accent)] text-[var(--paper-texture)] rounded-sm font-serif hover:bg-opacity-90"
          >
            Refresh Page
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 flex academia-container">
      {/* Sidebar */}
      <div className="flex flex-col w-64 border-r border-[var(--primary-dark)]">
        <div className="p-4 border-b border-[var(--primary-dark)]">
          <div className="flex items-center justify-between">
            <Logo />
            <button
              onClick={() => setSettingsOpen(true)}
              className="p-2 text-[var(--primary-accent)] hover:text-[var(--primary-dark)] rounded-sm hover:bg-[var(--paper-texture)]"
            >
              <Cog6ToothIcon className="h-5 w-5" />
            </button>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto">
          <ChatThreadList
            threads={threads}
            currentThreadId={currentThread?.id}
            onSelectThread={async (thread) => {
              try {
                await setCurrentThread(thread);
              } catch (error) {
                console.error('Error selecting thread:', error);
              }
            }}
            onCreateThread={handleCreateThread}
          />
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 flex flex-col">
        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4">
          <div className="max-w-4xl mx-auto">
            {currentThread ? (
              <>
                {loading && currentThread.messages.length === 0 ? (
                  <div className="h-full flex flex-col items-center justify-center px-4 py-16 text-center animate-fadeIn">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[var(--primary-accent)] mb-4"></div>
                    <p className="text-[var(--primary-dark)] font-serif">Loading chat messages...</p>
                  </div>
                ) : currentThread.messages.length > 0 ? (
                  <>
                    {currentThread.messages.map((message, index) => (
                      <ChatMessage 
                        key={index} 
                        message={message} 
                        isStreaming={index === currentThread.messages.length - 1 && isStreaming}
                      />
                    ))}
                    {processingStatus && processingStatus !== 'Generating response...' && (
                      <div className="p-4 flex items-center justify-center">
                        <div className="flex flex-col items-center space-y-2 w-full max-w-xs">
                          <div className="w-full bg-gray-200 rounded-full h-1.5">
                            <div 
                              className="bg-[var(--primary-accent)] h-1.5 rounded-full transition-all duration-300 ease-in-out" 
                              style={{ 
                                width: processingStatus === 'Searching documents...' ? `${Math.max(10, searchProgress)}%` : 
                                      processingStatus === 'Analyzing context...' ? '80%' : '0%' 
                              }}
                            ></div>
                          </div>
                          <div className="text-sm text-[var(--primary-dark)] font-serif">
                            {processingStatus}
                            {processingStatus === 'Searching documents...' && searchProgress > 0 && (
                              <span className="text-xs ml-1">({searchProgress}%)</span>
                            )}
                          </div>
                        </div>
                      </div>
                    )}
                  </>
                ) : (
                  <div className="h-full flex flex-col items-center justify-center px-4 py-16 text-center animate-fadeIn">
                    <div className="w-24 h-24 mb-8 animate-float">
                      <svg
                        viewBox="0 0 24 24"
                        fill="none"
                        xmlns="http://www.w3.org/2000/svg"
                        className="w-full h-full text-[var(--primary-accent)]"
                      >
                        <path
                          d="M4 19.5C4 18.837 4.26339 18.2011 4.73223 17.7322C5.20107 17.2634 5.83696 17 6.5 17H20"
                          stroke="currentColor"
                          strokeWidth="2"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                        <path
                          d="M6.5 2H20V22H6.5C5.83696 22 5.20107 21.7366 4.73223 21.2678C4.26339 20.7989 4 20.163 4 19.5V4.5C4 3.83696 4.26339 3.20107 4.73223 2.73223C5.20107 2.26339 5.83696 2 6.5 2Z"
                          stroke="currentColor"
                          strokeWidth="2"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                        <path
                          d="M8 7H16M8 11H16M8 15H12"
                          stroke="currentColor"
                          strokeWidth="2"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                    </div>
                    <h2 className="academia-heading mb-3">Ready to Explore Your Knowledge</h2>
                    <p className="academia-text max-w-md mb-8">
                      Start a conversation to uncover insights from your past writing. Ask questions, explore connections, and synthesize your knowledge.
                    </p>
                    <div className="flex flex-col gap-4 items-center">
                      <p className="text-sm academia-text">
                        Try asking: "What are the key themes in my recent notes? Be specific. and reference existing notes"
                      </p>
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="h-full flex items-center justify-center academia-text">
                Select a chat or start a new one
              </div>
            )}
          </div>
        </div>

        {/* Input */}
        <div className="border-t border-[var(--primary-dark)] bg-[var(--paper-texture)]">
          <div className="max-w-4xl mx-auto">
            <ChatInput
              onSendMessage={sendMessage}
              disabled={!currentThread || processingStatus !== ''}
            />
          </div>
        </div>
      </div>

      {/* File upload sidebar */}
      <div className={`${isSidebarCollapsed ? 'w-12' : 'w-80'} border-l border-[var(--primary-dark)] bg-[var(--paper-texture)] transition-all duration-300`}>
        <div className="p-4 border-b border-[var(--primary-dark)] flex items-center justify-between">
          {!isSidebarCollapsed && <h2 className="academia-heading">Documents</h2>}
          <button
            onClick={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
            className="p-2 text-[var(--paper-texture)] bg-[var(--primary-green)] rounded-sm hover:opacity-90"
          >
            {isSidebarCollapsed ? (
              <ChevronLeftIcon className="h-5 w-5" />
            ) : (
              <ChevronRightIcon className="h-5 w-5" />
            )}
          </button>
        </div>
        {!isSidebarCollapsed && (
          <div className="flex-1 overflow-y-auto">
            <FileUpload />
          </div>
        )}
      </div>

      {/* Settings modal */}
      <Transition appear show={settingsOpen} as={Fragment}>
        <Dialog
          as="div"
          className="relative z-10"
          onClose={() => setSettingsOpen(false)}
        >
          <Transition.Child
            as={Fragment}
            enter="ease-out duration-300"
            enterFrom="opacity-0"
            enterTo="opacity-100"
            leave="ease-in duration-200"
            leaveFrom="opacity-100"
            leaveTo="opacity-0"
          >
            <div className="fixed inset-0 bg-black bg-opacity-25" />
          </Transition.Child>

          <div className="fixed inset-0 overflow-y-auto">
            <div className="flex min-h-full items-center justify-center p-4">
              <Transition.Child
                as={Fragment}
                enter="ease-out duration-300"
                enterFrom="opacity-0 scale-95"
                enterTo="opacity-100 scale-100"
                leave="ease-in duration-200"
                leaveFrom="opacity-100 scale-100"
                leaveTo="opacity-0 scale-95"
              >
                <Dialog.Panel className="w-full max-w-2xl transform overflow-hidden academia-card shadow-xl transition-all">
                  <Dialog.Title
                    as="h3"
                    className="academia-heading"
                  >
                    Settings
                  </Dialog.Title>
                  <div className="mt-4">
                    <SettingsPanel />
                  </div>
                  <div className="mt-6 flex justify-between items-center px-4 pb-4">
                    <button
                      type="button"
                      className="inline-flex justify-center rounded-sm border border-[var(--primary-dark)] px-4 py-2 text-sm font-serif text-[var(--primary-dark)] hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-[var(--primary-green)] focus:ring-offset-2"
                      onClick={async () => {
                        await logout();
                        setSettingsOpen(false);
                      }}
                    >
                      Logout
                    </button>
                    <button
                      type="button"
                      className="inline-flex justify-center rounded-sm border border-[var(--primary-green)] px-4 py-2 text-sm font-serif text-[var(--paper-texture)] bg-[var(--primary-green)] hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-[var(--primary-green)] focus:ring-offset-2"
                      onClick={() => setSettingsOpen(false)}
                    >
                      Close
                    </button>
                  </div>
                </Dialog.Panel>
              </Transition.Child>
            </div>
          </div>
        </Dialog>
      </Transition>
    </div>
  );
} 