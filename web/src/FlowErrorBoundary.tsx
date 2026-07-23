import { Component, type ErrorInfo, type ReactNode } from 'react'

type Props = { children: ReactNode; onReset?: () => void }
type State = { error: Error | null }

/** Catch React Flow crashes so the whole /app shell does not go blank. */
export class FlowErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Assembly canvas crash', error, info.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="graph-empty">
          <p>Canvas gặp lỗi khi kéo nối node.</p>
          <p className="muted text-sm">{this.state.error.message}</p>
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={() => {
              this.setState({ error: null })
              this.props.onReset?.()
            }}
          >
            Thử lại
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
