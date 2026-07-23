import Link from 'next/link'

export default function PricingPage() {
  return (
    <>
      <section className="page-hero">
        <p className="eyebrow">Pricing</p>
        <h1>Simple and transparent</h1>
        <p className="page-lead">Runs on your machine — no subscription, no cloud lock-in.</p>
      </section>

      <section className="section section-tight">
        <div className="pricing-grid">
          <article className="pricing-card">
            <p className="pricing-tier">Local</p>
            <p className="pricing-price">Free</p>
            <p className="pricing-desc">Run on your personal machine, 100% local data.</p>
            <ul className="pricing-features">
              <li>✓ Unlimited workspaces</li>
              <li>✓ Upload PDF, DOCX, MD…</li>
              <li>✓ Chat + citations</li>
              <li>✓ Filesystem storage</li>
              <li>✓ No API key required</li>
            </ul>
            <Link href="/app" className="btn-primary full-width">
              Get started
            </Link>
          </article>

          <article className="pricing-card pricing-card-featured">
            <p className="pricing-badge">Recommended</p>
            <p className="pricing-tier">Self-host</p>
            <p className="pricing-price">Free</p>
            <p className="pricing-desc">Docker + PostgreSQL for teams or internal deployment.</p>
            <ul className="pricing-features">
              <li>✓ All Local features</li>
              <li>✓ PostgreSQL + pgvector</li>
              <li>✓ Persistent volumes</li>
              <li>✓ Chat history in DB</li>
              <li>✓ Ready to scale</li>
            </ul>
            <Link href="/guide#docker" className="btn-primary full-width">
              Docker setup guide
            </Link>
          </article>

          <article className="pricing-card">
            <p className="pricing-tier">Cloud (coming soon)</p>
            <p className="pricing-price">—</p>
            <p className="pricing-desc">Hosted version for teams that need fast deploy without managing servers.</p>
            <ul className="pricing-features">
              <li>○ Managed hosting</li>
              <li>○ Team workspaces</li>
              <li>○ SSO / access control</li>
              <li>○ Auto backup</li>
              <li>○ Priority support</li>
            </ul>
            <a
              href="https://github.com/lqb464/RAnythinG"
              className="btn-ghost full-width"
              target="_blank"
              rel="noopener noreferrer"
            >
              Follow on GitHub
            </a>
          </article>
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Frequently asked questions</h2>
        </div>
        <div className="faq-list">
          <details className="faq-item">
            <summary>Do I need to pay for OpenAI/Google API?</summary>
            <p>
              Not required. RAnythinG uses local models (E5 embedding + Qwen Instruct). You can swap models later if you
              want.
            </p>
          </details>
          <details className="faq-item">
            <summary>Does data go to the cloud?</summary>
            <p>No, when running locally or self-hosted. Files and index stay on your machine/volume.</p>
          </details>
          <details className="faq-item">
            <summary>Limits on workspaces / files?</summary>
            <p>No hard limits — depends on disk space and RAM when indexing.</p>
          </details>
        </div>
      </section>
    </>
  )
}
