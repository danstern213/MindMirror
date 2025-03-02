import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'AI Note Copilot',
  description: 'Talk to your notes, creating new connections with AI. It\'s like having your personal sanctuary of knowledge.',
  icons: {
    icon: '/favicon.svg',
  },
  openGraph: {
    title: 'AI Note Copilot',
    description: 'Talk to your notes, creating new connections with AI. It\'s like having your personal sanctuary of knowledge.',
    type: 'website',
    images: [{ url: '/images/vintage-study.jpg', width: 1792, height: 1024, alt: 'AI Note Copilot' }],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'AI Note Copilot',
    description: 'Talk to your notes, creating new connections with AI. It\'s like having your personal sanctuary of knowledge.',
    images: [{ url: '/images/vintage-study.jpg', width: 1792, height: 1024, alt: 'AI Note Copilot' }],
  }
} 