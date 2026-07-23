const ENTRIES = [
  {
    version: 'v1.3.0',
    date: '2026-07-23',
    tag: 'New',
    title: 'Next.js frontend + separate servers',
    items: [
      'UI migrated to Next.js App Router in frontend/',
      'FastAPI is API-only; Next.js runs on :3000 and proxies /api',
      'Docker Compose: web + api + db services',
    ],
  },
  {
    version: 'v1.2.1',
    date: '2026-07-21',
    tag: 'New',
    title: 'Graph mode (GraphRAG UI)',
    items: [
      'Toggle Assembly / Graph on workspace; entity graph React Flow + communities',
      'Build Graph on-demand; click entity → Ask',
      'API /graph, /graph/build, /graph/ask — auto-index GraphRAG still off by default',
    ],
  },
  {
    version: 'v1.2.0',
    date: '2026-07-21',
    tag: 'New',
    title: 'Assembly Canvas + focused landing',
    items: [
      'Workspace React Flow: drag sources, connect context to Chat, attach Studio artifacts to board',
      'Scored quiz · flip flashcards · mind map expand',
      'Product-focused landing; streamlined marketing nav',
    ],
  },
  {
    version: 'v1.1.0',
    date: '2026-07-21',
    tag: 'New',
    title: 'Multi-user, flexible LLM, export, token-protected service API',
    items: [
      'JWT register/login; notebooks scoped by owner_id',
      'Lock /api/external/* with EXTERNAL_API_TOKEN',
      'Gemini multi-key + OpenAI-compatible / Ollama / vLLM (Settings UI)',
      'Export / import notebook ZIP; Studio persist on Postgres',
    ],
  },
  {
    version: 'v0.3.0',
    date: '2026-07-08',
    tag: 'New',
    title: 'Real Studio, chat streaming, incremental index',
    items: [
      'Studio tools generate content with LLM on main UI',
      'Chat streaming (SSE) and remembers recent conversation turns',
      'Add/remove documents with incremental indexing',
    ],
  },
  {
    version: 'v0.2.0',
    date: '2026-07-05',
    title: 'Multi-page product website',
    items: ['Home, Features, Solutions, Docs, Pricing, Compare, Changelog, About', 'App moved to /app'],
  },
  {
    version: 'v0.1.0',
    date: '2026-07-03',
    title: 'First release',
    items: [
      'Local RAG app',
      'Upload PDF/DOCX/PPTX/MD, FAISS index, chat with citations',
      'Docker + PostgreSQL (pgvector)',
      'CLI build & query',
    ],
  },
]

export default function ChangelogPage() {
  return (
    <>
      <section className="page-hero">
        <p className="eyebrow">Changelog</p>
        <h1>Release history</h1>
        <p className="page-lead">Track the latest changes to RAnythinG.</p>
      </section>

      <section className="section section-tight">
        <div className="changelog">
          {ENTRIES.map((e) => (
            <article key={e.version} className="changelog-entry">
              <div className="changelog-meta">
                <span className="changelog-version">{e.version}</span>
                <time className="changelog-date">{e.date}</time>
                {e.tag ? <span className="changelog-tag tag-new">{e.tag}</span> : null}
              </div>
              <h3>{e.title}</h3>
              <ul>
                {e.items.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </article>
          ))}
        </div>
      </section>
    </>
  )
}
