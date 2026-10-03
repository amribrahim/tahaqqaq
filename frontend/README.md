# Tahaqqaq web (Next.js)

Static export (App Router, Tailwind v4, shadcn/ui, next-intl without URL routing: the language toggle is persisted in `localStorage`).

```bash
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev    # http://localhost:3000
npm run build                                           # static site in ./out
node scripts/screenshot.mjs shots                       # full-page screenshots of every state (needs Chrome)
```

Design source of truth: `../design/README.md`.
