"use client";

import { Component, type ReactNode } from "react";

type Props = { children: ReactNode; fallback?: ReactNode };
type State = { error: Error | null };

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        this.props.fallback ?? (
          <div className="grid h-full min-h-[200px] place-items-center rounded-lg border border-red-200 bg-red-50 p-6 text-center dark:border-red-800 dark:bg-red-950">
            <div>
              <h2 className="text-sm font-semibold text-red-900 dark:text-red-300">Something went wrong</h2>
              <p className="mt-1 text-xs text-red-700 dark:text-red-400">{this.state.error.message}</p>
              <button
                type="button"
                onClick={() => window.location.reload()}
                className="mt-3 rounded-md border border-red-300 px-3 py-1 text-xs font-medium text-red-900 hover:bg-red-100 dark:border-red-700 dark:text-red-300 dark:hover:bg-red-900"
              >
                Try again
              </button>
            </div>
          </div>
        )
      );
    }
    return this.props.children;
  }
}
