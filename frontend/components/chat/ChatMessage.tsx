import { Message } from '@/types';
import ReactMarkdown from 'react-markdown';
import { Disclosure } from '@headlessui/react';
import { ChevronUpIcon } from '@heroicons/react/24/outline';
import React, { ReactNode } from 'react';

interface ChatMessageProps {
  message: Message;
  isStreaming?: boolean;
}

// Process text to handle bracketed content
const processBracketedText = (text: string) => {
  if (typeof text !== 'string') return text;
  
  const parts = text.split(/(\[\[(?:(?!\]\]).)*\]\])/g);
  return parts.map((part, index) => {
    if (part.startsWith('[[') && part.endsWith(']]')) {
      const innerText = part.slice(2, -2);
      return (
        <span key={index} className="font-medium text-indigo-600">
          {innerText}
        </span>
      );
    }
    return part;
  });
};

// Component to wrap markdown elements and process their text content
const MarkdownElement = ({ tag: Tag, className, children }: { tag: any, className?: string, children: ReactNode }) => {
  const processChildren = (child: ReactNode): ReactNode => {
    if (typeof child === 'string') {
      return processBracketedText(child);
    }
    return child;
  };

  return (
    <Tag className={className}>
      {Array.isArray(children) 
        ? children.map((child, index) => <React.Fragment key={index}>{processChildren(child)}</React.Fragment>)
        : processChildren(children)
      }
    </Tag>
  );
};

export function ChatMessage({ message, isStreaming = false }: ChatMessageProps) {
  const isAssistant = message.role === 'assistant';
  const hasSources = !isStreaming && message.sources && message.sources.length > 0;

  return (
    <div className={`py-4 ${isAssistant ? 'bg-gray-50' : 'bg-white'}`}>
      <div className="max-w-4xl mx-auto px-4">
        <div className="flex items-start">
          <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
            isAssistant ? 'bg-indigo-500' : 'bg-gray-300'
          }`}>
            <span className="text-white text-sm font-medium">
              {isAssistant ? 'AI' : 'U'}
            </span>
          </div>
          <div className="ml-4 flex-1">
            <div className="prose prose-indigo max-w-none">
              <ReactMarkdown
                components={{
                  p: ({ children }) => (
                    <MarkdownElement tag="p" className="my-3">
                      {children}
                    </MarkdownElement>
                  ),
                  h1: ({ children }) => (
                    <MarkdownElement tag="h1" className="text-2xl font-bold mt-6 mb-4">
                      {children}
                    </MarkdownElement>
                  ),
                  h2: ({ children }) => (
                    <MarkdownElement tag="h2" className="text-xl font-bold mt-5 mb-3">
                      {children}
                    </MarkdownElement>
                  ),
                  h3: ({ children }) => (
                    <MarkdownElement tag="h3" className="text-lg font-bold mt-4 mb-2">
                      {children}
                    </MarkdownElement>
                  ),
                  li: ({ children }) => (
                    <MarkdownElement tag="li" className="my-1">
                      {children}
                    </MarkdownElement>
                  ),
                  code: ({ className, children }) => {
                    const isInline = !className;
                    return isInline ? (
                      <code className="bg-gray-100 rounded px-1">{children}</code>
                    ) : (
                      <code className="block bg-gray-100 rounded p-2 my-2 whitespace-pre-wrap">
                        {children}
                      </code>
                    );
                  }
                }}
              >
                {message.content}
              </ReactMarkdown>
            </div>
            {hasSources && (
              <Disclosure as="div" className="mt-4">
                {({ open }) => (
                  <>
                    <Disclosure.Button className="flex items-center text-sm text-gray-500 hover:text-gray-700">
                      <ChevronUpIcon
                        className={`${open ? 'transform rotate-180' : ''} w-4 h-4 mr-1`}
                      />
                      View Sources ({message.sources!.length})
                    </Disclosure.Button>
                    <Disclosure.Panel className="mt-2">
                      <div className="space-y-2">
                        {message.sources!.map((source, index) => (
                          <div
                            key={index}
                            className="text-sm bg-white p-3 rounded-lg border border-gray-200"
                          >
                            <div className="font-medium text-gray-900">
                              {source.title}
                            </div>
                            <div className="mt-1 text-gray-500">
                              Relevance: {(source.score * 100).toFixed(1)}%
                            </div>
                            {source.matched_keywords && source.matched_keywords.length > 0 && (
                              <div className="mt-1 text-gray-500">
                                Matched terms: {source.matched_keywords.join(', ')}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </Disclosure.Panel>
                  </>
                )}
              </Disclosure>
            )}
          </div>
        </div>
      </div>
    </div>
  );
} 