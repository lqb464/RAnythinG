import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  MiniMap,
  addEdge,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Connection,
  type Edge,
  type Node,
  type OnConnect,
  type Viewport,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { api } from './api'
import { FlowErrorBoundary } from './FlowErrorBoundary'
import { GraphMode } from './GraphMode'
import {
  AskContext,
  nodeTypes,
  type ArtifactNodeData,
  type ChatNodeData,
  type SourceNodeData,
} from './nodes'

const STUDIO_TOOLS: { id: string; label: string }[] = [
  { id: 'summary', label: 'Tóm tắt' },
  { id: 'quiz', label: 'Quiz' },
  { id: 'flashcards', label: 'Flashcards' },
  { id: 'mindmap', label: 'Mind map' },
  { id: 'report', label: 'Báo cáo' },
]

type ChatMsg = { role: 'user' | 'bot'; text: string; cites?: string[] }

type AssemblySnap = {
  nodes: Node[]
  edges: Edge[]
  context: string[]
  messages: ChatMsg[]
  viewport?: Viewport
}

type Props = {
  notebookId: string
  notebookName: string
  sources: string[]
  onSourcesChange: (s: string[]) => void
  onBack: () => void
  onToast: (m: string) => void
  userEmail?: string
  onLogout: () => void
}

function storageKey(notebookId: string) {
  return `ranything:assembly:${notebookId}`
}

function defaultChatNode(notebookId: string): Node {
  return {
    id: 'chat-main',
    type: 'chat',
    position: { x: 380, y: 160 },
    data: {
      notebookId,
      contextSources: [],
      messages: [],
      busy: false,
    } satisfies ChatNodeData,
  }
}

function loadSnap(notebookId: string): AssemblySnap | null {
  try {
    const raw = localStorage.getItem(storageKey(notebookId))
    if (!raw) return null
    return JSON.parse(raw) as AssemblySnap
  } catch {
    return null
  }
}

function sanitizeNodes(nodes: Node[], notebookId: string): Node[] {
  return nodes.map((n) => {
    if (n.type === 'chat') {
      const d = n.data as ChatNodeData
      return {
        ...n,
        data: {
          notebookId,
          contextSources: d.contextSources || [],
          messages: d.messages || [],
          busy: false,
        } satisfies ChatNodeData,
      }
    }
    if (n.type === 'source') {
      const d = n.data as SourceNodeData
      return {
        ...n,
        data: { filename: d.filename, inContext: !!d.inContext } satisfies SourceNodeData,
      }
    }
    if (n.type === 'artifact') {
      const d = n.data as ArtifactNodeData
      return {
        ...n,
        data: { tool: d.tool, label: d.label, payload: d.payload || {} } satisfies ArtifactNodeData,
      }
    }
    return n
  })
}

function ensureSourcesOnBoard(
  notebookId: string,
  nodes: Node[],
  edges: Edge[],
  context: string[],
  sources: string[],
): { nodes: Node[]; edges: Edge[]; context: string[] } {
  let ns = nodes.length ? [...nodes] : [defaultChatNode(notebookId)]
  if (!ns.some((n) => n.id === 'chat-main')) {
    ns = [defaultChatNode(notebookId), ...ns]
  }
  let es = [...edges]
  let ctx = [...context]

  sources.forEach((filename, i) => {
    const id = `src-${filename}`
    if (!ns.some((n) => n.id === id)) {
      ns.push({
        id,
        type: 'source',
        position: { x: 40, y: 80 + i * 90 },
        data: { filename, inContext: true } satisfies SourceNodeData,
      })
    } else {
      ns = ns.map((n) =>
        n.id === id
          ? { ...n, data: { ...(n.data as SourceNodeData), inContext: true } }
          : n,
      )
    }
    if (!es.some((e) => e.source === id && e.target === 'chat-main')) {
      es.push({
        id: `e-${id}-chat`,
        source: id,
        target: 'chat-main',
        sourceHandle: 'out',
        targetHandle: 'in',
        animated: true,
      })
    }
    if (!ctx.includes(filename)) ctx.push(filename)
  })

  return { nodes: sanitizeNodes(ns, notebookId), edges: es, context: ctx }
}

function pickBoard(
  server: AssemblySnap | null,
  local: AssemblySnap | null,
  notebookId: string,
): AssemblySnap {
  const serverScore = server?.nodes?.length || 0
  const localScore = local?.nodes?.length || 0
  const chosen = serverScore >= localScore ? server : local
  if (chosen?.nodes?.length) {
    return {
      nodes: sanitizeNodes(chosen.nodes, notebookId),
      edges: chosen.edges || [],
      context: chosen.context || [],
      messages: chosen.messages || [],
      viewport: chosen.viewport,
    }
  }
  return {
    nodes: [defaultChatNode(notebookId)],
    edges: [],
    context: [],
    messages: [],
  }
}

