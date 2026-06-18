import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // PRANA shell palette (from PRANA_Portal_v52.html)
        shell:   '#0F172A',
        canvas:  '#F8FAFC',
        canvas2: '#F1F5F9',
        // Role accent colours
        'role-emp':  '#0EA5E9',   // sky — employee
        'role-oaop': '#10B981',   // emerald — OA-Operator
        'role-oaadm':'#8B5CF6',   // violet — OA-Admin
        'role-pa':   '#F59E0B',   // amber — Portal Admin
        'role-chro': '#EC4899',   // pink — CHRO
        'role-cfo':  '#6366F1',   // indigo — CFO
        'role-ciso': '#EF4444',   // red — CISO
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
    },
  },
  plugins: [],
} satisfies Config
