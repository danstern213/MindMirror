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
  
  const parts = text.split(/(\[\[.*?\]\]|\[.*?\]\(.*?\))/g);
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
    if (React.isValidElement(child) && child.props) {
      const props = { ...child.props };
      if (props.children) {
        props.children = processChildren(props.children);
      }
      return React.cloneElement(child, props);
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
                  p: ({ children, ...props }) => (
                    <MarkdownElement tag="p" className="my-3 text-gray-700" {...props}>
                      {children}
                    </MarkdownElement>
                  ),
                  h1: ({ children, ...props }) => (
                    <MarkdownElement tag="h1" className="text-3xl font-bold mt-8 mb-4 text-gray-900" {...props}>
                      {children}
                    </MarkdownElement>
                  ),
                  h2: ({ children, ...props }) => (
                    <MarkdownElement tag="h2" className="text-2xl font-bold mt-6 mb-3 text-gray-900" {...props}>
                      {children}
                    </MarkdownElement>
                  ),
                  h3: ({ children, ...props }) => (
                    <MarkdownElement tag="h3" className="text-xl font-bold mt-5 mb-2 text-gray-900" {...props}>
                      {children}
                    </MarkdownElement>
                  ),
                  ul: ({ children }) => (
                    <ul className="list-disc list-outside pl-5 my-4 space-y-2 text-gray-700">
                      {children}
                    </ul>
                  ),
                  ol: ({ children }) => (
                    <ol className="list-decimal list-outside pl-5 my-4 space-y-2 text-gray-700">
                      {children}
                    </ol>
                  ),
                  li: ({ children, ...props }) => (
                    <MarkdownElement tag="li" className="pl-2 my-1" {...props}>
                      {children}
                    </MarkdownElement>
                  ),
                  a: ({ href, children }) => (
                    <a href={href} className="text-indigo-600 hover:text-indigo-700 font-medium">
                      {children}
                    </a>
                  ),
                  strong: ({ children }) => (
                    <strong className="font-bold text-gray-900">
                      {children}
                    </strong>
                  ),
                  em: ({ children }) => (
                    <em className="italic">
                      {children}
                    </em>
                  ),
                  blockquote: ({ children }) => (
                    <blockquote className="border-l-4 border-indigo-200 pl-4 my-4 italic text-gray-700">
                      {children}
                    </blockquote>
                  ),
                  code: ({ className, children }) => {
                    const isInline = !className;
                    return isInline ? (
                      <code className="bg-gray-100 rounded px-1.5 py-0.5 font-mono text-sm text-gray-800">
                        {children}
                      </code>
                    ) : (
                      <code className="block bg-gray-100 rounded p-3 my-3 whitespace-pre-wrap font-mono text-sm text-gray-800 overflow-x-auto">
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