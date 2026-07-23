'use client'

import dynamic from 'next/dynamic'

const WorkspaceApp = dynamic(() => import('@/components/workspace/WorkspaceApp'), {
  ssr: false,
  loading: () => (
    <div className="app-shell">
      <div className="auth-screen">
        <p className="muted">Loading workspace…</p>
      </div>
    </div>
  ),
})

export default function AppPage() {
  return <WorkspaceApp />
}
