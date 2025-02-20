'use client';

import { useAuth } from '@/contexts/AuthContext';
import { AuthForm } from '@/components/auth/AuthForm';
import { useRouter, useSearchParams } from 'next/navigation';
import { useEffect } from 'react';

export default function AuthPage() {
  const { user } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const mode = searchParams?.get('mode');

  useEffect(() => {
    // If user is logged in, redirect to home
    if (user) {
      router.push('/');
    }
  }, [user, router]);

  // If user is already logged in, show nothing while redirecting
  if (user) {
    return null;
  }

  // Default to login mode if no mode specified
  const isLogin = mode !== 'signup';

  return (
    <div className="min-h-screen">
      <AuthForm initialMode={isLogin} />
    </div>
  );
} 