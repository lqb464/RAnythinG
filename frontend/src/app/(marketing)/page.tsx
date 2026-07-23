import Link from 'next/link'

export default function HomePage() {
  return (
    <>
      <section className="hero hero-product">
        <div className="hero-bg" aria-hidden="true">
          <span className="orb orb-a" />
          <span className="orb orb-b" />
          <span className="hero-grid" />
        </div>
        <div className="hero-inner">
          <p className="eyebrow">RAnythinG · Local · Privacy-first</p>
          <h1>
            Document workspace
            <br />
            <span className="gradient-text">drag · assemble · ask with sources</span>
          </h1>
          <p className="hero-lead">
            Upload PDF/DOCX, drag sources onto the canvas, chat with citations, assemble quiz · mind map · report into
            learning packs — runs on your machine, no cloud lock-in.
          </p>
          <div className="hero-cta">
            <Link href="/app" className="btn-primary btn-lg">
              Open Workspace →
            </Link>
            <Link href="/#product" className="btn-ghost btn-lg">
              See Assembly Canvas
            </Link>
          </div>
          <div className="trust-row">
            <span className="trust-pill">Drag-and-drop canvas</span>
            <span className="trust-pill">Source citations</span>
            <span className="trust-pill">Docker · JWT</span>
            <span className="trust-pill">Gemini / Ollama</span>
          </div>
        </div>
      </section>

      <section className="section" id="product">
        <div className="section-head">
          <p className="eyebrow">Product</p>
          <h2>Assembly Canvas — not a brochure page</h2>
          <p className="section-lead">
            One board: document sources · RAG chat · Studio artifacts. Drag sources into Context to lock the answer scope.
          </p>
        </div>
        <div className="product-showcase">
          <div className="showcase-frame">
            <div className="showcase-chrome">
              <span />
              <span />
              <span />
              <em>RAnythinG · /app</em>
            </div>
            <div className="showcase-body">
              <div className="sc-col sc-lib">
                <strong>Sources</strong>
                <div className="sc-card">policy.pdf</div>
                <div className="sc-card">spec.docx</div>
                <div className="sc-card muted">+ drag and drop</div>
              </div>
              <div className="sc-col sc-canvas">
                <div className="sc-node n-src">policy.pdf</div>
                <div className="sc-node n-chat">Chat · grounded</div>
                <div className="sc-node n-art">Mind map</div>
                <div className="sc-wire" aria-hidden="true" />
              </div>
              <div className="sc-col sc-studio">
                <strong>Studio</strong>
                <div className="sc-chip">Quiz</div>
                <div className="sc-chip">Flashcards</div>
                <div className="sc-chip">Report</div>
              </div>
            </div>
          </div>
          <ul className="product-bullets">
            <li>
              <strong>Drag source → Context</strong> — AI answers only from documents you select
            </li>
            <li>
              <strong>Interactive artifacts</strong> — scored quiz, flip flashcards, expandable mind map
            </li>
            <li>
              <strong>Export ZIP</strong> — backup notebook + re-import
            </li>
            <li>
              <strong>Local-first</strong> — Postgres/FAISS on your machine; JWT multi-user
            </li>
          </ul>
        </div>
        <div className="hero-cta center">
          <Link href="/app" className="btn-primary btn-lg">
            Start in Workspace
          </Link>
        </div>
      </section>

      <section className="section section-tight">
        <div className="section-head">
          <p className="eyebrow">Quick start</p>
          <h2>Run one command</h2>
        </div>
        <pre className="code-block">
          <code>{`docker compose up --build
# → http://localhost:3000/app`}</code>
        </pre>
        <p className="muted-center">
          Setup details: <Link href="/guide">/guide</Link> · Changelog: <Link href="/changelog">/changelog</Link>
        </p>
      </section>
    </>
  )
}
