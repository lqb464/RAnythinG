import Link from 'next/link'

const FEATURES = [
  {
    icon: '↑',
    title: 'Multi-format upload',
    body: 'PDF, DOCX, PPTX, HTML, TXT, CSV, Markdown — drag and drop, auto-indexed, no manual steps.',
  },
  {
    icon: '◎',
    title: 'Vector search (FAISS)',
    body: 'Local embeddings with sentence-transformers. Finds the right passages before answering.',
  },
  {
    icon: '💬',
    title: 'Chat + citations',
    body: 'Ask naturally, get answers with source numbers — click to compare the original passage.',
  },
  {
    icon: '📓',
    title: 'Multi-project workspaces',
    body: 'One workspace per topic: contracts, research, internal docs — fully isolated.',
  },
  {
    icon: '🐘',
    title: 'PostgreSQL + pgvector',
    body: 'Run with Docker: metadata, chat history, workspaces stored in Postgres — ready to scale.',
  },
  {
    icon: '🔒',
    title: 'Privacy by design',
    body: 'No API key required. Sensitive documents never leave your machine.',
  },
]

export default function FeaturesPage() {
  return (
    <>
      <section className="page-hero">
        <p className="eyebrow">Features</p>
        <h1>Everything you need to work with documents</h1>
        <p className="page-lead">Not a generic chatbot — every answer is grounded in sources you upload.</p>
      </section>

      <section className="section section-tight">
        <div className="feature-grid">
          {FEATURES.map((f) => (
            <article key={f.title} className="feature-card">
              <div className="feat-icon">{f.icon}</div>
              <h3>{f.title}</h3>
              <p>{f.body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="section section-studio">
        <div className="studio-layout">
          <div className="studio-copy">
            <p className="eyebrow">Studio</p>
            <h2>Turn documents into ready-to-use output</h2>
            <p className="section-sub">
              Convert raw content into working tools — quiz, flashcards, mind map, report, slides, audio overview.
            </p>
            <ul className="studio-list">
              <li>
                <strong>Quiz</strong> — test understanding of document content
              </li>
              <li>
                <strong>Flashcards</strong> — review concepts and domain terminology
              </li>
              <li>
                <strong>Mind Map</strong> — see how ideas connect at a glance
              </li>
              <li>
                <strong>Report</strong> — structured summary report
              </li>
              <li>
                <strong>Slides &amp; Audio</strong> — presentation-style or podcast overview
              </li>
            </ul>
            <p className="note-inline">Studio generates content with an LLM directly on Assembly Canvas.</p>
          </div>
          <div className="studio-visual">
            <div className="studio-cards">
              <div className="scard scard-1">Quiz from chapter 3</div>
              <div className="scard scard-2">Mind map — workflow</div>
              <div className="scard scard-3">Q2 summary report</div>
              <div className="scard scard-4">12 flashcards</div>
            </div>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Assembly Canvas</h2>
          <p className="section-sub">Drag sources · grounded chat · attach Studio artifacts to the board.</p>
        </div>
        <div className="panel-overview">
          <div className="panel-overview-item">
            <span>📁</span>
            <div>
              <strong>Sources</strong>
              <p>Upload, select sources, manage files</p>
            </div>
          </div>
          <div className="panel-overview-item">
            <span>💬</span>
            <div>
              <strong>Chat</strong>
              <p>RAG Q&amp;A, suggested questions, history</p>
            </div>
          </div>
          <div className="panel-overview-item">
            <span>🎨</span>
            <div>
              <strong>Studio</strong>
              <p>Quiz, cards, mind map, notes</p>
            </div>
          </div>
        </div>
        <div className="hero-cta" style={{ justifyContent: 'center', marginTop: 28 }}>
          <Link href="/app" className="btn-primary">
            Open workspace →
          </Link>
        </div>
      </section>
    </>
  )
}
