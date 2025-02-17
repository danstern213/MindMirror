import { ChatThread } from '@/types';
import { PlusIcon } from '@heroicons/react/24/outline';
import { format } from 'date-fns';

interface ChatThreadListProps {
  threads: ChatThread[];
  currentThreadId?: string;
  onSelectThread: (thread: ChatThread) => void;
  onCreateThread: () => void;
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
}: ChatThreadListProps) {
  return (
    <div className="bg-[var(--paper-texture)] w-64 flex-shrink-0">
      <div className="p-4">
        <button
          onClick={onCreateThread}
          className="w-full flex items-center justify-center px-4 py-2 border border-[var(--primary-green)] rounded-sm shadow-sm text-sm font-serif text-[var(--paper-texture)] bg-[var(--primary-green)] hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[var(--primary-green)]"
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
                  className={`w-full flex flex-col items-start px-3 py-2 text-sm rounded-sm border ${
                    currentThreadId === thread.id
                      ? 'bg-[var(--paper-texture)] text-[var(--primary-dark)] border-[var(--primary-green)]'
                      : 'text-[var(--primary-dark)] hover:bg-[var(--paper-texture)] hover:border-[var(--primary-green)] border-transparent'
                  }`}
                >
                  <div className="flex items-center justify-between w-full">
                    <span className="font-serif truncate">
                      {title}
                    </span>
                  </div>
                  <span className="text-xs academia-text truncate w-full mt-1">
                    {preview}
                  </span>
                  <span className="text-xs text-[var(--primary-green)] mt-1 font-serif">
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