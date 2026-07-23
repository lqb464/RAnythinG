'use client'

import { useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import '@/styles/marketing.css'

const NAV = [
  { to: '/#product', label: 'Product' },
  { to: '/guide', label: 'Setup' },
]

type FooterLink = { label: string; to?: string; href?: string }

const FOOTER: { title: string; links: FooterLink[] }[] = [
  {
    title: 'Product',
    links: [
      { to: '/app', label: 'Open Workspace' },
      { to: '/#product', label: 'Assembly Canvas' },
      { to: '/guide', label: 'Setup' },
    ],
  },
  {
    title: 'Resources',
    links: [
      { to: '/changelog', label: 'Changelog' },
      { to: '/about', label: 'About' },
      { to: '/features', label: 'Features (details)' },
      { href: 'https://github.com/lqb464/RAnythinG', label: 'GitHub' },
    ],
  },
]

function Brand({ className = 'nav-brand' }: { className?: string }) {
  return (
    <Link href="/" className={className} aria-label="RAnythinG home">
      <span className="brand-r">R</span>
      <span className="brand-any">AnythinG</span>
    </Link>
  )
}

export function SiteLayout({ children }: { children: React.ReactNode }) {
  const [menuOpen, setMenuOpen] = useState(false)
  const pathname = usePathname()
  const closeMenu = () => setMenuOpen(false)

  return (
    <div className="marketing-shell">
      <nav className="site-nav" id="top">
        <Brand />
        <div className="nav-links">
          {NAV.map((item) =>
            item.to.includes('#') ? (
              <a key={item.to} href={item.to}>
                {item.label}
              </a>
            ) : (
              <Link key={item.to} href={item.to} className={pathname === item.to ? 'active' : undefined}>
                {item.label}
              </Link>
            ),
          )}
        </div>
        <div className="nav-actions">
          <a
            href="https://github.com/lqb464/RAnythinG"
            className="btn-ghost nav-gh"
            target="_blank"
            rel="noopener noreferrer"
          >
            GitHub
          </a>
          <Link href="/app" className="btn-primary">
            Get started →
          </Link>
        </div>
        <button
          type="button"
          className="nav-toggle"
          aria-label="Open menu"
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((o) => !o)}
        >
          ☰
        </button>
      </nav>

      <div className={`mobile-menu${menuOpen ? ' open' : ''}`}>
        {NAV.map((item) =>
          item.to.includes('#') ? (
            <a key={item.to} href={item.to} onClick={closeMenu}>
              {item.label}
            </a>
          ) : (
            <Link key={item.to} href={item.to} onClick={closeMenu}>
              {item.label}
            </Link>
          ),
        )}
        <Link href="/about" onClick={closeMenu}>
          About
        </Link>
        <Link href="/changelog" onClick={closeMenu}>
          Changelog
        </Link>
        <Link href="/app" className="btn-primary full" onClick={closeMenu}>
          Get started →
        </Link>
      </div>

      <main>{children}</main>

      <footer className="site-footer">
        <div className="footer-inner">
          <div className="footer-brand">
            <Brand />
            <p>Anything · powered by RAG · runs on your machine</p>
          </div>
          <div className="footer-links">
            {FOOTER.map((section) => (
              <div key={section.title}>
                <strong>{section.title}</strong>
                {section.links.map((link) =>
                  link.href ? (
                    <a key={link.label} href={link.href} target="_blank" rel="noopener noreferrer">
                      {link.label}
                    </a>
                  ) : link.to?.includes('#') ? (
                    <a key={link.label} href={link.to}>
                      {link.label}
                    </a>
                  ) : (
                    <Link key={link.label} href={link.to || '/'}>
                      {link.label}
                    </Link>
                  ),
                )}
              </div>
            ))}
          </div>
        </div>
        <p className="footer-copy">© 2026 RAnythinG · Local RAG · Privacy-first</p>
      </footer>
    </div>
  )
}
