import { Component, ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: any) {
    console.error('Error caught by boundary:', error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: '20px', color: '#d32f2f', fontFamily: 'monospace' }}>
          <h2>❌ Something went wrong</h2>
          <details style={{ whiteSpace: 'pre-wrap', color: '#666' }}>
            {this.state.error?.toString()}
          </details>
        </div>
      )
    }

    return this.props.children
  }
}
