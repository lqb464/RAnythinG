'use client'

import { useMemo, useState, type ReactNode } from 'react'
import type { FlashItem, QuizItem } from './nodes'

export function QuizWidget({ items }: { items: QuizItem[] }) {
  const [scores, setScores] = useState<Record<number, 'correct' | 'wrong'>>({})
  if (!items.length) return <p className="muted">No questions</p>
  return (
    <div>
      {items.slice(0, 8).map((item, i) => {
        const q = item.question || `Question ${i + 1}`
        const opts = item.options || []
        const correct = item.answer || item.correct || ''
        return (
          <div key={i} className="quiz-item">
            <strong>{q}</strong>
            {opts.map((opt) => (
              <button
                key={opt}
                type="button"
                className={`btn btn-sm${scores[i] ? (opt === correct || opt.includes(String(correct)) ? ' correct' : scores[i] === 'wrong' ? ' wrong' : '') : ''}`}
                onClick={() =>
                  setScores((s) => ({
                    ...s,
                    [i]: opt === correct || opt.includes(String(correct)) ? 'correct' : 'wrong',
                  }))
                }
              >
                {opt}
              </button>
            ))}
            {scores[i] && (
              <div className="cite">{scores[i] === 'correct' ? 'Correct' : `Wrong · answer: ${correct}`}</div>
            )}
          </div>
        )
      })}
    </div>
  )
}

export function FlashcardsWidget({ items }: { items: FlashItem[] }) {
  const cards = useMemo(
    () =>
      items.map((it) => ({
        front: it.front || it.q || '?',
        back: it.back || it.a || '',
      })),
    [items],
  )
  const [idx, setIdx] = useState(0)
  const [flipped, setFlipped] = useState(false)
  if (!cards.length) return <p className="muted">No cards</p>
  const card = cards[idx % cards.length]
  return (
    <div>
      <div className={`flashcard${flipped ? ' flipped' : ''}`} onClick={() => setFlipped((f) => !f)}>
        <div className="flashcard-inner">
          <div className="flash-face">{card.front}</div>
          <div className="flash-face back">{card.back}</div>
        </div>
      </div>
      <div className="flash-nav">
        <button
          type="button"
          className="btn btn-sm"
          onClick={(e) => {
            e.stopPropagation()
            setFlipped(false)
            setIdx((i) => (i - 1 + cards.length) % cards.length)
          }}
        >
          ←
        </button>
        <span className="cite">
          {idx + 1}/{cards.length} · click card to flip
        </span>
        <button
          type="button"
          className="btn btn-sm"
          onClick={(e) => {
            e.stopPropagation()
            setFlipped(false)
            setIdx((i) => (i + 1) % cards.length)
          }}
        >
          →
        </button>
      </div>
    </div>
  )
}

type MindNode = { id?: string; label?: string; name?: string; children?: MindNode[] }

function renderMind(node: MindNode, depth = 0): ReactNode {
  const label = node.label || node.name || node.id || 'node'
  const kids = node.children || []
  return (
    <li key={`${label}-${depth}`}>
      <details open={depth < 2}>
        <summary>{label}</summary>
        {kids.length ? <ul className="mind-tree">{kids.map((c) => renderMind(c, depth + 1))}</ul> : null}
      </details>
    </li>
  )
}

export function MindMapWidget({ data }: { data: Record<string, unknown> }) {
  const root = (data.tree || data.root || data.mindmap || data) as MindNode
  if (!root || typeof root !== 'object') {
    return <pre className="payload-pre">{JSON.stringify(data, null, 2).slice(0, 600)}</pre>
  }
  return <ul className="mind-tree">{renderMind(root)}</ul>
}

export function ReportWidget({ markdown }: { markdown: string }) {
  return <div className="report-body">{markdown || '—'}</div>
}
