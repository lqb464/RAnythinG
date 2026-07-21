import { memo, useCallback, useState } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { FlashcardsWidget, MindMapWidget, QuizWidget, ReportWidget } from './widgets'

export type SourceNodeData = { filename: string; inContext?: boolean }
export type ChatNodeData = {
  notebookId: string
  contextSources: string[]
  onAsk?: (q: string) => Promise<void>
  messages?: { role: 'user' | 'bot'; text: string; cites?: string[] }[]
  busy?: boolean
}
export type ArtifactNodeData = {
  tool: string
  label: string
  payload: Record<string, unknown>
}

function SourceNode({ data }: NodeProps) {
  const d = data as SourceNodeData
  return (
    <div className={`rf-node source${d.inContext ? ' active' : ''}`}>
      <Handle type="source" position={Position.Right} />
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
  const [q, setQ] = useState('')
  const ask = useCallback(async () => {
    if (!q.trim() || !d.onAsk) return
    const text = q.trim()
    setQ('')
    await d.onAsk(text)
  }, [d, q])

  return (
    <div className="rf-node chat chat-wide">
      <Handle type="target" position={Position.Left} />
      <div className="hd">Chat · grounded</div>
      <div className="bd">
        <div className="cite">
          Context: {d.contextSources.length ? d.contextSources.join(', ') : 'chưa chọn nguồn'}
        </div>
        <div className="chat-log">
          {(d.messages || []).map((m, i) => (
            <div key={i} className={`bubble ${m.role}`}>
              {m.text}
              {m.cites?.length ? <div className="cite">← {m.cites.join(', ')}</div> : null}
            </div>
          ))}
        </div>
        <textarea value={q} onChange={(e) => setQ(e.target.value)} placeholder="Hỏi trong ngữ cảnh đã kéo…" rows={3} />
        <button
          type="button"
          className="btn btn-primary btn-block"
          disabled={d.busy || !d.contextSources.length}
          onClick={ask}
        >
          {d.busy ? 'Đang trả lời…' : 'Gửi'}
        </button>
      </div>
      <Handle type="source" position={Position.Right} />
    </div>
  )
}

function ArtifactNode({ data }: NodeProps) {
  const d = data as ArtifactNodeData
  return (
    <div className="rf-node artifact artifact-wide">
      <Handle type="target" position={Position.Left} />
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
