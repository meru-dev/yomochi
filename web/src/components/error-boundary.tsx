"use client"
import { Component, type ErrorInfo, type ReactNode } from "react"

interface Props {
  fallback?: ReactNode
  fallbackRender?: (props: { error: Error }) => ReactNode
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("[ErrorBoundary]", error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallbackRender && this.state.error) {
        return this.props.fallbackRender({ error: this.state.error })
      }
      if (this.props.fallback) {
        return this.props.fallback
      }
      return (
        <div className="flex flex-col items-center justify-center min-h-[40vh] p-8 text-center">
          <p className="font-serif italic text-[22px] text-[var(--text-2)] max-w-[44ch] mb-4">
            Something went sideways here. The page failed to render.
          </p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="inline-flex items-center justify-center rounded-lg px-4 h-9 text-sm font-medium bg-[var(--accent)] text-[var(--fab-fg)] transition-opacity hover:opacity-80"
          >
            Try again
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
