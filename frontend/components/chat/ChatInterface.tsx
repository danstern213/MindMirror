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
    <div className="fixed inset-0 flex bg-white">
      {/* Sidebar */}
      <div className="flex flex-col w-64 border-r">
        <div className="p-4 border-b">
          <div className="flex items-center justify-between">
            <h1 className="text-xl font-semibold text-gray-900">AI Note Copilot</h1>
            <button
              onClick={() => setSettingsOpen(true)}
              className="p-2 text-gray-400 hover:text-gray-500 rounded-full hover:bg-gray-100"
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
                      <div className="animate-pulse h-2 w-2 rounded-full bg-indigo-500"></div>
                      <div className="text-sm text-gray-500">{processingStatus}</div>
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="h-full flex items-center justify-center text-gray-500">
                Select a chat or start a new one
              </div>
            )}
          </div>
        </div>

        {/* Input */}
        <div className="border-t bg-white">
          <div className="max-w-4xl mx-auto">
            <ChatInput
              onSendMessage={sendMessage}
              disabled={!currentThread || processingStatus !== ''}
            />
          </div>
        </div>
      </div>

      {/* File upload sidebar */}
      <div className="w-80 border-l bg-gray-50">
        <div className="p-4 border-b">
          <h2 className="text-lg font-medium text-gray-900">Documents</h2>
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
                <Dialog.Panel className="w-full max-w-2xl transform overflow-hidden rounded-2xl bg-white p-6 shadow-xl transition-all">
                  <Dialog.Title
                    as="h3"
                    className="text-lg font-medium leading-6 text-gray-900"
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