'use client';

import { useAuth } from '@/contexts/AuthContext';
import { AuthForm } from '@/components/auth/AuthForm';
import { ChatInterface } from '@/components/chat/ChatInterface';
import { Logo } from '@/components/common/Logo';
import { motion } from 'framer-motion';
import Link from 'next/link';

export default function Home() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[var(--primary-green)]"></div>
      </div>
    );
  }

  if (user) {
    return <ChatInterface />;
  }

  return (
    <div className="min-h-screen bg-[var(--paper-texture)]">
      {/* Header */}
      <header className="fixed w-full top-0 z-50 border-b border-[var(--primary-dark)] bg-[var(--paper-texture)]">
        <nav className="container mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <Logo size="large" />
            <div className="flex items-center space-x-4">
              <Link 
                href="/auth?mode=login"
                className="px-6 py-2 text-sm font-serif text-[var(--primary-green)] border border-[var(--primary-green)] hover:bg-[var(--primary-green)] hover:text-[var(--paper-texture)] transition-colors duration-200 rounded-sm"
              >
                Sign in
              </Link>
              <Link 
                href="/auth?mode=signup"
                className="px-6 py-2 text-sm font-serif text-[var(--paper-texture)] bg-[var(--primary-green)] hover:bg-[var(--primary-green)]/90 transition-colors duration-200 rounded-sm"
              >
                Sign up
              </Link>
            </div>
          </div>
        </nav>
      </header>

      {/* Hero Section */}
      <section className="pt-48 pb-36 relative overflow-hidden">
        <div 
          className="absolute inset-0 bg-[url('/images/vintage-study.jpg')] bg-cover bg-center bg-no-repeat brightness-[0.6]"
        />
        <div 
          className="absolute inset-0 bg-black/75"
        />
        <div className="container mx-auto px-6 relative">
          <motion.div 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8 }}
            className="max-w-4xl mx-auto text-center"
          >
            <div className="inline-block mb-8">
              <div className="relative flex items-center justify-center gap-4 text-[#FFD700]">
                <span className="h-[1px] w-12 bg-[#FFD700]"></span>
                <span className="text-2xl">✧</span>
                <span className="font-serif tracking-widest text-xl">ILLUMINATE THE KNOWLEDGE YOU ALREADY HAVE</span>
                <span className="text-2xl">✧</span>
                <span className="h-[1px] w-12 bg-[#FFD700]"></span>
              </div>
            </div>
            <div>
              <h1 className="text-6xl font-serif font-bold text-[var(--paper-texture)] mb-6 leading-tight">
                Talk To Your Notes
              </h1>
              <p className="text-2xl font-serif text-[var(--paper-texture)] mb-12 leading-relaxed max-w-3xl mx-auto">
                Discuss your past learnings and thoughts, creating new connections with AI.  It's like having your personal sanctuary of knowledge.
              </p>
              <Link 
                href="/auth?mode=signup"
                className="inline-flex items-center px-8 py-4 text-lg font-serif text-[var(--paper-texture)] bg-[var(--primary-green)] hover:bg-[var(--primary-green)]/90 transition-colors duration-200 rounded-sm shadow-lg hover:shadow-xl transform hover:-translate-y-0.5 transition-all"
              >
                Get Started
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 ml-2" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M10.293 3.293a1 1 0 011.414 0l6 6a1 1 0 010 1.414l-6 6a1 1 0 01-1.414-1.414L14.586 11H3a1 1 0 110-2h11.586l-4.293-4.293a1 1 0 010-1.414z" clipRule="evenodd" />
                </svg>
              </Link>
            </div>
          </motion.div>
        </div>
      </section>

      {/* Promo GIF Section */}
      <section className="py-16 relative bg-[var(--paper-texture)]">
        <div className="container mx-auto px-6">
          <motion.div 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.2 }}
            className="max-w-4xl mx-auto"
          >
            <div className="rounded-lg overflow-hidden shadow-[8px_8px_0px_0px_rgba(0,66,37,0.3)] border-2 border-[var(--primary-dark)]">
              <img 
                src="/images/promo.gif" 
                alt="AI Note Copilot Demo" 
                className="w-full h-auto"
              />
            </div>
          </motion.div>
        </div>
      </section>

      {/* Features Section */}
      <section className="py-24 relative">
        <div className="absolute inset-0 bg-[var(--primary-dark)]" />
        <div className="absolute inset-0 bg-[url('/neural-pattern.svg')] opacity-10" />
        <div className="container mx-auto px-6 relative">
          <motion.div 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.2 }}
            className="grid md:grid-cols-3 gap-12"
          >
            <div className="academia-card bg-[var(--paper-texture)] border-2 border-[var(--primary-dark)] shadow-[8px_8px_0px_0px_rgba(0,66,37,0.3)] p-8 hover:transform hover:translate-y-[-4px] transition-all duration-300">
              <div className="h-20 w-20 mb-8 text-[var(--primary-green)] mx-auto">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 12.75V12A2.25 2.25 0 0 1 4.5 9.75h15A2.25 2.25 0 0 1 21.75 12v.75m-8.69-6.44-2.12-2.12a1.5 1.5 0 0 0-1.061-.44H4.5A2.25 2.25 0 0 0 2.25 6v12a2.25 2.25 0 0 0 2.25 2.25h15A2.25 2.25 0 0 0 21.75 18V9a2.25 2.25 0 0 0-2.25-2.25h-5.379a1.5 1.5 0 0 1-1.06-.44Z" />
                </svg>
              </div>
              <h3 className="text-2xl font-serif font-bold text-[var(--primary-dark)] mb-4 text-center">
                Upload Your Notes
              </h3>
              <p className="font-serif text-[var(--primary-dark)] leading-relaxed text-center text-lg">
                Take all of your documents, whether carefully written or thrown together, and upload once.
              </p>
            </div>

            <div className="academia-card bg-[var(--paper-texture)] border-2 border-[var(--primary-dark)] shadow-[8px_8px_0px_0px_rgba(0,66,37,0.3)] p-8 hover:transform hover:translate-y-[-4px] transition-all duration-300">
              <div className="h-20 w-20 mb-8 text-[var(--primary-green)] mx-auto">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 0 0-2.456 2.456ZM16.894 20.567 16.5 21.75l-.394-1.183a2.25 2.25 0 0 0-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 0 0 1.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 0 0 1.423 1.423l1.183.394-1.183.394a2.25 2.25 0 0 0-1.423 1.423Z" />
                </svg>
              </div>
              <h3 className="text-2xl font-serif font-bold text-[var(--primary-dark)] mb-4 text-center">
                AI-Powered Insights
              </h3>
              <p className="font-serif text-[var(--primary-dark)] leading-relaxed text-center text-lg">
                Let AI help you discover connections and generate new perspectives from your existing knowledge.
              </p>
            </div>

            <div className="academia-card bg-[var(--paper-texture)] border-2 border-[var(--primary-dark)] shadow-[8px_8px_0px_0px_rgba(0,66,37,0.3)] p-8 hover:transform hover:translate-y-[-4px] transition-all duration-300">
              <div className="h-20 w-20 mb-8 text-[var(--primary-green)] mx-auto">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 8.511c.884.284 1.5 1.128 1.5 2.097v4.286c0 1.136-.847 2.1-1.98 2.193-.34.027-.68.052-1.02.072v3.091l-3-3c-1.354 0-2.694-.055-4.02-.163a2.115 2.115 0 0 1-.825-.242m9.345-8.334a2.126 2.126 0 0 0-.476-.095 48.64 48.64 0 0 0-8.048 0c-1.131.094-1.976 1.057-1.976 2.192v4.286c0 .837.46 1.58 1.155 1.951m9.345-8.334V6.637c0-1.621-1.152-3.026-2.76-3.235A48.455 48.455 0 0 0 11.25 3c-2.115 0-4.198.137-6.24.402-1.608.209-2.76 1.614-2.76 3.235v6.226c0 1.621 1.152 3.026 2.76 3.235.577.075 1.157.14 1.74.194V21l4.155-4.155" />
                </svg>
              </div>
              <h3 className="text-2xl font-serif font-bold text-[var(--primary-dark)] mb-4 text-center">
                Natural Conversations
              </h3>
              <p className="font-serif text-[var(--primary-dark)] leading-relaxed text-center text-lg">
                Engage in natural conversations with your notes.  It's like having your own personal philosopher, except the philosopher is you.
              </p>
            </div>
          </motion.div>
        </div>
      </section>

      {/* Final CTA Section */}
      <section className="py-24 relative overflow-hidden">
        <div className="absolute inset-0 bg-[url('/neural-pattern.svg')] opacity-5" />
        <div className="container mx-auto px-6 relative">
          <motion.div 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.4 }}
            className="max-w-3xl mx-auto"
          >
            <div className="academia-card bg-[var(--paper-texture)] border-2 border-[var(--primary-dark)] shadow-[8px_8px_0px_0px_rgba(0,66,37,0.3)] p-12 text-center">
              <h2 className="text-4xl font-serif font-bold text-[var(--primary-dark)] mb-6">
                Your Personal Library of Alexandria
              </h2>
              <p className="text-xl font-serif text-[var(--primary-dark)] mb-8 leading-relaxed">
                Join 1,806 fellow thinkers and writers who use AI Note Copilot to create their own library of knowledge.
              </p>
              <Link 
                href="/auth?mode=signup"
                className="inline-flex items-center px-8 py-4 text-lg font-serif text-[var(--paper-texture)] bg-[var(--primary-green)] hover:bg-[var(--primary-green)]/90 transition-colors duration-200 rounded-sm shadow-lg hover:shadow-xl transform hover:-translate-y-0.5 transition-all"
              >
                Start Your Collection
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 ml-2" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M10.293 3.293a1 1 0 011.414 0l6 6a1 1 0 010 1.414l-6 6a1 1 0 01-1.414-1.414L14.586 11H3a1 1 0 110-2h11.586l-4.293-4.293a1 1 0 010-1.414z" clipRule="evenodd" />
                </svg>
              </Link>
            </div>
          </motion.div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t-2 border-[var(--primary-dark)] py-12 bg-[var(--paper-texture)]">
        <div className="container mx-auto px-6">
          <div className="flex flex-col md:flex-row justify-between items-center">
            <Logo />
            <div className="mt-6 md:mt-0">
              <p className="font-serif text-sm text-[var(--primary-dark)]">
                © {new Date().getFullYear()} AI Note Copilot. All rights reserved.
              </p>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
} 