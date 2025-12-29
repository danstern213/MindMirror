import { Message } from '@/types';
import ReactMarkdown from 'react-markdown';
import { Disclosure } from '@headlessui/react';
import { ChevronUpIcon } from '@heroicons/react/24/outline';
import { DocumentArrowDownIcon } from '@heroicons/react/24/outline';
import React, { ReactNode, useState } from 'react';
import { useFileStore } from '@/stores/fileStore';
import toast from 'react-hot-toast';

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
      const props = child.props as Record<string, any>;
      return React.cloneElement(child, {
        ...props,
        children: processChildren(props.children)
      } as any);
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
  const [isSaving, setIsSaving] = useState(false);
  const { uploadFile, fetchTotalFiles } = useFileStore();

  // Function to save the message as a document
  const saveAsDocument = async () => {
    if (!message.content || isStreaming) return;
    
    setIsSaving(true);
    // Show loading toast
    const loadingToast = toast.loading('Saving response to your documents...');
    
    try {
      // Create a title from the first few words of the response
      const titleText = message.content
        .split(/\s+/)
        .slice(0, 5)
        .join(' ')
        .replace(/[^\w\s]/g, '')
        .trim();
      
      // Create a date string for the filename (YYYY-MM-DD format)
      const today = new Date();
      const dateString = today.toISOString().split('T')[0]; // Gets YYYY-MM-DD
      
      // Sanitize the filename to ensure it's valid
      const sanitizedTitle = titleText.length > 0 
        ? titleText.replace(/[^a-zA-Z0-9_\-\s]/g, '').replace(/\s+/g, '_')
        : 'AI_Response';
      
      const filename = `${sanitizedTitle}_${dateString}.md`;
      
      // Create the markdown content with a title
      let markdownContent = `# ${titleText.length > 0 ? titleText : 'AI Response'}\n\n${message.content}`;
      
      // Add sources if available
      if (message.sources && message.sources.length > 0) {
        markdownContent += '\n\n## Sources\n\n';
        message.sources.forEach((source, index) => {
          markdownContent += `${index + 1}. **${source.title}** (Relevance: ${(source.score * 100).toFixed(1)}%)\n`;
          if (source.matched_keywords && source.matched_keywords.length > 0) {
            markdownContent += `   - Matched terms: ${source.matched_keywords.join(', ')}\n`;
          }
          markdownContent += '\n';
        });
      }
      
      // Create a file object
      const file = new File([markdownContent], filename, { type: 'text/markdown' });
      
      // Upload the file
      await uploadFile(file);
      
      // Refresh the file count
      await fetchTotalFiles();
      
      // Update the loading toast to success
      toast.success('Response saved to your documents', { id: loadingToast });
    } catch (error) {
      console.error('Error saving response:', error);
      // Update the loading toast to error
      toast.error('Failed to save response', { id: loadingToast });
    } finally {
      setIsSaving(false);
    }
  };

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
            {isAssistant && !isStreaming && (
              <div className="mt-4 flex items-center justify-between">
                {hasSources ? (
                  <Disclosure as="div" className="flex-1">
                    {({ open }) => (
                      <>
                        <div className="flex items-center justify-between">
                          <Disclosure.Button className="flex items-center text-sm academia-text hover:text-[var(--primary-accent)]">
                            <ChevronUpIcon
                              className={`${open ? 'transform rotate-180' : ''} w-4 h-4 mr-1`}
                            />
                            View Sources ({message.sources!.length})
                          </Disclosure.Button>
                          <button
                            onClick={saveAsDocument}
                            disabled={isSaving}
                            className="inline-flex items-center px-4 py-2 border border-[var(--primary-green)] rounded-sm shadow-sm text-sm font-serif text-[var(--paper-texture)] bg-[var(--primary-green)] hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[var(--primary-green)]"
                            title="Save this response to your document repository"
                          >
                            <DocumentArrowDownIcon className="h-4 w-4 mr-1.5" />
                            {isSaving ? 'Saving...' : 'Save to my Notes'}
                          </button>
                        </div>
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
                ) : (
                  <div className="flex-1"></div> 
                )}
                {!hasSources && (
                  <button
                    onClick={saveAsDocument}
                    disabled={isSaving}
                    className="inline-flex items-center px-4 py-2 border border-[var(--primary-green)] rounded-sm shadow-sm text-sm font-serif text-[var(--paper-texture)] bg-[var(--primary-green)] hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[var(--primary-green)]"
                    title="Save this response to your document repository"
                  >
                    <DocumentArrowDownIcon className="h-4 w-4 mr-1.5" />
                    {isSaving ? 'Saving...' : 'Save to my Notes'}
                  </button>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}