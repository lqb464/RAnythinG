'use client'

import { createContext, memo, useCallback, useContext, useState } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { FlashcardsWidget, MindMapWidget, QuizWidget, ReportWidget } from './widgets'

export type SourceNodeData = { filename: string; inContext?: boolean }
export type ChatNodeData = {
  notebookId: string
  contextSources: string[]
  messages?: { role: 'user' | 'bot'; text: string; cites?: string[] }[]
  busy?: boolean
}
export type ArtifactNodeData = {
  tool: string
  label: string
  payload: Record<string, unknown>
}

/** Keep ask handler out of node.data — functions in RF node data crash connection UX. */
export const AskContext = createContext<(q: string) => Promise<void>>(async () => {})

function SourceNode({ data }: NodeProps) {
  const d = data as SourceNodeData
  return (
    <div className={`rf-node source${d.inContext ? ' active' : ''}`}>
      <Handle type="source" position={Position.Right} id="out" />
      <div className="hd">Source</div>
      <div className="bd">
        {d.filename}
        {d.inContext ? ' · in context' : ''}
      </div>
    </div>
  )
}

function ChatNode({ data }: NodeProps) {
  const d = data as ChatNodeData
  const onAsk = useContext(AskContext)
  const [q, setQ] = useState('')
  const ask = useCallback(async () => {
    if (!q.trim()) return
    const text = q.trim()
    setQ('')
    await onAsk(text)
  }, [onAsk, q])

  return (
    <div className="rf-node chat chat-wide">
      <Handle type="target" position={Position.Left} id="in" />
      <div className="hd">Chat · grounded</div>
      <div className="bd">
        <div className="cite">
          Context: {d.contextSources.length ? d.contextSources.join(', ') : 'no sources selected'}
        </div>
        <div className="chat-log">
          {(d.messages || []).map((m, i) => (
            <div key={i} className={`bubble ${m.role}`}>
              {m.text}
              {m.cites?.length ? <div className="cite">← {m.cites.join(', ')}</div> : null}
            </div>
          ))}
        </div>
        <textarea
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Ask within the dragged context…"
          rows={3}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              ask()
            }
          }}
        />
        <button
          type="button"
          className="btn btn-primary btn-block"
          disabled={d.busy || !d.contextSources.length}
          onClick={ask}
        >
          {d.busy ? 'Answering…' : 'Send'}
        </button>
      </div>
      <Handle type="source" position={Position.Right} id="out" />
    </div>
  )
}

function ArtifactNode({ data }: NodeProps) {
  const d = data as ArtifactNodeData
  return (
    <div className="rf-node artifact artifact-wide">
      <Handle type="target" position={Position.Left} id="in" />
      <div className="hd">{d.label}</div>
      <div className="bd">
        {d.tool === 'quiz' && <QuizWidget items={(d.payload.items as QuizItem[]) || []} />}
        {d.tool === 'flashcards' && <FlashcardsWidget items={(d.payload.items as FlashItem[]) || []} />}
        {d.tool === 'mindmap' && <MindMapWidget data={d.payload} />}
        {(d.tool === 'summary' || d.tool === 'report') && (
          <ReportWidget markdown={String(d.payload.markdown || '')} />
        )}
        {!['quiz', 'flashcards', 'mindmap', 'summary', 'report'].includes(d.tool) && (
          <pre className="payload-pre">{JSON.stringify(d.payload, null, 2).slice(0, 800)}</pre>
        )}
      </div>
    </div>
  )
}

export type QuizItem = { question?: string; options?: string[]; answer?: string; correct?: string }
export type FlashItem = { front?: string; back?: string; q?: string; a?: string }

export const nodeTypes = {
  source: memo(SourceNode),
  chat: memo(ChatNode),
  artifact: memo(ArtifactNode),
}
