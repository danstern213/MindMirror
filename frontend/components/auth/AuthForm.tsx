import { useState } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { motion } from 'framer-motion';

export function AuthForm() {
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const { login, signup } = useAuth();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    
    console.log('Form submission started:', {
      mode: isLogin ? 'login' : 'signup',
      email,
      passwordLength: password.length
    });

    try {
      if (isLogin) {
        console.log('Attempting login...');
        await login(email, password);
        console.log('Login attempt completed');
      } else {
        console.log('Attempting signup...');
        await signup(email, password);
        console.log('Signup attempt completed');
      }
    } catch (err: any) {
      console.error('Auth form submission error:', {
        message: err.message,
        status: err.status,
        name: err.name,
        supabaseError: err.error,
        supabaseErrorDescription: err.error_description
      });
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
        className="hidden lg:flex lg:w-2/5 bg-gradient-to-br from-indigo-600 via-purple-600 to-indigo-800 relative overflow-hidden"
      >
        <div className="absolute inset-0 bg-[url('/neural-pattern.svg')] opacity-10" />
        <div className="relative z-10 flex flex-col justify-between w-full p-12">
          <div className="font-display">
            <motion.h1 
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3 }}
              className="text-4xl font-bold text-white"
            >
              AI Note Copilot
            </motion.h1>
            <motion.p 
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.4 }}
              className="mt-4 text-xl text-white/80"
            >
              Cultivate the knowledge that you already have.  Find it when you need it.
            </motion.p>
          </div>
          
          <motion.div 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.5 }}
            className="mt-auto"
          >
            <div className="flex space-x-4">
              <div className="h-1 w-12 rounded-full bg-white/30" />
              <div className="h-1 w-12 rounded-full bg-white" />
              <div className="h-1 w-12 rounded-full bg-white/30" />
            </div>
          </motion.div>
        </div>
      </motion.div>

      {/* Right Panel - Auth Forms */}
      <div className="flex-1 flex flex-col justify-center px-4 sm:px-6 lg:px-20 bg-white">
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="max-w-md w-full mx-auto"
        >
          <div className="text-center mb-8">
            <h2 className="font-display text-3xl font-bold text-gray-900">
              {isLogin ? 'Welcome back' : 'Create your account'}
            </h2>
            <p className="mt-3 text-gray-600">
              {isLogin
                ? 'Sign in to continue to your workspace'
                : 'Start organizing your thoughts with BigBrain'}
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-gray-700">
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
                  className="form-input block w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all duration-200 ease-in-out"
                  placeholder="you@example.com"
                />
              </motion.div>
            </div>

            <div>
              <label htmlFor="password" className="block text-sm font-medium text-gray-700">
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
                  className="form-input block w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all duration-200 ease-in-out"
                  placeholder="••••••••"
                />
              </motion.div>
            </div>

            {error && (
              <motion.div
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                className="p-4 rounded-lg bg-red-50 border border-red-100"
              >
                <p className="text-sm text-red-600">{error}</p>
              </motion.div>
            )}

            <motion.button
              whileHover={{ scale: 1.01 }}
              whileTap={{ scale: 0.99 }}
              type="submit"
              className="w-full flex justify-center py-3 px-4 border border-transparent rounded-lg shadow-sm text-sm font-medium text-white bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-700 hover:to-purple-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 transition-all duration-200 ease-in-out"
            >
              {isLogin ? 'Sign in' : 'Create account'}
            </motion.button>

            <div className="text-center">
              <button
                type="button"
                onClick={() => setIsLogin(!isLogin)}
                className="text-sm text-indigo-600 hover:text-indigo-500 font-medium focus:outline-none focus:underline transition-colors duration-200"
              >
                {isLogin ? "Don't have an account? Sign up" : 'Already have an account? Sign in'}
              </button>
            </div>
          </form>

          <div className="mt-8">
            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-gray-200" />
              </div>
              <div className="relative flex justify-center text-sm">
                <span className="px-2 bg-white text-gray-500">
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