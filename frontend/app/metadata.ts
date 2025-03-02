import type { Metadata } from 'next'

// Use environment variable or default to empty string for local development
const BASE_URL = process.env.NEXT_PUBLIC_BASE_URL || ''

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
    images: [{ 
      url: 'https://www.ainotecopilot.com/images/vintage-study.jpg', 
      width: 1792, 
      height: 1024, 
      alt: 'AI Note Copilot' 
    }],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'AI Note Copilot',
    description: 'Talk to your notes, creating new connections with AI. It\'s like having your personal sanctuary of knowledge.',
    images: [{ 
      url: 'https://www.ainotecopilot.com/images/vintage-study.jpg', 
      width: 1792, 
      height: 1024, 
      alt: 'AI Note Copilot' 
    }],
  }
} 