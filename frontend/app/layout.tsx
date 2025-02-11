'use client';

import { Inter } from 'next/font/google';
import localFont from 'next/font/local';
import './globals.css';
import { AuthProvider } from '@/contexts/AuthContext';
import { Toaster } from 'react-hot-toast';

const inter = Inter({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-inter',
});

const clashDisplay = localFont({
  src: '../public/fonts/ClashDisplay-Variable.ttf',
  variable: '--font-clash-display',
  display: 'swap',
});

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${inter.variable} ${clashDisplay.variable} h-full antialiased`}>
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>BigBrain - Your Second Brain</title>
        <meta
          name="description"
          content="BigBrain helps you organize and connect your thoughts, documents, and ideas."
        />
      </head>
      <body className="h-full bg-white">
        <AuthProvider>
          {children}
          <Toaster 
            position="bottom-right" 
            toastOptions={{
              duration: 3000,
              style: {
                background: '#fff',
                color: '#363636',
                boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)',
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
        </AuthProvider>
      </body>
    </html>
  );
} 