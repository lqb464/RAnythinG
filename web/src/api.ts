/** API client for RAnythinG backend */

const TOKEN_KEY = 'rananything_token'

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem('rananything_refresh')
}

async function request<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    ...(opts.headers as Record<string, string> | undefined),
  }
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  if (opts.body && !(opts.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json'
  }
  const res = await fetch(path, { ...opts, headers })
  if (res.status === 401) {
    clearToken()
    throw new Error('UNAUTHORIZED')
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    const detail = err.detail
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail) || 'API error')
  }
  if (res.headers.get('content-type')?.includes('application/zip')) {
    return (await res.blob()) as T
  }
  return res.json()
}

export const api = {
  health: () => request<{ auth_required: boolean; version?: string }>('/api/health'),
  register: (email: string, password: string) =>
    request<{ access_token: string; user: { id: string; email: string } }>('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  login: (email: string, password: string) =>
    request<{ access_token: string; user: { id: string; email: string } }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  me: () => request<{ id: string; email: string }>('/api/auth/me'),
  listNotebooks: () => request<NotebookMeta[]>('/api/notebooks'),
  createNotebook: (name: string) =>
    request<NotebookMeta>('/api/notebooks', { method: 'POST', body: JSON.stringify({ name }) }),
  getNotebook: (id: string) => request<NotebookDetail>(`/api/notebooks/${id}`),
  upload: async (id: string, files: FileList | File[]) => {
    const fd = new FormData()
    ;[...files].forEach((f) => fd.append('files', f))
    return request<{ added: string[]; sources: string[]; indexed: boolean; stats: { chunks: number } }>(
      `/api/notebooks/${id}/upload`,
      { method: 'POST', body: fd },
    )
  },
  deleteSource: (id: string, filename: string) =>
    request<{ sources: string[] }>(`/api/notebooks/${id}/sources/${encodeURIComponent(filename)}`, {
      method: 'DELETE',
    }),
  chat: (id: string, query: string, sources: string[]) =>
    request<{ answer: string; answer_html: string; sources: { source: string; text: string }[] }>(
      `/api/notebooks/${id}/chat`,
      { method: 'POST', body: JSON.stringify({ query, sources }) },
    ),
  studio: (id: string, tool: string, sources: string[]) =>
    request<Record<string, unknown>>(`/api/notebooks/${id}/studio/${tool}`, {
      method: 'POST',
      body: JSON.stringify({ sources }),
    }),
  exportZip: (id: string) => request<Blob>(`/api/notebooks/${id}/export`),
  getGraph: (id: string) => request<GraphView>(`/api/notebooks/${id}/graph`),
  buildGraph: (id: string, use_llm = true) =>
    request<GraphView>(`/api/notebooks/${id}/graph/build`, {
      method: 'POST',
      body: JSON.stringify({ use_llm, max_nodes: 60 }),
    }),
  askGraphEntity: (id: string, entity_id: string, question = '') =>
    request<{ answer: string; sources: { source: string; text: string }[] }>(
      `/api/notebooks/${id}/graph/ask`,
      { method: 'POST', body: JSON.stringify({ entity_id, question }) },
    ),
}

export type GraphNode = {
  id: string
  label: string
  entity_type?: string
  community?: number | null
  chunk_count?: number
  sources?: string[]
  position: { x: number; y: number }
}

export type GraphEdge = {
  id: string
  source: string
  target: string
  label?: string
}

export type GraphView = {
  ok: boolean
  built?: boolean
  message?: string
  nodes: GraphNode[]
  edges: GraphEdge[]
  communities: { id: number; entity_names: string[]; summary: string; chunk_count?: number }[]
  node_count?: number
  edge_count?: number
  build?: { entities?: number; relations?: number; communities?: number }
}

export type NotebookMeta = {
  id: string
  name: string
  source_count?: number
  updated_at?: string
}

export type NotebookDetail = NotebookMeta & {
  sources: string[]
  indexed: boolean
  stats: { documents?: number; chunks?: number }
}
