import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  override state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("JARVIS UI crashed:", error, info);
  }

  override render() {
    if (this.state.error) {
      return (
        <div className="min-h-screen bg-surface-deep text-light flex items-center justify-center p-6">
          <div className="max-w-lg w-full rounded-xl border border-status-error/40 bg-status-error/10 p-6 space-y-3">
            <h1 className="text-lg font-semibold text-status-error">
              Something went wrong
            </h1>
            <p className="text-sm text-surface-panel">
              The interface hit an error instead of going blank. Details:
            </p>
            <pre className="text-xs text-light bg-surface-deep rounded p-3 overflow-auto max-h-48 whitespace-pre-wrap">
              {this.state.error.message}
              {"\n"}
              {this.state.error.stack ?? ""}
            </pre>
            <button
              type="button"
              onClick={() => {
                this.setState({ error: null });
                window.location.reload();
              }}
              className="rounded-lg bg-accent-cyan/20 text-accent-cyan px-4 py-2 text-sm font-medium hover:bg-accent-cyan/30"
            >
              Reload
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