function AssemblyCanvas({
  notebookId,
  sources,
  onSourcesChange,
  onToast,
}: {
  notebookId: string
  sources: string[]
  onSourcesChange: (s: string[]) => void
  onToast: (m: string) => void
}) {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([defaultChatNode(notebookId)])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])
  const [context, setContext] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [studioBusy, setStudioBusy] = useState(false)
  const [messages, setMessages] = useState<ChatMsg[]>([])
  const [flowKey, setFlowKey] = useState(0)
  const [ready, setReady] = useState(false)
  const [savedViewport, setSavedViewport] = useState<Viewport | undefined>()
  const fileRef = useRef<HTMLInputElement>(null)
  const fitted = useRef(false)
  const { fitView, setViewport, getViewport } = useReactFlow()

  // Hydrate board from server (prefer) + localStorage backup; seed source nodes
  useEffect(() => {
    let cancelled = false
    setReady(false)
    fitted.current = false
    ;(async () => {
      let server: AssemblySnap | null = null
      try {
        const remote = await api.getAssembly(notebookId)
        if (remote && (remote.nodes?.length || remote.edges?.length || remote.messages?.length)) {
          server = {
            nodes: (remote.nodes || []) as Node[],
            edges: (remote.edges || []) as Edge[],
            context: remote.context || [],
            messages: remote.messages || [],
            viewport: remote.viewport || undefined,
          }
        }
      } catch {
        /* offline / first open */
      }
      if (cancelled) return
      const local = loadSnap(notebookId)
      const base = pickBoard(server, local, notebookId)
      const seeded = ensureSourcesOnBoard(notebookId, base.nodes, base.edges, base.context, sources)
      setNodes(seeded.nodes)
      setEdges(seeded.edges)
      setContext(seeded.context)
      setMessages(base.messages)
      setSavedViewport(base.viewport)
      setReady(true)
    })()
    return () => {
      cancelled = true
    }
    // sources intentionally omitted: re-seed via separate effect after ready
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [notebookId, setNodes, setEdges])

  const edgesRef = useRef(edges)
  const contextRef = useRef(context)
  edgesRef.current = edges
  contextRef.current = context

  // When new files appear on server, put them on the canvas automatically
  useEffect(() => {
    if (!ready || !sources.length) return
    setNodes((nds) => {
      const missing = sources.some((f) => !nds.some((n) => n.id === `src-${f}`))
      if (!missing) return nds
      const next = ensureSourcesOnBoard(notebookId, nds, edgesRef.current, contextRef.current, sources)
      setEdges(next.edges)
      setContext(next.context)
      return next.nodes
    })
  }, [sources, ready, notebookId, setNodes, setEdges])

  useEffect(() => {
    fitted.current = false
  }, [notebookId, flowKey, ready])

  const onInit = useCallback(() => {
    if (fitted.current || !ready) return
    fitted.current = true
    if (savedViewport) {
      setViewport(savedViewport)
      return
    }
    fitView({ padding: 0.45, maxZoom: 0.85, minZoom: 0.35 })
  }, [fitView, setViewport, savedViewport, ready])

  const ask = useCallback(
    async (query: string) => {
      if (!context.length) {
        onToast('Kéo ít nhất 1 source vào Chat (nối cạnh) hoặc chọn trong panel')
        return
      }
      setBusy(true)
      setMessages((m) => [...m, { role: 'user', text: query }])
      try {
        const res = await api.chat(notebookId, query, context)
        setMessages((m) => [
          ...m,
          {
            role: 'bot',
            text: res.answer,
            cites: (res.sources || []).map((s) => s.source),
          },
        ])
      } catch (e) {
        onToast(e instanceof Error ? e.message : 'Chat lỗi')
      } finally {
        setBusy(false)
      }
    },
    [context, notebookId, onToast],
  )

  // Sync serializable chat/source fields only — never put functions into node.data
  useEffect(() => {
    setNodes((nds) =>
      nds.map((n) => {
        if (n.id === 'chat-main') {
          const prev = n.data as ChatNodeData
          if (
            prev.notebookId === notebookId &&
            prev.busy === busy &&
            prev.messages === messages &&
            prev.contextSources === context
          ) {
            return n
          }
          return {
            ...n,
            data: {
              notebookId,
              contextSources: context,
              messages,
              busy,
            } satisfies ChatNodeData,
          }
        }
        if (n.type === 'source') {
          const d = n.data as SourceNodeData
          const inContext = context.includes(d.filename)
          if (d.inContext === inContext) return n
          return { ...n, data: { ...d, inContext } }
        }
        return n
      }),
    )
  }, [busy, context, messages, notebookId, setNodes])

  // Persist assembly board to localStorage + server (after hydrate)
  useEffect(() => {
    if (!ready) return
    const t = window.setTimeout(() => {
      const payload: AssemblySnap = {
        nodes: sanitizeNodes(nodes, notebookId),
        edges,
        context,
        messages,
        viewport: getViewport(),
      }
      try {
        localStorage.setItem(storageKey(notebookId), JSON.stringify(payload))
      } catch {
        /* quota */
      }
      api.saveAssembly(notebookId, payload).catch(() => {
        /* keep local copy */
      })
    }, 600)
    return () => window.clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, edges, context, messages, notebookId, ready])

  const nodesRef = useRef(nodes)
  nodesRef.current = nodes

  const onConnect: OnConnect = useCallback(
    (connection: Connection) => {
      if (!connection.source || !connection.target) return
      setEdges((eds) =>
        addEdge(
          {
            ...connection,
            id: `e-${connection.source}-${connection.target}-${eds.length}`,
            animated: true,
          },
          eds,
        ),
      )
      const srcNode = nodesRef.current.find((n) => n.id === connection.source)
      if (srcNode?.type === 'source' && connection.target === 'chat-main') {
        const filename = (srcNode.data as SourceNodeData).filename
        setContext((prev) => (prev.includes(filename) ? prev : [...prev, filename]))
      }
    },
    [setEdges],
  )

  const addSourceNode = useCallback(
    (filename: string) => {
      const id = `src-${filename}`
      setNodes((nds) => {
        if (nds.some((n) => n.id === id)) return nds
        const node: Node = {
          id,
          type: 'source',
          position: { x: 40, y: 80 + nds.filter((n) => n.type === 'source').length * 90 },
          data: { filename, inContext: true } satisfies SourceNodeData,
        }
        return [...nds, node]
      })
      setEdges((eds) => {
        if (eds.some((e) => e.source === id && e.target === 'chat-main')) return eds
        return addEdge(
          { id: `e-${id}-chat`, source: id, target: 'chat-main', sourceHandle: 'out', targetHandle: 'in', animated: true },
          eds,
        )
      })
      setContext((prev) => (prev.includes(filename) ? prev : [...prev, filename]))
    },
    [setEdges, setNodes],
  )

  const toggleContext = (filename: string) => {
    setContext((prev) => (prev.includes(filename) ? prev.filter((x) => x !== filename) : [...prev, filename]))
    addSourceNode(filename)
  }

  const onUpload = async (files: FileList | null) => {
    if (!files?.length) return
    try {
      const res = await api.upload(notebookId, files)
      onSourcesChange(res.sources)
      res.added.forEach(addSourceNode)
      onToast(`Đã thêm ${res.added.length} nguồn`)
    } catch (e) {
      onToast(e instanceof Error ? e.message : 'Upload lỗi')
    }
  }

  const runStudio = async (tool: string, label: string) => {
    const srcs = context.length ? context : sources
    if (!srcs.length) {
      onToast('Cần ít nhất 1 nguồn')
      return
    }
    setStudioBusy(true)
    try {
      const payload = await api.studio(notebookId, tool, srcs)
      const id = `art-${tool}-${Date.now()}`
      setNodes((nds) => [
        ...nds,
        {
          id,
          type: 'artifact',
          position: { x: 760, y: 80 + nds.filter((n) => n.type === 'artifact').length * 40 },
          data: { tool, label, payload } satisfies ArtifactNodeData,
        },
      ])
      setEdges((eds) =>
        addEdge(
          {
            id: `e-chat-${id}`,
            source: 'chat-main',
            target: id,
            sourceHandle: 'out',
            targetHandle: 'in',
            animated: true,
          },
          eds,
        ),
      )
      onToast(`Đã tạo ${label}`)
    } catch (e) {
      onToast(e instanceof Error ? e.message : 'Studio lỗi')
    } finally {
      setStudioBusy(false)
    }
  }

  return (
    <AskContext.Provider value={ask}>
      <div className="workspace">
        <aside className="side-panel">
          <div className="side-hd">
            Sources <span className="spacer" />
            <button className="btn btn-sm" type="button" onClick={() => fileRef.current?.click()}>
              Upload
            </button>
          </div>
          <div className="side-body">
            <div
              className="dropzone"
              onDragOver={(e) => {
                e.preventDefault()
                e.currentTarget.classList.add('over')
              }}
              onDragLeave={(e) => e.currentTarget.classList.remove('over')}
              onDrop={(e) => {
                e.preventDefault()
                e.currentTarget.classList.remove('over')
                onUpload(e.dataTransfer.files)
              }}
              onClick={() => fileRef.current?.click()}
            >
              Kéo file PDF/DOCX/MD vào đây
            </div>
            <input
              ref={fileRef}
              type="file"
              multiple
              hidden
              accept=".pdf,.docx,.pptx,.txt,.md,.csv,.html"
              onChange={(e) => onUpload(e.target.files)}
            />
            {sources.map((s) => (
              <div
                key={s}
                className={`source-chip${context.includes(s) ? ' active' : ''}`}
                draggable
                onDragStart={(e) => e.dataTransfer.setData('text/source', s)}
                onClick={() => toggleContext(s)}
                title="Bấm để đưa vào context + canvas"
              >
                {s}
              </div>
            ))}
            {!sources.length && <p className="muted text-sm">Chưa có nguồn — upload để bắt đầu</p>}
          </div>
        </aside>

        <main
          className="canvas-wrap"
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            const name = e.dataTransfer.getData('text/source')
            if (name) addSourceNode(name)
          }}
        >
          <div className="canvas-hint">
            Assembly Canvas · kéo source → nối vào Chat · board được lưu trên server
          </div>
          {!ready ? (
            <div className="graph-empty">
              <p className="muted">Đang tải workspace…</p>
            </div>
          ) : (
          <FlowErrorBoundary onReset={() => setFlowKey((k) => k + 1)}>
            <ReactFlow
              key={flowKey}
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              nodeTypes={nodeTypes}
              onInit={onInit}
              minZoom={0.25}
              maxZoom={1.75}
              deleteKeyCode={['Backspace', 'Delete']}
              proOptions={{ hideAttribution: true }}
            >
              <Background gap={18} color="#1e293b" />
              <Controls showInteractive={false} />
              <MiniMap
                pannable
                zoomable
                maskColor="rgba(6, 10, 18, 0.7)"
                nodeColor="#1e3a5f"
                style={{ background: '#0b1220' }}
              />
            </ReactFlow>
          </FlowErrorBoundary>
          )}
        </main>

        <aside className="side-panel right">
          <div className="side-hd">Studio · lắp artifact</div>
          <div className="side-body">
            <p className="muted text-sm" style={{ margin: 0 }}>
              Dùng context đang chọn ({context.length || 'all'} nguồn) để sinh widget tương tác trên canvas.
            </p>
            <div className="studio-tools">
              {STUDIO_TOOLS.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  className="btn"
                  disabled={studioBusy}
                  onClick={() => runStudio(t.id, t.label)}
                >
                  {t.label}
                </button>
              ))}
            </div>
            <p className="muted text-sm">
              Quiz chấm điểm · Flashcard lật · Mind map expand — kéo sắp xếp trên board.
            </p>
          </div>
        </aside>
      </div>
    </AskContext.Provider>
  )
}

