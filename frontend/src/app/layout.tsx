import type { Metadata } from 'next'
import { Outfit } from 'next/font/google'
import './globals.css'

const outfit = Outfit({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700', '800'],
  variable: '--font-outfit',
  display: 'swap',
})

export const metadata: Metadata = {
  title: 'RAnythinG',
  description: 'Local privacy-first RAG document workspace — Assembly Canvas, citations, Docker ready.',
  icons: { icon: '/favicon.svg' },
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={outfit.variable} style={{ fontFamily: 'var(--font-outfit), system-ui, sans-serif' }}>
        {children}
      </body>
    </html>
  )
}
