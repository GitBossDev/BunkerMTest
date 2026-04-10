'use client'

import { Component, type ReactNode } from 'react'

interface Props {
  children: ReactNode
  // Componente opcional para renderizar en caso de error
  fallback?: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

// Captura errores de renderizado en el subárbol de componentes.
// Debe ser un class component: los hooks no pueden reemplazar componentDidCatch.
export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: { componentStack: string }): void {
    // Registra el error en consola; en producción se puede reemplazar por un
    // servicio de monitoreo (Sentry, Datadog, etc.)
    console.error('[ErrorBoundary] Unhandled render error:', error, info.componentStack)
  }

  render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback
      }

      return (
        <div className="flex min-h-screen items-center justify-center p-8">
          <div className="max-w-md rounded-lg border border-destructive/30 bg-destructive/5 p-6 text-center">
            <h2 className="mb-2 text-lg font-semibold text-destructive">
              Something went wrong
            </h2>
            <p className="mb-4 text-sm text-muted-foreground">
              An unexpected error occurred. Reload the page to try again.
            </p>
            <button
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
              onClick={() => this.setState({ hasError: false, error: null })}
            >
              Try again
            </button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
