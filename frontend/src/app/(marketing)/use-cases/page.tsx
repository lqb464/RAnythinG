import Link from 'next/link'

const CASES = [
  {
    icon: '🔬',
    title: 'Research & analysis',
    body: 'Read papers and long reports — ask quickly, cite original passages, export overview mind maps.',
    steps: [
      'Upload multiple papers into one workspace',
      'Ask “what is the main method?” with citations',
      'Export summary report via Studio',
    ],
  },
  {
    icon: '📋',
    title: 'Contracts & legal',
    body: 'Upload sensitive contracts, look up clauses while data never leaves your machine.',
    steps: [
      'Run locally — no cloud upload',
      'Search “payment terms” with source numbers',
      'Save analysis notes in the workspace',
    ],
  },
  {
    icon: '⚙️',
    title: 'Technical documentation',
    body: 'Manuals, specs, release notes — chat to find APIs, workflows, changelogs faster than Ctrl+F.',
    steps: [
      'Index README, API docs, migration guide',
      'Select specific sources when asking',
      'Auto-suggested questions from content',
    ],
  },
  {
    icon: '🏢',
    title: 'Internal teams',
    body: 'Self-host with Docker + Postgres. One workspace per project, chat history persisted.',
    steps: ['docker compose up --build', 'PostgreSQL stores workspace, chat, metadata', 'FAISS index on persistent volume'],
  },
]

export default function UseCasesPage() {
  return (
    <>
      <section className="page-hero">
        <p className="eyebrow">Solutions</p>
        <h1>For people working with real documents</h1>
        <p className="page-lead">
          Research, contracts, technical docs — no need to upload files to third-party services.
        </p>
      </section>

      <section className="section section-tight">
        <div className="usecase-grid usecase-grid-lg">
          {CASES.map((c) => (
            <article key={c.title} className="usecase-card usecase-card-lg">
              <span className="uc-icon">{c.icon}</span>
              <h3>{c.title}</h3>
              <p>{c.body}</p>
              <ul className="uc-steps">
                {c.steps.map((s) => (
                  <li key={s}>{s.includes('docker') ? <code>{s}</code> : s}</li>
                ))}
              </ul>
            </article>
          ))}
        </div>
      </section>

      <section className="section">
        <div className="cta-box">
          <h2>Fit your workflow?</h2>
          <p>Create your first workspace and try uploading documents now.</p>
          <div className="hero-cta">
            <Link href="/app" className="btn-primary btn-lg">
              Get started →
            </Link>
            <Link href="/guide" className="btn-ghost btn-lg">
              Setup guide
            </Link>
          </div>
        </div>
      </section>
    </>
  )
}
