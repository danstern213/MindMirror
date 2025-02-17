import React from 'react';

interface LogoProps {
  variant?: 'light' | 'dark';
  className?: string;
}

export function Logo({ variant = 'dark', className = '' }: LogoProps) {
  const textColor = variant === 'light' ? 'text-white' : 'text-[var(--primary-dark)]';
  
  return (
    <div className={`flex items-center space-x-2 ${className}`}>
      <svg
        width="32"
        height="32"
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className={`${variant === 'light' ? 'text-white' : 'text-[var(--primary-dark)]'}`}
      >
        {/* Connection lines - square pattern with diagonals */}
        <path
          d="M6 6L18 6M6 6L6 18M18 6L18 18M6 18L18 18M6 6L12 12M18 6L12 12M6 18L12 12M18 18L12 12M9 6L12 9M15 6L12 9M6 9L9 12M6 15L9 12M18 9L15 12M18 15L15 12M9 18L12 15M15 18L12 15"
          stroke="currentColor"
          strokeWidth="0.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {/* Nodes - positioned in a more square pattern */}
        <circle cx="6" cy="6" r="1.2" fill="none" stroke="currentColor" strokeWidth="0.8" />
        <circle cx="18" cy="6" r="1.2" fill="none" stroke="currentColor" strokeWidth="0.8" />
        <circle cx="6" cy="18" r="1.2" fill="none" stroke="currentColor" strokeWidth="0.8" />
        <circle cx="18" cy="18" r="1.2" fill="none" stroke="currentColor" strokeWidth="0.8" />
        <circle cx="12" cy="12" r="1.4" fill="none" stroke="currentColor" strokeWidth="0.8" />
        <circle cx="9" cy="6" r="1.0" fill="none" stroke="currentColor" strokeWidth="0.8" />
        <circle cx="15" cy="6" r="1.0" fill="none" stroke="currentColor" strokeWidth="0.8" />
        <circle cx="6" cy="9" r="1.0" fill="none" stroke="currentColor" strokeWidth="0.8" />
        <circle cx="6" cy="15" r="1.0" fill="none" stroke="currentColor" strokeWidth="0.8" />
        <circle cx="18" cy="9" r="1.0" fill="none" stroke="currentColor" strokeWidth="0.8" />
        <circle cx="18" cy="15" r="1.0" fill="none" stroke="currentColor" strokeWidth="0.8" />
        <circle cx="9" cy="18" r="1.0" fill="none" stroke="currentColor" strokeWidth="0.8" />
        <circle cx="15" cy="18" r="1.0" fill="none" stroke="currentColor" strokeWidth="0.8" />
        <circle cx="12" cy="9" r="1.1" fill="none" stroke="currentColor" strokeWidth="0.8" />
        <circle cx="12" cy="15" r="1.1" fill="none" stroke="currentColor" strokeWidth="0.8" />
        <circle cx="9" cy="12" r="1.1" fill="none" stroke="currentColor" strokeWidth="0.8" />
        <circle cx="15" cy="12" r="1.1" fill="none" stroke="currentColor" strokeWidth="0.8" />
      </svg>
      <span className={`font-serif font-bold text-lg leading-tight ${textColor}`}>
        AI Note Copilot
      </span>
    </div>
  );
} 