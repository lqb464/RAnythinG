'use client'

import { useState } from 'react'
import Link from 'next/link'

const SECTIONS = [
  { id: 'install', label: 'Install' },
  { id: 'docker', label: 'Docker' },
  { id: 'usage', label: 'Usage flow' },
  { id: 'cli', label: 'CLI' },
  { id: 'architecture', label: 'Architecture' },
]

export default function GuidePage() {
  const [active, setActive] = useState('install')

  return (
    <>
      <section className="page-hero">
        <p className="eyebrow">Docs</p>
        <h1>Setup &amp; usage guide</h1>
        <p className="page-lead">From zero to your first workspace — run locally or with Docker.</p>
      </section>

      <section className="section section-tight">
        <div className="docs-layout">
          <aside className="docs-sidebar">
            <nav>
              {SECTIONS.map((s) => (
                <a
                  key={s.id}
                  href={`#${s.id}`}
                  className={active === s.id ? 'active' : undefined}
                  onClick={() => setActive(s.id)}
                >
                  {s.label}
                </a>
              ))}
            </nav>
          </aside>
          <div className="docs-content prose">
            <h2 id="install">Install (local)</h2>
            <pre className="code-block">
              <code>{`# Terminal 1 — API
python -m venv .venv
.\\.\venv\\Scripts\\Activate.ps1   # Windows
pip install -r backend/requirements.txt
python -m backend                    # http://127.0.0.1:8000

# Terminal 2 — UI
cd frontend
npm install
npm run dev                      # http://localhost:3000`}</code>
            </pre>
            <p>
              Open <strong>http://localhost:3000</strong> (product site) and <strong>http://localhost:3000/app</strong>{' '}
              (Workspace). The Next.js server proxies <code>/api</code> to FastAPI on port 8000.
            </p>

            <h2 id="docker">Docker (recommended)</h2>
            <pre className="code-block">
              <code>docker compose up --build</code>
            </pre>
            <ul>
              <li>Next.js UI + FastAPI API + PostgreSQL (pgvector)</li>
              <li>
                UI: <code>http://localhost:3000</code> · API: <code>http://localhost:8000</code>
              </li>
              <li>
                Postgres: port <code>5432</code>, user/pass/db = <code>ranything</code>
              </li>
              <li>
                FAISS index → volume <code>app_data</code>
              </li>
            </ul>
            <p>
              Check storage: <code>GET http://localhost:8000/api/health</code>
            </p>

            <h2 id="usage">Usage flow</h2>
            <ol className="docs-ol">
              <li>
                Create a new workspace at <Link href="/app">/app</Link>
              </li>
              <li>Upload documents (auto-indexed), drag sources onto the canvas</li>
              <li>Connect context to Chat and ask with citations</li>
              <li>
                Use <strong>Studio</strong> to create quiz, flashcards, reports…
              </li>
            </ol>

            <h2 id="cli">CLI (optional)</h2>
            <pre className="code-block">
              <code>{`python -m backend.cli build --source-folder ./docs --output-dir ./data
python -m backend.cli query --index-path ./data/rag_index.faiss \\
  --metadata-path ./data/rag_index.faiss.json --query "What is the main content?"`}</code>
            </pre>

            <h2 id="architecture">Architecture</h2>
            <table className="docs-table">
              <tbody>
                <tr>
                  <th>Component</th>
                  <th>Description</th>
                </tr>
                <tr>
                  <td>Frontend</td>
                  <td>Next.js (App Router) — <code>frontend/</code> on port 3000</td>
                </tr>
                <tr>
                  <td>Backend</td>
                  <td>FastAPI — <code>backend/</code> API-only on port 8000</td>
                </tr>
                <tr>
                  <td>Embedding</td>
                  <td>intfloat/multilingual-e5-small</td>
                </tr>
                <tr>
                  <td>Reranker</td>
                  <td>BAAI/bge-reranker-v2-m3</td>
                </tr>
                <tr>
                  <td>Vector store</td>
                  <td>FAISS (+ BM25 hybrid)</td>
                </tr>
                <tr>
                  <td>Storage</td>
                  <td>Filesystem or PostgreSQL</td>
                </tr>
              </tbody>
            </table>

            <div className="hero-cta" style={{ marginTop: 32 }}>
              <Link href="/app" className="btn-primary">
                Open app →
              </Link>
              <Link href="/features" className="btn-ghost">
                See features
              </Link>
            </div>
          </div>
        </div>
      </section>
    </>
  )
}
