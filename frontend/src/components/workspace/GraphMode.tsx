'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Background,
  Controls,
  ReactFlow,
  Handle,
  Position,
  MarkerType,
  type Node,
  type Edge,
  type NodeProps,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { api, type GraphView } from '@/lib/api'

const COMM_COLORS = ['#38bdf8', '#a78bfa', '#4ade80', '#fbbf24', '#f472b6', '#2dd4bf', '#fb923c']

function EntityNode({ data }: NodeProps) {
  const d = data as {
    label: string
    entity_type?: string
    community?: number | null
    chunk_count?: number
    selected?: boolean
    dimmed?: boolean
  }
  const color = COMM_COLORS[(d.community ?? 0) % COMM_COLORS.length]
  return (
    <div
      className={`rf-node entity entity-compact${d.selected ? ' selected' : ''}${d.dimmed ? ' dimmed' : ''}`}
      style={{ borderColor: color }}
    >
      <Handle type="target" position={Position.Left} className="entity-handle" />
      <div className="hd" style={{ color }}>
        {d.label}
      </div>
      <div className="bd">{d.chunk_count ?? 0} chunks</div>
      <Handle type="source" position={Position.Right} className="entity-handle" />
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
  const [focusComm, setFocusComm] = useState<number | null>(null)
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState('')
  const [asking, setAsking] = useState(false)
  const [confirmClear, setConfirmClear] = useState(false)

  const load = useCallback(async () => {
    try {
      const g = await api.getGraph(notebookId)
      setView(g)
    } catch (e) {
      onToast(e instanceof Error ? e.message : 'Could not load graph')
    }
  }, [notebookId, onToast])

  useEffect(() => {
    load()
  }, [load])

  const build = async () => {
    setBusy(true)
    setAnswer('')
    setSelected(null)
    setFocusComm(null)
    try {
      const g = await api.buildGraph(notebookId, true)
      setView(g)
      onToast(
        `Graph: ${g.build?.entities ?? g.node_count ?? 0} entities · ${g.build?.relations ?? g.edge_count ?? 0} relations`,
      )
    } catch (e) {
      onToast(e instanceof Error ? e.message : 'Build graph error')
    } finally {
      setBusy(false)
    }
  }

  const clear = async () => {
    setConfirmClear(false)
    if (!view?.built) return
    setBusy(true)
    setAnswer('')
    setSelected(null)
    setFocusComm(null)
    try {
      const g = await api.clearGraph(notebookId)
      setView(g)
      onToast('Graph deleted')
    } catch (e) {
      onToast(e instanceof Error ? e.message : 'Delete graph error')
    } finally {
      setBusy(false)
    }
  }

  const nodes: Node[] = useMemo(() => {
    if (!view?.nodes?.length) return []
    return view.nodes.map((n) => {
      const dimmed = focusComm != null && n.community !== focusComm
      return {
        id: n.id,
        type: 'entity',
        position: n.position || { x: 0, y: 0 },
        data: {
          label: n.label,
          entity_type: n.entity_type,
          community: n.community,
          chunk_count: n.chunk_count,
          selected: selected === n.id,
          dimmed,
        },
      }
    })
  }, [view, selected, focusComm])

  const edges: Edge[] = useMemo(() => {
    if (!view?.edges?.length) return []
    const keep =
      focusComm == null
        ? null
        : new Set(view.nodes.filter((n) => n.community === focusComm).map((n) => n.id))
    return view.edges
      .filter((e) => !keep || (keep.has(e.source) && keep.has(e.target)))
      .map((e) => {
        const hasLabel = !!(e.label && e.label.trim() && e.label.toLowerCase() !== 'co-occurs')
        return {
          id: e.id,
          source: e.source,
          target: e.target,
          // Never paint edge labels on canvas — they clutter into "co-occurs" soup
          label: undefined,
          animated: false,
          style: {
            stroke: hasLabel ? 'rgba(0, 149, 255, 0.45)' : 'rgba(51, 65, 85, 0.55)',
            strokeWidth: hasLabel ? 1.5 : 1,
          },
          markerEnd: hasLabel
            ? { type: MarkerType.ArrowClosed, width: 14, height: 14, color: 'rgba(0, 149, 255, 0.55)' }
            : undefined,
        }
      })
  }, [view, focusComm])

  const ask = async () => {
    if (!selected) {
      onToast('Select an entity on the graph')
      return
    }
    setAsking(true)
    try {
      const res = await api.askGraphEntity(notebookId, selected, question)
      setAnswer(res.answer)
    } catch (e) {
      onToast(e instanceof Error ? e.message : 'Ask entity error')
    } finally {
      setAsking(false)
    }
  }

  const selectedNode = view?.nodes.find((n) => n.id === selected)
  const relatedEdges =
    selected && view?.edges
      ? view.edges.filter((e) => e.source === selected || e.target === selected).slice(0, 8)
      : []

  return (
    <div className="graph-mode">
      <div className="graph-toolbar">
        <div className="graph-toolbar-left">
          {view?.built ? (
            <>
              <button type="button" className="btn btn-primary btn-sm" disabled={busy} onClick={build}>
                {busy ? 'Building…' : 'Rebuild'}
              </button>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                disabled={busy}
                onClick={() => setConfirmClear(true)}
              >
                Delete graph
              </button>
            </>
          ) : null}
        </div>
        <div className="graph-stats">
          {view?.built ? (
            <>
              <span>{view.node_count ?? 0} entities</span>
              <span className="dot">·</span>
              <span>{view.edge_count ?? 0} links</span>
              <span className="dot">·</span>
              <span>{view.communities?.length ?? 0} communities</span>
            </>
          ) : (
            <span className="muted">{view?.message || 'No graph yet'}</span>
          )}
        </div>
        {focusComm != null && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => setFocusComm(null)}>
            Clear filter C{focusComm}
          </button>
        )}
      </div>

      <div className="graph-body">
        <div className="graph-canvas">
          {nodes.length ? (
            <ReactFlow
              nodes={nodes}
              edges={edges}
              nodeTypes={entityTypes}
              fitView
              fitViewOptions={{ padding: 0.28, maxZoom: 0.95 }}
              minZoom={0.15}
              maxZoom={1.6}
              nodesConnectable={false}
              elementsSelectable
              onNodeClick={(_, n) => setSelected(n.id)}
              onPaneClick={() => setSelected(null)}
              proOptions={{ hideAttribution: true }}
              defaultEdgeOptions={{ type: 'default' }}
            >
              <Background gap={22} color="#1a2332" />
              <Controls showInteractive={false} />
            </ReactFlow>
          ) : (
            <div className="graph-empty">
              <h3>Knowledge graph</h3>
              <p className="muted">
                Build Graph to extract entities and relations from uploaded documents. Then click a node to ask questions.
              </p>
              <button type="button" className="btn btn-primary" disabled={busy} onClick={build}>
                {busy ? 'Building…' : 'Build Graph'}
              </button>
            </div>
          )}
        </div>

        <aside className="graph-side">
          <section className="graph-panel">
            <h3>Entity</h3>
            {selectedNode ? (
              <>
                <p className="entity-picked">{selectedNode.label}</p>
                <p className="muted text-sm">
                  {(selectedNode.entity_type || 'concept') +
                    ` · ${selectedNode.chunk_count ?? 0} chunks` +
                    (selectedNode.community != null ? ` · C${selectedNode.community}` : '')}
                </p>
                {relatedEdges.length > 0 && (
                  <ul className="rel-list">
                    {relatedEdges.map((e) => {
                      const otherId = e.source === selected ? e.target : e.source
                      const other = view?.nodes.find((n) => n.id === otherId)?.label || otherId
                      const rel = e.label?.trim() && e.label.toLowerCase() !== 'co-occurs' ? e.label : 'related to'
                      return (
                        <li key={e.id}>
                          <button type="button" className="linkish" onClick={() => setSelected(otherId)}>
                            {rel} → {other}
                          </button>
                        </li>
                      )
                    })}
                  </ul>
                )}
                <textarea
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder="Ask about this entity (leave blank to explain)…"
                  rows={3}
                />
                <button type="button" className="btn btn-primary" disabled={asking} onClick={ask}>
                  {asking ? 'Asking…' : 'Ask about entity'}
                </button>
                {answer && <div className="bubble mt-2">{answer}</div>}
              </>
            ) : (
              <p className="muted text-sm">Click a node on the graph to view relations and ask questions.</p>
            )}
          </section>

          <section className="graph-panel">
            <h3>Communities</h3>
            <div className="comm-list">
              {(view?.communities || []).slice(0, 10).map((c) => (
                <button
                  key={c.id}
                  type="button"
                  className={`comm-card${focusComm === c.id ? ' active' : ''}`}
                  onClick={() => setFocusComm((cur) => (cur === c.id ? null : c.id))}
                >
                  <strong style={{ color: COMM_COLORS[c.id % COMM_COLORS.length] }}>C{c.id}</strong>
                  <span className="muted"> · {(c.entity_names || []).slice(0, 3).join(', ')}</span>
                  <p>{c.summary?.slice(0, 140) || '—'}</p>
                </button>
              ))}
              {!view?.communities?.length && <p className="muted text-sm">No communities yet</p>}
            </div>
          </section>
        </aside>
      </div>

      {confirmClear && (
        <div className="modal-backdrop" role="presentation" onClick={() => !busy && setConfirmClear(false)}>
          <div className="modal-card" role="dialog" onClick={(e) => e.stopPropagation()}>
            <h2>Delete knowledge graph?</h2>
            <p>Only deletes the entity graph. Source documents and Assembly chat are kept.</p>
            <div className="modal-actions">
              <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => setConfirmClear(false)}>
                Cancel
              </button>
              <button type="button" className="btn btn-primary" disabled={busy} onClick={clear}>
                Delete graph
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
