/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['Plus Jakarta Sans', 'Tajawal', 'sans-serif'],
        display: ['Outfit', 'Tajawal', 'sans-serif'],
      },
      colors: {
        primary: {
          DEFAULT: '#1F5E47',
          light: '#2A7A5D',
          dark: '#144231',
        },
        danger: '#EF4444',
        surface: {
          dark: '#0B0F13',
          light: '#131A20',
        },
        'on-surface': '#E2E8F0',
      },
    },
  },
};
