'use client';

import { Inter } from 'next/font/google';
import localFont from 'next/font/local';
import './globals.css';
import { AuthProvider } from '@/contexts/AuthContext';

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
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
} 