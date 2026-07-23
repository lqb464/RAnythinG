import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { api, clearToken, getToken, setToken, type NotebookMeta } from './api'
import { Workspace } from './Workspace'

type User = { id: string; email: string }

export default function App() {
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
  const [createName, setCreateName] = useState('Workspace mới')
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

  const openNb = async (id: string) => {
    try {
      const detail = await api.getNotebook(id)
      setActive({ id: detail.id, name: detail.name, sources: detail.sources || [] })
      const hash = detail.id
      if (location.hash.slice(1) !== hash) location.hash = hash
    } catch (ex) {
      showToast(ex instanceof Error ? ex.message : 'Không mở được workspace')
    }
  }

  useEffect(() => {
    if (!user || boot) return
    const id = location.hash.slice(1)
    if (id && !active) openNb(id).catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, boot])

  const deleteNb = async (id: string, name: string) => {
    if (!window.confirm(`Xóa workspace «${name}»? Toàn bộ nguồn, chat và graph sẽ mất.`)) return
    try {
      await api.deleteNotebook(id)
      if (active?.id === id) {
        setActive(null)
        location.hash = ''
      }
      await loadNotebooks()
      showToast('Đã xóa workspace')
    } catch (ex) {
      showToast(ex instanceof Error ? ex.message : 'Xóa thất bại')
    }
  }

  const openCreate = () => {
    setCreateName('Workspace mới')
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
      showToast(ex instanceof Error ? ex.message : 'Không tạo được workspace')
    } finally {
      setCreating(false)
    }
  }

  const logout = () => {
    clearToken()
    setUser(null)
    setActive(null)
    setNotebooks([])
  }

  if (boot) {
    return (
      <div className="app-shell">
        <div className="auth-screen">
          <p className="muted">Đang tải Workspace…</p>
        </div>
      </div>
    )
  }

  if (authRequired && !user) {
    return (
      <div className="app-shell">
        <div className="auth-screen">
          <form className="auth-card" onSubmit={submitAuth}>
            <h1>{mode === 'login' ? 'Đăng nhập' : 'Tạo tài khoản'}</h1>
            <p>RAnythinG Assembly Canvas — workspace riêng tư</p>
            <label>
              Email
              <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
            </label>
            <label>
              Mật khẩu
              <input type="password" required minLength={6} value={password} onChange={(e) => setPassword(e.target.value)} />
            </label>
            {err && <div className="err">{err}</div>}
            <button className="btn btn-primary" type="submit">
              {mode === 'login' ? 'Đăng nhập' : 'Đăng ký'}
            </button>
            <button type="button" className="linkish" onClick={() => setMode(mode === 'login' ? 'register' : 'login')}>
              {mode === 'login' ? 'Chưa có tài khoản? Đăng ký' : 'Đã có tài khoản? Đăng nhập'}
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
            location.hash = ''
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
            Đăng xuất
          </button>
        )}
      </header>
      <div className="home-screen">
        <div className="home-card home-wide">
          <h1>Workspaces</h1>
          <p>Tạo workspace → upload nguồn → kéo lắp trên canvas → Studio artifact tương tác.</p>
          <button className="btn btn-primary" onClick={openCreate}>
            + Tạo workspace
          </button>
          <div className="nb-grid">
            {notebooks.map((nb) => (
              <div key={nb.id} className="nb-item-wrap">
                <button type="button" className="nb-item" onClick={() => openNb(nb.id)}>
                  <strong>{nb.name}</strong>
                  <span>{nb.source_count ?? 0} nguồn · {nb.id}</span>
                </button>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm nb-del"
                  title="Xóa workspace"
                  onClick={(e) => {
                    e.stopPropagation()
                    deleteNb(nb.id, nb.name)
                  }}
                >
                  Xóa
                </button>
              </div>
            ))}
          </div>
          {!notebooks.length && <p className="muted">Chưa có workspace — tạo cái đầu tiên.</p>}
        </div>
      </div>
      {createOpen && (
        <div
          className="modal-backdrop"
          role="presentation"
          onClick={() => !creating && setCreateOpen(false)}
        >
          <form
            className="modal-card"
            role="dialog"
            aria-labelledby="create-nb-title"
            onClick={(ev) => ev.stopPropagation()}
            onSubmit={createNb}
          >
            <h2 id="create-nb-title">Tạo workspace</h2>
            <p>Đặt tên workspace để upload nguồn và hỏi đáp.</p>
            <label>
              Tên workspace
              <input
                autoFocus
                required
                maxLength={120}
                value={createName}
                onChange={(e) => setCreateName(e.target.value)}
                placeholder="Workspace mới"
              />
            </label>
            <div className="modal-actions">
              <button
                type="button"
                className="btn btn-ghost"
                disabled={creating}
                onClick={() => setCreateOpen(false)}
              >
                Hủy
              </button>
              <button type="submit" className="btn btn-primary" disabled={creating || !createName.trim()}>
                {creating ? 'Đang tạo…' : 'Tạo'}
              </button>
            </div>
          </form>
        </div>
      )}
      {toast && <div className="toast">{toast}</div>}
    </div>
  )
}
