# RAnythinG frontend (Next.js)

```powershell
npm install
npm run dev     # http://localhost:3000 — proxies /api → http://127.0.0.1:8000
npm run build
npm start       # production Node server on :3000
```

Set `API_ORIGIN` if the FastAPI API is not on `http://127.0.0.1:8000` (used by `next.config.ts` rewrites).

## Layout

```text
frontend/
  src/
    app/           # App Router routes
    components/    # React components (marketing/, workspace/)
    lib/           # API client, shared utilities
    styles/        # Global CSS (marketing.css, workspace.css)
  public/          # Static assets
```

Global styles stay in `src/styles/` and are imported from layouts — standard for large legacy CSS sheets. Component-level styling would use CSS Modules co-located with components; not needed here yet.
