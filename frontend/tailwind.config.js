/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'bg-base':      'var(--bg-base)',
        'bg-surface':   'var(--bg-surface)',
        'bg-panel':     'var(--bg-panel)',
        'text-primary': 'var(--text-primary)',
        'text-muted':   'var(--text-muted)',
        'text-dim':     'var(--text-dim)',
        'accent-red':   'var(--accent-red)',
        'accent-blue':  'var(--accent-blue)',
        'accent-green': 'var(--accent-green)',
        'accent-amber': 'var(--accent-amber)',
        'accent-purple':'var(--accent-purple)',
        'accent-orange':'var(--accent-orange)',
      },
      borderColor: {
        'border-subtle': 'var(--border-subtle)',
        'border-mid':    'var(--border-mid)',
      },
    },
  },
  plugins: [],
}

