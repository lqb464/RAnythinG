export default function AboutPage() {
  return (
    <>
      <section className="page-hero">
        <p className="eyebrow">About</p>
        <h1>Local RAG for your documents</h1>
        <p className="page-lead">Anything · powered by RAG — runs on your machine, no cloud lock-in.</p>
      </section>

      <section className="section section-tight">
        <div className="about-grid">
          <article className="about-block">
            <h2>Mission</h2>
            <p>
              RAnythinG helps you Q&amp;A and work with your own documents — contracts, reports, technical specs — without
              sending data to third-party services.
            </p>
            <p>
              We believe AI is most useful when grounded in real sources, running where you control it, and transparent
              about how it answers.
            </p>
          </article>
          <article className="about-block">
            <h2>Technology</h2>
            <ul className="about-tech">
              <li>
                <strong>Backend:</strong> FastAPI, SQLAlchemy, FAISS (<code>backend/</code>)
              </li>
              <li>
                <strong>Frontend:</strong> Next.js App Router (<code>frontend/</code>)
              </li>
              <li>
                <strong>ML:</strong> sentence-transformers, transformers, PyTorch
              </li>
              <li>
                <strong>Storage:</strong> Filesystem or PostgreSQL + pgvector
              </li>
              <li>
                <strong>Deploy:</strong> Docker Compose (web + api + db)
              </li>
            </ul>
          </article>
          <article className="about-block">
            <h2>Roadmap</h2>
            <ul className="roadmap-list">
              <li>
                <span className="roadmap-status done">✓</span> Core RAG: upload, chat, citations
              </li>
              <li>
                <span className="roadmap-status done">✓</span> Product website
              </li>
              <li>
                <span className="roadmap-status done">✓</span> Studio API on main UI
              </li>
              <li>
                <span className="roadmap-status done">✓</span> Multi-user &amp; auth (JWT)
              </li>
              <li>
                <span className="roadmap-status done">✓</span> Optional LLM (Gemini / Ollama / vLLM)
              </li>
              <li>
                <span className="roadmap-status done">✓</span> Assembly Canvas
              </li>
              <li>
                <span className="roadmap-status done">✓</span> Graph mode (GraphRAG UI)
              </li>
              <li>
                <span className="roadmap-status done">✓</span> Next.js separate UI server
              </li>
              <li>
                <span className="roadmap-status planned">○</span> pgvector instead of FAISS (optional)
              </li>
            </ul>
          </article>
          <article className="about-block">
            <h2>Source code</h2>
            <p>RAnythinG is open source. Contribute, report issues, and follow development on GitHub.</p>
            <a href="https://github.com/lqb464/RAnythinG" className="btn-primary" target="_blank" rel="noopener noreferrer">
              GitHub →
            </a>
          </article>
        </div>
      </section>
    </>
  )
}
