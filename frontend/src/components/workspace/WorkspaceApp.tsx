'use client'

import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { api, clearToken, getToken, setToken, type NotebookMeta } from '@/lib/api'
import { Workspace } from './Workspace'
import '@/styles/workspace.css'

type User = { id: string; email: string }

export default function WorkspaceApp() {
  const router = useRouter()
  const params = useParams<{ notebookId?: string }>()
  const routeNotebookId = typeof params?.notebookId === 'string' ? params.notebookId : undefined

  const [boot, setBoot] = useState(true)
  const [authRequired, setAuthRequired] = useState(true)
  const [user, setUser] = useState<User | null>(null)
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState('')
  const [toast, setToast] = useState('')
  const [notebooks, setNotebooks] = useState<NotebookMeta[]>([])
  const [active, setActive] = useState<{ id: string; name: string; sources: string[] } | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [createName, setCreateName] = useState('New workspace')
  const [creating, setCreating] = useState(false)

  const showToast = useCallback((m: string) => {
    setToast(m)
    setTimeout(() => setToast(''), 2800)
  }, [])

  const loadNotebooks = useCallback(async () => {
    const list = await api.listNotebooks()
    setNotebooks(list)
  }, [])

  useEffect(() => {
    ;(async () => {
      try {
        const h = await api.health()
        setAuthRequired(!!h.auth_required)
        if (!h.auth_required) {
          setUser({ id: 'anonymous', email: 'local' })
          await loadNotebooks()
        } else if (getToken()) {
          const me = await api.me()
          setUser(me)
          await loadNotebooks()
        }
      } catch {
        /* show auth */
      } finally {
        setBoot(false)
      }
    })()
  }, [loadNotebooks])

  const openNb = useCallback(
    async (id: string, push = true) => {
      try {
        const detail = await api.getNotebook(id)
        setActive({ id: detail.id, name: detail.name, sources: detail.sources || [] })
        if (push) router.push(`/app/${detail.id}`)
      } catch (ex) {
        showToast(ex instanceof Error ? ex.message : 'Could not open workspace')
        router.replace('/app')
      }
    },
    [router, showToast],
  )

  useEffect(() => {
    if (!user || boot) return
    if (routeNotebookId) {
      if (active?.id !== routeNotebookId) {
        openNb(routeNotebookId, false).catch(() => {})
      }
    } else if (active) {
      setActive(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, boot, routeNotebookId])

  const submitAuth = async (e: FormEvent) => {
    e.preventDefault()
    setErr('')
    try {
      const fn = mode === 'login' ? api.login : api.register
      const res = await fn(email.trim(), password)
      setToken(res.access_token)
      setUser(res.user)
      await loadNotebooks()
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : 'Auth failed')
    }
  }

  const deleteNb = async (id: string, name: string) => {
    if (!window.confirm(`Delete workspace «${name}»? All sources, chat, and graph will be lost.`)) return
    try {
      await api.deleteNotebook(id)
      if (active?.id === id) {
        setActive(null)
        router.push('/app')
      }
      await loadNotebooks()
      showToast('Workspace deleted')
    } catch (ex) {
      showToast(ex instanceof Error ? ex.message : 'Delete failed')
    }
  }

  const openCreate = () => {
    setCreateName('New workspace')
    setCreateOpen(true)
  }

  const createNb = async (e?: FormEvent) => {
    e?.preventDefault()
    const name = createName.trim()
    if (!name || creating) return
    setCreating(true)
    try {
      const meta = await api.createNotebook(name)
      setCreateOpen(false)
      await loadNotebooks()
      await openNb(meta.id)
    } catch (ex) {
      showToast(ex instanceof Error ? ex.message : 'Could not create workspace')
    } finally {
      setCreating(false)
    }
  }

  const logout = () => {
    clearToken()
    setUser(null)
    setActive(null)
    setNotebooks([])
    router.push('/app')
  }

  if (boot) {
    return (
      <div className="app-shell">
        <div className="auth-screen">
          <p className="muted">Loading workspace…</p>
        </div>
      </div>
    )
  }

  if (authRequired && !user) {
    return (
      <div className="app-shell">
        <div className="auth-screen">
          <form className="auth-card" onSubmit={submitAuth}>
            <h1>{mode === 'login' ? 'Sign in' : 'Create account'}</h1>
            <p>RAnythinG Assembly Canvas — private workspace</p>
            <label>
              Email
              <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
            </label>
            <label>
              Password
              <input
                type="password"
                required
                minLength={6}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            {err && <div className="err">{err}</div>}
            <button className="btn btn-primary" type="submit">
              {mode === 'login' ? 'Sign in' : 'Sign up'}
            </button>
            <button type="button" className="linkish" onClick={() => setMode(mode === 'login' ? 'register' : 'login')}>
              {mode === 'login' ? 'No account? Sign up' : 'Already have an account? Sign in'}
            </button>
          </form>
        </div>
      </div>
    )
  }

  if (active) {
    return (
      <>
        <Workspace
          notebookId={active.id}
          notebookName={active.name}
          sources={active.sources}
          onSourcesChange={(s) => setActive((a) => (a ? { ...a, sources: s } : a))}
          onBack={() => {
            setActive(null)
            router.push('/app')
            loadNotebooks()
          }}
          onToast={showToast}
          userEmail={user?.email}
          onLogout={logout}
        />
        {toast && <div className="toast">{toast}</div>}
      </>
    )
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          R<span>AnythinG</span>
        </div>
        <span className="muted">Assembly Workspace</span>
        <div className="spacer" />
        <span className="muted">{user?.email}</span>
        {authRequired && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={logout}>
            Sign out
          </button>
        )}
      </header>
      <div className="home-screen">
        <div className="home-card home-wide">
          <h1>Workspaces</h1>
          <p>Create workspace → upload sources → drag and assemble on canvas → interactive Studio artifacts.</p>
          <button className="btn btn-primary" onClick={openCreate}>
            + Create workspace
          </button>
          <div className="nb-grid">
            {notebooks.map((nb) => (
              <div key={nb.id} className="nb-item-wrap">
                <button type="button" className="nb-item" onClick={() => openNb(nb.id)}>
                  <strong>{nb.name}</strong>
                  <span>
                    {nb.source_count ?? 0} sources · {nb.id}
                  </span>
                </button>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm nb-del"
                  title="Delete workspace"
                  onClick={(e) => {
                    e.stopPropagation()
                    deleteNb(nb.id, nb.name)
                  }}
                >
                  Delete
                </button>
              </div>
            ))}
          </div>
          {!notebooks.length && <p className="muted">No workspaces yet — create your first one.</p>}
        </div>
      </div>
      {createOpen && (
        <div className="modal-backdrop" role="presentation" onClick={() => !creating && setCreateOpen(false)}>
          <form
            className="modal-card"
            role="dialog"
            aria-labelledby="create-nb-title"
            onClick={(ev) => ev.stopPropagation()}
            onSubmit={createNb}
          >
            <h2 id="create-nb-title">Create workspace</h2>
            <p>Name your workspace to upload sources and ask questions.</p>
            <label>
              Workspace name
              <input
                autoFocus
                required
                maxLength={120}
                value={createName}
                onChange={(e) => setCreateName(e.target.value)}
                placeholder="New workspace"
              />
            </label>
            <div className="modal-actions">
              <button type="button" className="btn btn-ghost" disabled={creating} onClick={() => setCreateOpen(false)}>
                Cancel
              </button>
              <button type="submit" className="btn btn-primary" disabled={creating || !createName.trim()}>
                {creating ? 'Creating…' : 'Create'}
              </button>
            </div>
          </form>
        </div>
      )}
      {toast && <div className="toast">{toast}</div>}
    </div>
  )
}
