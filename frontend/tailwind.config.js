/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        studio: {
          bg: '#090b10',
          panel: '#11151f',
          card: '#161b28',
          border: '#242c3d',
          gold: '#d4af37',
          crimson: '#b91c1c',
          accent: '#f59e0b',
        },
      },
    },
  },
  plugins: [],
};
