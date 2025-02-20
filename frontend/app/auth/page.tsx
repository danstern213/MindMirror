'use client';

import { useAuth } from '@/contexts/AuthContext';
import { AuthForm } from '@/components/auth/AuthForm';
import { useRouter, useSearchParams } from 'next/navigation';
import { useEffect, Suspense } from 'react';

function AuthContent() {
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

export default function AuthPage() {
  return (
    <Suspense fallback={
      <div className="flex h-screen items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[var(--primary-green)]"></div>
      </div>
    }>
      <AuthContent />
    </Suspense>
  );
} 