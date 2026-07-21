import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  Handle,
  Position,
  type Node,
  type Edge,
  type NodeProps,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { api, type GraphView } from './api'

const COMM_COLORS = ['#38bdf8', '#a78bfa', '#4ade80', '#fbbf24', '#f472b6', '#2dd4bf', '#fb923c']

function EntityNode({ data }: NodeProps) {
  const d = data as {
    label: string
    entity_type?: string
    community?: number | null
    chunk_count?: number
    selected?: boolean
  }
  const color = COMM_COLORS[(d.community ?? 0) % COMM_COLORS.length]
  return (
    <div
      className={`rf-node entity${d.selected ? ' selected' : ''}`}
      style={{ borderColor: color, minWidth: 140, maxWidth: 200 }}
    >
      <Handle type="target" position={Position.Left} />
      <div className="hd" style={{ color }}>
        {d.label}
      </div>
      <div className="bd" style={{ fontSize: '0.72rem' }}>
        {d.entity_type || 'concept'} · {d.chunk_count ?? 0} chunks
      </div>
      <Handle type="source" position={Position.Right} />
    </div>
  )
}

const entityTypes = { entity: EntityNode }

type Props = {
  notebookId: string
  onToast: (m: string) => void
}

export function GraphMode({ notebookId, onToast }: Props) {
  const [view, setView] = useState<GraphView | null>(null)
  const [busy, setBusy] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState('')
  const [asking, setAsking] = useState(false)

  const load = useCallback(async () => {
    try {
      const g = await api.getGraph(notebookId)
      setView(g)
    } catch (e) {
      onToast(e instanceof Error ? e.message : 'Không tải được graph')
    }
  }, [notebookId, onToast])

  useEffect(() => {
    load()
  }, [load])

  const build = async (useLlm: boolean) => {
    setBusy(true)
    setAnswer('')
    try {
      const g = await api.buildGraph(notebookId, useLlm)
      setView(g)
      onToast(
        `Graph: ${g.build?.entities ?? g.node_count ?? 0} entities · ${g.build?.relations ?? g.edge_count ?? 0} relations`,
      )
    } catch (e) {
      onToast(e instanceof Error ? e.message : 'Build graph lỗi')
    } finally {
      setBusy(false)
    }
  }

  const nodes: Node[] = useMemo(() => {
    if (!view?.nodes?.length) return []
    return view.nodes.map((n) => ({
      id: n.id,
      type: 'entity',
      position: n.position || { x: 0, y: 0 },
      data: {
        label: n.label,
        entity_type: n.entity_type,
        community: n.community,
        chunk_count: n.chunk_count,
        selected: selected === n.id,
      },
    }))
  }, [view, selected])

  const edges: Edge[] = useMemo(() => {
    if (!view?.edges?.length) return []
    return view.edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      label: e.label,
      animated: false,
      style: { stroke: '#334155' },
      labelStyle: { fill: '#94a3b8', fontSize: 10 },
    }))
  }, [view])

  const ask = async () => {
    if (!selected) {
      onToast('Chọn một entity trên graph')
      return
    }
    setAsking(true)
    try {
      const res = await api.askGraphEntity(notebookId, selected, question)
      setAnswer(res.answer)
    } catch (e) {
      onToast(e instanceof Error ? e.message : 'Ask entity lỗi')
    } finally {
      setAsking(false)
    }
  }

  const selectedLabel = view?.nodes.find((n) => n.id === selected)?.label

  return (
    <div className="graph-mode">
      <div className="graph-toolbar">
        <button type="button" className="btn btn-primary btn-sm" disabled={busy} onClick={() => build(true)}>
          {busy ? 'Đang build…' : 'Build Graph (LLM)'}
        </button>
        <button type="button" className="btn btn-sm" disabled={busy} onClick={() => build(false)}>
          Build nhanh (rule)
        </button>
        <button type="button" className="btn btn-ghost btn-sm" onClick={load}>
          Refresh
        </button>
        <span className="muted">
          {view?.built
            ? `${view.node_count ?? 0} nodes · ${view.edge_count ?? 0} edges · ${view.communities?.length ?? 0} communities`
            : view?.message || 'Chưa build — bấm Build Graph'}
        </span>
      </div>

      <div className="graph-body">
        <div className="graph-canvas">
          {nodes.length ? (
            <ReactFlow
              nodes={nodes}
              edges={edges}
              nodeTypes={entityTypes}
              fitView
              fitViewOptions={{ padding: 0.35, maxZoom: 1 }}
              minZoom={0.2}
              maxZoom={1.75}
              onNodeClick={(_, n) => setSelected(n.id)}
              proOptions={{ hideAttribution: true }}
            >
              <Background gap={20} color="#1e293b" />
              <Controls showInteractive={false} />
              <MiniMap
                maskColor="rgba(6, 10, 18, 0.7)"
                nodeColor="#1e3a5f"
                style={{ background: '#0b1220' }}
              />
            </ReactFlow>
          ) : (
            <div className="graph-empty">
              <p>Knowledge graph trống.</p>
              <p className="muted">Upload tài liệu rồi bấm Build Graph để trích entity · quan hệ · community.</p>
            </div>
          )}
        </div>

        <aside className="graph-side">
          <h3>Ask from node</h3>
          <p className="muted text-sm">
            {selectedLabel ? `Đang chọn: ${selectedLabel}` : 'Click entity trên graph'}
          </p>
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Để trống = giải thích khái niệm này…"
            rows={3}
          />
          <button type="button" className="btn btn-primary" disabled={!selected || asking} onClick={ask}>
            {asking ? 'Đang hỏi…' : 'Hỏi về entity'}
          </button>
          {answer && <div className="bubble mt-2">{answer}</div>}

          <h3 className="section-gap">Communities</h3>
          <div className="comm-list">
            {(view?.communities || []).slice(0, 8).map((c) => (
              <div key={c.id} className="comm-card">
                <strong style={{ color: COMM_COLORS[c.id % COMM_COLORS.length] }}>C{c.id}</strong>
                <span className="muted"> · {(c.entity_names || []).slice(0, 4).join(', ')}</span>
                <p>{c.summary?.slice(0, 180) || '—'}</p>
              </div>
            ))}
            {!view?.communities?.length && <p className="muted">Chưa có community</p>}
          </div>
        </aside>
      </div>
    </div>
  )
}
