import { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import { User } from '@supabase/supabase-js';
import { auth } from '@/lib/supabase';

interface AuthContextType {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    console.log('AuthProvider: Initializing and checking session');
    
    // Check for existing session
    auth.getSession().then(session => {
      console.log('AuthProvider: Session check result:', {
        hasSession: !!session,
        userId: session?.user?.id,
        email: session?.user?.email
      });
      setUser(session?.user ?? null);
      setLoading(false);
    });

    // Subscribe to auth changes
    const { data: { subscription } } = auth.onAuthStateChange((event, session) => {
      console.log('AuthProvider: Auth state changed:', {
        event,
        userId: session?.user?.id,
        email: session?.user?.email
      });
      setUser(session?.user ?? null);
    });

    return () => {
      console.log('AuthProvider: Cleaning up subscription');
      subscription.unsubscribe();
    };
  }, []);

  const login = async (email: string, password: string) => {
    console.log('AuthProvider: Starting login process');
    const { user } = await auth.login(email, password);
    console.log('AuthProvider: Login completed:', {
      userId: user?.id,
      email: user?.email
    });
    setUser(user);
  };

  const signup = async (email: string, password: string) => {
    console.log('AuthProvider: Starting signup process');
    const { user } = await auth.signup(email, password);
    console.log('AuthProvider: Signup completed:', {
      userId: user?.id,
      email: user?.email
    });
    setUser(user);
  };

  const logout = async () => {
    console.log('AuthProvider: Starting logout process');
    await auth.logout();
    console.log('AuthProvider: Logout completed');
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
} 