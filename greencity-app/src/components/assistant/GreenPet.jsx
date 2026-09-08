import React from 'react';

export function GreenPet({ thinking = false, className = '' }) {
  return <svg className={`green-pet ${thinking ? 'is-thinking' : ''} ${className}`} viewBox="0 0 112 120" fill="none" aria-hidden="true">
    <ellipse cx="56" cy="109" rx="30" ry="5" fill="#064e3b" opacity=".12" />
    <path d="M53 34C35 34 28 20 32 10C48 9 57 20 53 34Z" fill="#86efac" stroke="#047857" strokeWidth="2.5" />
    <path d="M56 35C55 17 70 10 82 14C83 28 72 37 56 35Z" fill="#34d399" stroke="#047857" strokeWidth="2.5" />
    <path d="M55 40L45 23M56 36L71 24" stroke="#047857" strokeWidth="2.5" strokeLinecap="round" />
    <path d="M31 93L27 104C31 109 39 109 42 104L43 96M70 96L71 104C76 109 83 108 85 103L80 92" fill="#047857" />
    <path d="M27 63C15 66 14 79 24 83M86 64C97 66 100 77 89 82" fill="#a7f3d0" stroke="#047857" strokeWidth="2.5" strokeLinecap="round" />
    <path d="M56 34C34 34 23 49 23 72C23 94 36 102 56 102C77 102 89 93 89 72C89 49 79 34 56 34Z" fill="#d1fae5" stroke="#047857" strokeWidth="2.5" />
    <path d="M39 44C32 48 29 55 29 64" stroke="white" strokeWidth="5" strokeLinecap="round" opacity=".9" />
    <ellipse cx="56" cy="78" rx="23" ry="16" fill="#ecfdf5" />
    <g className="green-pet-eyes" fill="#064e3b"><ellipse cx="44" cy="68" rx="3.5" ry="5" /><ellipse cx="69" cy="68" rx="3.5" ry="5" /></g>
    <circle cx="44.8" cy="66.5" r="1" fill="white" /><circle cx="69.8" cy="66.5" r="1" fill="white" />
    <ellipse cx="36" cy="78" rx="5" ry="2.5" fill="#6ee7b7" /><ellipse cx="77" cy="78" rx="5" ry="2.5" fill="#6ee7b7" />
    <path d="M50 80C53 85 60 85 63 80" stroke="#047857" strokeWidth="2.5" strokeLinecap="round" />
  </svg>;
}
