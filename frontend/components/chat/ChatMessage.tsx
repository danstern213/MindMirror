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
        <span 
          key={index} 
          className="text-[var(--primary-accent)]"
          style={{ fontSize: 'inherit', fontWeight: 'inherit', fontFamily: 'inherit' }}
        >
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
    if (React.isValidElement(child)) {
      return React.cloneElement(child, {
        ...child.props,
        children: processChildren(child.props.children)
      });
    }
    if (Array.isArray(child)) {
      return child.map((c, i) => <React.Fragment key={i}>{processChildren(c)}</React.Fragment>);
    }
    return child;
  };

  return (
    <Tag className={className}>
      {processChildren(children)}
    </Tag>
  );
};

export function ChatMessage({ message, isStreaming = false }: ChatMessageProps) {
  const isAssistant = message.role === 'assistant';
  const hasSources = !isStreaming && message.sources && message.sources.length > 0;

  return (
    <div className={`py-4 ${isAssistant ? 'bg-[var(--paper-texture)] border-y border-[var(--primary-dark)]' : ''}`}>
      <div className="max-w-4xl mx-auto px-4">
        <div className="flex items-start">
          <div className={`flex-shrink-0 w-8 h-8 rounded-sm flex items-center justify-center ${
            isAssistant ? 'bg-[var(--primary-green)]' : 'bg-[var(--primary-accent)]'
          }`}>
            <span className="text-[var(--paper-texture)] text-sm font-serif">
              {isAssistant ? 'AI' : 'U'}
            </span>
          </div>
          <div className="ml-4 flex-1">
            <div className="prose prose-stone max-w-none">
              <ReactMarkdown
                components={{
                  p: ({ children, ...props }) => (
                    <MarkdownElement tag="p" className="my-3 academia-text" {...props}>
                      {children}
                    </MarkdownElement>
                  ),
                  h1: ({ children, ...props }) => (
                    <MarkdownElement tag="h1" className="academia-heading mt-8 mb-4" {...props}>
                      {children}
                    </MarkdownElement>
                  ),
                  h2: ({ children, ...props }) => (
                    <MarkdownElement tag="h2" className="academia-heading mt-6 mb-3" {...props}>
                      {children}
                    </MarkdownElement>
                  ),
                  h3: ({ children, ...props }) => (
                    <MarkdownElement tag="h3" className="academia-heading mt-5 mb-2" {...props}>
                      {children}
                    </MarkdownElement>
                  ),
                  ul: ({ children }) => (
                    <ul className="list-disc list-outside pl-5 my-4 space-y-2 academia-text">
                      {children}
                    </ul>
                  ),
                  ol: ({ children }) => (
                    <ol className="list-decimal list-outside pl-5 my-4 space-y-2 academia-text">
                      {children}
                    </ol>
                  ),
                  li: ({ children, ...props }) => (
                    <MarkdownElement tag="li" className="pl-2 my-1" {...props}>
                      {children}
                    </MarkdownElement>
                  ),
                  a: ({ href, children }) => (
                    <a href={href} className="academia-link">
                      {children}
                    </a>
                  ),
                  strong: ({ children }) => (
                    <strong className="font-bold text-[var(--primary-dark)]">
                      {children}
                    </strong>
                  ),
                  em: ({ children }) => (
                    <em className="italic">
                      {children}
                    </em>
                  ),
                  blockquote: ({ children }) => (
                    <blockquote className="border-l-4 border-[var(--primary-accent)] pl-4 my-4 italic academia-text">
                      {children}
                    </blockquote>
                  ),
                  code: ({ className, children }) => {
                    const isInline = !className;
                    return isInline ? (
                      <code className="bg-[var(--paper-texture)] border border-[var(--primary-dark)] rounded-sm px-1.5 py-0.5 font-mono text-sm text-[var(--primary-dark)]">
                        {children}
                      </code>
                    ) : (
                      <code className="block bg-[var(--paper-texture)] border border-[var(--primary-dark)] rounded-sm p-3 my-3 whitespace-pre-wrap font-mono text-sm text-[var(--primary-dark)] overflow-x-auto">
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
                    <Disclosure.Button className="flex items-center text-sm academia-text hover:text-[var(--primary-accent)]">
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
                            className="text-sm academia-card"
                          >
                            <div className="font-serif font-medium text-[var(--primary-dark)]">
                              {source.title}
                            </div>
                            <div className="mt-1 academia-text">
                              Relevance: {(source.score * 100).toFixed(1)}%
                            </div>
                            {source.matched_keywords && source.matched_keywords.length > 0 && (
                              <div className="mt-1 academia-text">
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