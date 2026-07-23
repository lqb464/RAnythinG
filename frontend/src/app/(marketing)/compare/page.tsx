import Link from 'next/link'

const ROWS: [string, string, string, string][] = [
  ['Run local / self-host', '✓', '✗', '✗'],
  ['Data never leaves machine', '✓', '✗', '✗'],
  ['Specific source citations', '✓', '✓', 'Partial'],
  ['Studio (quiz, mind map…)', '✓', '✓', '✗'],
  ['No API key required', '✓', '✗', '✗'],
  ['PostgreSQL / scalable', '✓', '✗', '✗'],
  ['Multi-project workspaces', '✓', '✓', 'Partial'],
  ['Cost', 'Free (local)', 'Free (cloud)', 'Paid API'],
]

function cellClass(col: number, val: string) {
  if (col === 1) {
    if (val === '✓') return 'col-highlight yes'
    return 'col-highlight'
  }
  if (val === '✓') return 'yes'
  if (val === '✗') return 'no'
  if (val === 'Partial') return 'partial'
  return undefined
}

export default function ComparePage() {
  return (
    <>
      <section className="page-hero">
        <p className="eyebrow">Compare</p>
        <h1>What makes RAnythinG different?</h1>
        <p className="page-lead">Detailed comparison with popular alternatives.</p>
      </section>

      <section className="section section-tight">
        <div className="compare-wrap">
          <table className="compare-table">
            <thead>
              <tr>
                <th>Criteria</th>
                <th className="col-highlight">RAnythinG</th>
                <th>NotebookLM</th>
                <th>ChatGPT upload</th>
              </tr>
            </thead>
            <tbody>
              {ROWS.map(([crit, a, b, c]) => (
                <tr key={crit}>
                  <td>{crit}</td>
                  <td className={cellClass(1, a)}>{a}</td>
                  <td className={cellClass(2, b)}>{b}</td>
                  <td className={cellClass(3, c)}>{c}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="section">
        <div className="compare-notes">
          <article className="compare-note">
            <h3>When to choose RAnythinG?</h3>
            <p>
              Sensitive documents, need self-host, don&apos;t want to depend on Google/OpenAI, need full control over data
              and models.
            </p>
          </article>
          <article className="compare-note">
            <h3>When to choose NotebookLM?</h3>
            <p>
              You&apos;re OK with Google cloud, need a strong model immediately with no setup, don&apos;t need to deploy a
              server.
            </p>
          </article>
          <article className="compare-note">
            <h3>When to choose ChatGPT upload?</h3>
            <p>
              Quick Q&amp;A on a single file, don&apos;t need strict citations, accept data on OpenAI cloud.
            </p>
          </article>
        </div>
        <div className="hero-cta" style={{ justifyContent: 'center', marginTop: 32 }}>
          <Link href="/app" className="btn-primary btn-lg">
            Try RAnythinG →
          </Link>
        </div>
      </section>
    </>
  )
}
