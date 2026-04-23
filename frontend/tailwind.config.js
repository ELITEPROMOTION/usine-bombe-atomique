/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        display: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      colors: {
        // Deep luxury dark
        ink: {
          950: '#060607',
          900: '#0a0a0c',
          850: '#0e0e11',
          800: '#141418',
          700: '#1c1c22',
          600: '#26262e',
          500: '#33333d',
          400: '#4a4a57',
          300: '#6a6a79',
          200: '#9a9aa8',
          100: '#c7c7cf',
          50:  '#eaeaee',
        },
        // Soft champagne gold accents
        gold: {
          50:  '#fdf8ec',
          100: '#f9edc9',
          200: '#f1d98c',
          300: '#e7c05b',
          400: '#d9a63c',
          500: '#c49129',
          600: '#a87522',
          700: '#82581c',
          800: '#5c3e15',
          900: '#3b2810',
        },
        success: '#3ecf8e',
        warn:    '#f7c948',
        danger:  '#ef5b5b',
      },
      boxShadow: {
        'glow-gold': '0 0 32px -8px rgba(231, 192, 91, 0.35)',
        'panel':     '0 1px 0 rgba(255,255,255,0.04) inset, 0 24px 64px -24px rgba(0,0,0,0.8)',
      },
      backgroundImage: {
        'grid-dots': "radial-gradient(rgba(255,255,255,0.035) 1px, transparent 1px)",
      },
      backgroundSize: {
        'grid-dots': '24px 24px',
      },
      keyframes: {
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        'fade-in': {
          '0%': { opacity: 0, transform: 'translateY(4px)' },
          '100%': { opacity: 1, transform: 'translateY(0)' },
        },
        'pulse-soft': {
          '0%, 100%': { opacity: 0.6 },
          '50%': { opacity: 1 },
        },
      },
      animation: {
        shimmer: 'shimmer 2.8s linear infinite',
        'fade-in': 'fade-in 0.4s ease-out',
        'pulse-soft': 'pulse-soft 2s ease-in-out infinite',
      },
    },
  },
  plugins: [],
};
