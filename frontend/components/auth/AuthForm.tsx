import { useState, useEffect, useRef } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { motion } from 'framer-motion';
import { Logo } from '../common/Logo';
import { supabase } from '@/lib/supabase';

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: any) => void;
          renderButton: (element: HTMLElement, config: any) => void;
          prompt: () => void;
        };
      };
    };
  }
}

export function AuthForm() {
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const { login, signup } = useAuth();
  const googleButtonRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Load the Google Identity Services script
    const script = document.createElement('script');
    script.src = 'https://accounts.google.com/gsi/client';
    script.async = true;
    script.defer = true;
    document.body.appendChild(script);

    script.onload = () => {
      if (window.google && googleButtonRef.current) {
        window.google.accounts.id.initialize({
          client_id: process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID!,
          callback: handleGoogleSignIn,
          auto_select: false,
          cancel_on_tap_outside: true,
        });

        window.google.accounts.id.renderButton(googleButtonRef.current, {
          type: 'standard',
          theme: 'outline',
          size: 'large',
          text: 'continue_with',
          width: googleButtonRef.current.offsetWidth,
          logo_alignment: 'left',
          height: 48,
          shape: 'rectangular',
        });
      }
    };

    return () => {
      const scriptElement = document.querySelector('script[src="https://accounts.google.com/gsi/client"]');
      if (scriptElement && scriptElement.parentNode) {
        scriptElement.parentNode.removeChild(scriptElement);
      }
    };
  }, []);

  const handleGoogleSignIn = async (response: any) => {
    try {
      setError('');
      // The response contains the credential in response.credential
      const { data, error } = await supabase.auth.signInWithIdToken({
        provider: 'google',
        token: response.credential,
      });

      if (error) throw error;

      // The session will be automatically handled by the AuthContext
      console.log('Google sign-in successful:', data);
    } catch (err: any) {
      console.error('Google sign-in error:', err);
      setError(err.message || 'An error occurred during Google sign-in');
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    
    try {
      if (isLogin) {
        await login(email, password);
      } else {
        await signup(email, password);
      }
    } catch (err: any) {
      setError(err.message || 'An error occurred during authentication');
    }
  };

  return (
    <div className="min-h-screen flex">
      {/* Left Panel - Brand Presence */}
      <motion.div 
        initial={{ opacity: 0, x: -20 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.6 }}
        className="hidden lg:flex lg:w-2/5 relative overflow-hidden"
      >
        <div className="absolute inset-0 bg-[var(--primary-green)]" />
        <div className="absolute inset-0 bg-[url('/neural-pattern.svg')] opacity-10" />
        <div 
          className="absolute inset-0" 
          style={{
            backgroundImage: `linear-gradient(to right, rgba(222, 214, 200, 0.1) 1px, transparent 1px),
              linear-gradient(to bottom, rgba(222, 214, 200, 0.1) 1px, transparent 1px)`,
            backgroundSize: '20px 20px'
          }}
        />
        <div className="relative z-10 flex flex-col justify-between w-full p-12">
          <div className="font-serif">
            <motion.div 
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3 }}
            >
              <Logo variant="light" className="mb-8" />
            </motion.div>
            <motion.p 
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.4 }}
              className="mt-4 text-xl text-white font-serif"
            >
              Cultivate the knowledge that you already have. Find it when you need it.
            </motion.p>
          </div>
          
          <motion.div 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.5 }}
            className="mt-auto"
          >
            <div className="flex space-x-4">
              <div className="h-1 w-12 rounded-sm bg-white/30" />
              <div className="h-1 w-12 rounded-sm bg-white" />
              <div className="h-1 w-12 rounded-sm bg-white/30" />
            </div>
          </motion.div>
        </div>
      </motion.div>

      {/* Right Panel - Auth Forms */}
      <div className="flex-1 flex flex-col justify-center px-4 sm:px-6 lg:px-20 bg-[var(--paper-texture)]">
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="max-w-md w-full mx-auto"
        >
          <div className="text-center mb-8">
            <h2 className="font-serif text-3xl font-bold text-[var(--primary-dark)]">
              {isLogin ? 'Welcome back' : 'Create your account'}
            </h2>
            <p className="mt-3 text-[var(--primary-dark)] font-serif">
              {isLogin
                ? 'Sign in to continue to your workspace'
                : 'Start organizing your thoughts with BigBrain'}
            </p>
          </div>

          {/* Google Sign In Button */}
          <div 
            ref={googleButtonRef}
            className="w-full mb-6 px-4 [&>div]:w-full [&>div>div]:w-full [&>div>div>iframe]:!w-full"
          />

          <div className="relative mb-6">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-[var(--primary-dark)]" />
            </div>
            <div className="relative flex justify-center text-sm">
              <span className="px-2 bg-[var(--paper-texture)] text-[var(--primary-dark)] font-serif">
                Or continue with email
              </span>
            </div>
          </div>

          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <label htmlFor="email" className="block text-sm font-serif font-medium text-[var(--primary-dark)]">
                Email address
              </label>
              <motion.div 
                whileTap={{ scale: 0.995 }}
                className="mt-1"
              >
                <input
                  id="email"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="block w-full px-4 py-3 rounded-sm border border-[var(--primary-dark)] bg-[var(--paper-texture)] focus:ring-2 focus:ring-[var(--primary-green)] focus:border-transparent transition-all duration-200 ease-in-out font-serif"
                  placeholder="you@example.com"
                />
              </motion.div>
            </div>

            <div>
              <label htmlFor="password" className="block text-sm font-serif font-medium text-[var(--primary-dark)]">
                Password
              </label>
              <motion.div 
                whileTap={{ scale: 0.995 }}
                className="mt-1"
              >
                <input
                  id="password"
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="block w-full px-4 py-3 rounded-sm border border-[var(--primary-dark)] bg-[var(--paper-texture)] focus:ring-2 focus:ring-[var(--primary-green)] focus:border-transparent transition-all duration-200 ease-in-out font-serif"
                  placeholder="••••••••"
                />
              </motion.div>
            </div>

            {error && (
              <motion.div
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                className="p-4 rounded-sm border border-[var(--primary-dark)] bg-[var(--paper-texture)]"
              >
                <p className="text-sm font-serif text-[var(--primary-dark)]">{error}</p>
              </motion.div>
            )}

            <motion.button
              whileHover={{ scale: 1.01 }}
              whileTap={{ scale: 0.99 }}
              type="submit"
              className="w-full flex justify-center py-3 px-4 border border-[var(--primary-green)] rounded-sm shadow-sm text-sm font-serif text-[var(--paper-texture)] bg-[var(--primary-green)] hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[var(--primary-green)] transition-all duration-200 ease-in-out"
            >
              {isLogin ? 'Sign in' : 'Create account'}
            </motion.button>

            <div className="text-center">
              <button
                type="button"
                onClick={() => setIsLogin(!isLogin)}
                className="text-sm text-[var(--primary-green)] hover:opacity-90 font-serif font-medium focus:outline-none focus:underline transition-colors duration-200"
              >
                {isLogin ? "Don't have an account? Sign up" : 'Already have an account? Sign in'}
              </button>
            </div>
          </form>

          <div className="mt-8">
            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-[var(--primary-dark)]" />
              </div>
              <div className="relative flex justify-center text-sm">
                <span className="px-2 bg-[var(--paper-texture)] text-[var(--primary-dark)] font-serif">
                  Secured by BigBrain
                </span>
              </div>
            </div>
          </div>
        </motion.div>
      </div>
    </div>
  );
} 