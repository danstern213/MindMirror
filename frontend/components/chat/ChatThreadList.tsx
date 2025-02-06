import { ChatThread } from '@/types';
import { PlusIcon, TrashIcon } from '@heroicons/react/24/outline';
import { format } from 'date-fns';

interface ChatThreadListProps {
  threads: ChatThread[];
  currentThreadId?: string;
  onSelectThread: (thread: ChatThread) => void;
  onCreateThread: () => void;
  onDeleteThread: (threadId: string) => void;
}

function getThreadPreview(thread: ChatThread): { title: string; preview: string } {
  // Get the first user message as title
  const firstUserMessage = thread.messages.find(m => m.role === 'user');
  const lastMessage = thread.messages[thread.messages.length - 1];
  
  const title = firstUserMessage 
    ? firstUserMessage.content.slice(0, 50) + (firstUserMessage.content.length > 50 ? '...' : '')
    : thread.title;
    
  const preview = lastMessage
    ? `${lastMessage.role === 'user' ? 'You: ' : 'AI: '}${lastMessage.content.slice(0, 60)}${lastMessage.content.length > 60 ? '...' : ''}`
    : 'No messages yet';

  return { title, preview };
}

export function ChatThreadList({
  threads,
  currentThreadId,
  onSelectThread,
  onCreateThread,
  onDeleteThread,
}: ChatThreadListProps) {
  return (
    <div className="bg-gray-50 w-64 flex-shrink-0 border-r">
      <div className="p-4">
        <button
          onClick={onCreateThread}
          className="w-full flex items-center justify-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
        >
          <PlusIcon className="h-5 w-5 mr-2" />
          New Chat
        </button>
      </div>
      <nav className="flex-1 overflow-y-auto">
        <ul className="space-y-1 p-2">
          {threads.map((thread) => {
            const { title, preview } = getThreadPreview(thread);
            return (
              <li key={thread.id}>
                <button
                  onClick={() => onSelectThread(thread)}
                  className={`w-full flex flex-col items-start px-3 py-2 text-sm rounded-md ${
                    currentThreadId === thread.id
                      ? 'bg-indigo-100 text-indigo-900'
                      : 'text-gray-700 hover:bg-gray-100'
                  }`}
                >
                  <div className="flex items-center justify-between w-full">
                    <span className="font-medium truncate max-w-[80%]">
                      {title}
                    </span>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onDeleteThread(thread.id);
                      }}
                      className="ml-2 p-1 rounded-full text-gray-400 hover:text-gray-500 hover:bg-gray-200"
                    >
                      <TrashIcon className="h-4 w-4" />
                    </button>
                  </div>
                  <span className="text-xs text-gray-500 truncate w-full mt-1">
                    {preview}
                  </span>
                  <span className="text-xs text-gray-400 mt-1">
                    {format(new Date(thread.last_updated), 'MMM d, h:mm a')}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </nav>
    </div>
  );
} 