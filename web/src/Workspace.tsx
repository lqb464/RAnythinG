import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  addEdge,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type Node,
  type OnConnect,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { api } from './api'
import { GraphMode } from './GraphMode'
import { nodeTypes, type ArtifactNodeData, type ChatNodeData, type SourceNodeData } from './nodes'

const STUDIO_TOOLS: { id: string; label: string }[] = [
  { id: 'summary', label: 'Tóm tắt' },
  { id: 'quiz', label: 'Quiz' },
  { id: 'flashcards', label: 'Flashcards' },
  { id: 'mindmap', label: 'Mind map' },
  { id: 'report', label: 'Báo cáo' },
]

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
  const [context, setContext] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [studioBusy, setStudioBusy] = useState(false)
  const [messages, setMessages] = useState<{ role: 'user' | 'bot'; text: string; cites?: string[] }[]>([])
  const [mode, setMode] = useState<'assembly' | 'graph'>('assembly')
  const fileRef = useRef<HTMLInputElement>(null)

  const initialNodes = useMemo<Node[]>(
    () => [
      {
        id: 'chat-main',
        type: 'chat',
        position: { x: 380, y: 160 },
        data: {
          notebookId,
          contextSources: [],
          messages: [],
          busy: false,
        } satisfies ChatNodeData,
      },
    ],
    [notebookId],
  )

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])

  const onConnect: OnConnect = useCallback(
    (connection: Connection) => {
      setEdges((eds) => addEdge({ ...connection, animated: true }, eds))
      const srcNode = nodes.find((n) => n.id === connection.source)
      if (srcNode?.type === 'source' && connection.target === 'chat-main') {
        const filename = (srcNode.data as SourceNodeData).filename
        setContext((prev) => (prev.includes(filename) ? prev : [...prev, filename]))
      }
    },
    [nodes, setEdges],
  )

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

  // Keep chat node data in sync
  useEffect(() => {
    setNodes((nds) =>
      nds.map((n) =>
        n.id === 'chat-main'
          ? {
              ...n,
              data: {
                notebookId,
                contextSources: context,
                messages,
                busy,
                onAsk: ask,
              } satisfies ChatNodeData,
            }
          : n.type === 'source'
            ? {
                ...n,
                data: {
                  ...(n.data as SourceNodeData),
                  inContext: context.includes((n.data as SourceNodeData).filename),
                },
              }
            : n,
      ),
    )
  }, [ask, busy, context, messages, notebookId, setNodes])

  const addSourceNode = (filename: string) => {
    const id = `src-${filename}`
    setNodes((nds) => {
      if (nds.some((n) => n.id === id)) return nds
      const node: Node = {
        id,
        type: 'source',
        position: { x: 40, y: 80 + nds.filter((n) => n.type === 'source').length * 90 },
        data: { filename, inContext: context.includes(filename) } satisfies SourceNodeData,
      }
      return [...nds, node]
    })
    setEdges((eds) => {
      if (eds.some((e) => e.id === `e-${id}-chat`)) return eds
      return addEdge(
        { id: `e-${id}-chat`, source: id, target: 'chat-main', animated: true },
        eds,
      )
    })
    setContext((prev) => (prev.includes(filename) ? prev : [...prev, filename]))
  }

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
      setEdges((eds) => addEdge({ id: `e-chat-${id}`, source: 'chat-main', target: id, animated: true }, eds))
      onToast(`Đã tạo ${label}`)
    } catch (e) {
      onToast(e instanceof Error ? e.message : 'Studio lỗi')
    } finally {
      setStudioBusy(false)
    }
  }

  const exportNb = async () => {
    try {
      const blob = await api.exportZip(notebookId)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `rananything-${notebookId}.zip`
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
          ← Notebooks
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
          <div className="canvas-hint">Assembly Canvas · kéo source → nối vào Chat · Studio tạo artifact bên phải</div>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            nodeTypes={nodeTypes}
            fitView
            fitViewOptions={{ padding: 0.45, maxZoom: 0.85, minZoom: 0.35 }}
            minZoom={0.25}
            maxZoom={1.75}
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
      )}
    </div>
  )
}