export function Workspace({
  notebookId,
  notebookName,
  sources,
  onSourcesChange,
  onBack,
  onToast,
  userEmail,
  onLogout,
}: Props) {
  const [mode, setMode] = useState<'assembly' | 'graph'>('assembly')

  const exportNb = async () => {
    try {
      const blob = await api.exportZip(notebookId)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `ranything-${notebookId}.zip`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      onToast(e instanceof Error ? e.message : 'Export lỗi')
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <button className="btn btn-ghost btn-sm" onClick={onBack}>
          ← Workspaces
        </button>
        <div className="brand">
          R<span>AnythinG</span>
        </div>
        <strong className="nb-title" title={notebookName}>
          {notebookName}
        </strong>
        <div className="mode-toggle" role="group" aria-label="Chế độ workspace">
          <button
            type="button"
            className={`seg${mode === 'assembly' ? ' active' : ''}`}
            onClick={() => setMode('assembly')}
          >
            Assembly
          </button>
          <button type="button" className={`seg${mode === 'graph' ? ' active' : ''}`} onClick={() => setMode('graph')}>
            Graph
          </button>
        </div>
        <div className="spacer" />
        <span className="muted">{userEmail}</span>
        <button className="btn btn-sm" onClick={exportNb}>
          Export
        </button>
        <button className="btn btn-ghost btn-sm" onClick={onLogout}>
          Đăng xuất
        </button>
      </header>

      {mode === 'graph' ? (
        <GraphMode notebookId={notebookId} onToast={onToast} />
      ) : (
        <ReactFlowProvider>
          <AssemblyCanvas
            key={notebookId}
            notebookId={notebookId}
            sources={sources}
            onSourcesChange={onSourcesChange}
            onToast={onToast}
          />
        </ReactFlowProvider>
      )}
    </div>
  )
}
