/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{vue,js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        shiso: {
          50: '#f0f7f2',
          100: '#e4f0e7',
          200: '#c8e0ce',
          300: '#a3c4ab',
          400: '#7fa388',
          500: '#5a7d63',
          600: '#3d5a45',
          700: '#2a3d30',
          800: '#1c2b22',
          850: '#162019',
          900: '#111a16',
          950: '#0a0f0d',
        },
        accent: {
          green: '#4ade80',
          sage: '#86efac',
          moss: '#22c55e',
          amber: '#d4a574',
          red: '#e87070',
        },
      },
      fontFamily: {
        body: ['Manrope', 'sans-serif'],
        display: ['"Noto Serif"', 'serif'],
      },
    },
  },
  plugins: [],
}
