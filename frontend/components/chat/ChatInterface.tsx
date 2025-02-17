import { useEffect, useState } from 'react';
import { useChatStore } from '@/stores/chatStore';
import { useAuth } from '@/contexts/AuthContext';
import { ChatMessage } from './ChatMessage';
import { ChatInput } from './ChatInput';
import { ChatThreadList } from './ChatThreadList';
import { FileUpload } from '../files/FileUpload';
import { SettingsPanel } from '../settings/SettingsPanel';
import { Dialog, Transition } from '@headlessui/react';
import { Fragment } from 'react';
import { Cog6ToothIcon } from '@heroicons/react/24/outline';
import { Logo } from '@/components/common/Logo';

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
    isStreaming,
    fetchThreads,
    createThread,
    setCurrentThread,
    deleteThread,
    sendMessage
  } = useChatStore();

  const { user } = useAuth();
  const [settingsOpen, setSettingsOpen] = useState(false);

  // Auto-create thread when no threads exist
  useEffect(() => {
    const createInitialThread = async () => {
      if (user && !loading && threads.length === 0 && !error) {
        try {
          await createThread("New Chat");
        } catch (error) {
          console.error('Error creating initial thread:', error);
        }
      }
    };
    createInitialThread();
  }, [user, loading, threads.length, createThread, error]);

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
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-red-500">{error}</div>
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
            onSelectThread={setCurrentThread}
            onCreateThread={handleCreateThread}
            onDeleteThread={deleteThread}
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
                {currentThread.messages.length > 0 ? (
                  <>
                    {currentThread.messages.map((message, index) => (
                      <ChatMessage 
                        key={index} 
                        message={message} 
                        isStreaming={index === currentThread.messages.length - 1 && isStreaming}
                      />
                    ))}
                    {processingStatus && (
                      <div className="p-4 flex items-center justify-center">
                        <div className="flex items-center space-x-2">
                          <div className="animate-pulse h-2 w-2 rounded-full bg-[var(--primary-accent)]"></div>
                          <div className="text-sm text-[var(--primary-dark)] font-serif">{processingStatus}</div>
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
      <div className="w-80 border-l border-[var(--primary-dark)] bg-[var(--paper-texture)]">
        <div className="p-4 border-b border-[var(--primary-dark)]">
          <h2 className="academia-heading">Documents</h2>
        </div>
        <div className="flex-1 overflow-y-auto">
          <FileUpload />
        </div>
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
                  <div className="mt-6">
                    <button
                      type="button"
                      className="inline-flex justify-center rounded-md border border-transparent bg-indigo-100 px-4 py-2 text-sm font-medium text-indigo-900 hover:bg-indigo-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2"
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