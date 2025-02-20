'use client';

import { Inter, Playfair_Display } from 'next/font/google';
import './globals.css';
import { AuthProvider } from '@/contexts/AuthContext';
import { Toaster } from 'react-hot-toast';
import { usePathname } from 'next/navigation';

const inter = Inter({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-inter',
});

const playfair = Playfair_Display({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-playfair',
});

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const isLandingPage = pathname === '/';
  const isAuthPage = pathname === '/auth';

  return (
    <html lang="en" className={`${inter.variable} ${playfair.variable} ${!isLandingPage ? 'h-full' : ''} antialiased`}>
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>AI Note Copilot</title>
        <meta
          name="description"
          content="Your scholarly companion for knowledge exploration"
        />
        <link rel="icon" href="/favicon.svg" type="image/svg+xml" sizes="48x48" />
        <link rel="icon" href="/favicon.ico" sizes="48x48" />
      </head>
      <body className={`academia-container ${!isLandingPage && !isAuthPage ? 'h-screen overflow-hidden' : ''}`}>
        <AuthProvider>
          <div className={`${!isLandingPage && !isAuthPage ? 'h-full' : ''}`}>
            <main className={`relative ${!isLandingPage && !isAuthPage ? 'h-full' : ''}`}>
              {children}
            </main>
            <Toaster 
              position="bottom-right" 
              toastOptions={{
                duration: 3000,
                style: {
                  background: 'var(--paper-texture)',
                  color: 'var(--primary-dark)',
                  boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.2), 0 2px 4px -1px rgba(0, 0, 0, 0.1)',
                  border: '1px solid var(--primary-dark)',
                  fontFamily: 'var(--font-playfair), serif',
                },
              }}
              containerStyle={{
                bottom: 40,
                right: 40,
                maxHeight: '200px',
                position: 'fixed',
                zIndex: 9999,
              }}
              gutter={8}
              containerClassName="overflow-hidden"
            />
          </div>
        </AuthProvider>
      </body>
    </html>
  );
} 