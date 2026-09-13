import { Moon, Sun } from '@phosphor-icons/react';

import type { ApiError } from '@/api/types';
import { Button, ErrorState } from '@/components/ui';
import { ResultsView } from '@/features/results/ResultsView';
import { UploadPanel } from '@/features/upload/UploadPanel';
import { useReconciliation } from '@/lib/useReconciliation';
import { useTheme } from '@/lib/useTheme';

import styles from './app.module.css';

/**
 * Which failures belong on the form, and which take over the page.
 *
 * A field-scoped validation error (a malformed CSV, a bad tolerance) stays
 * inline next to the control that caused it, because the user's next action
 * is to fix that control. A dropped connection or a 500 has no control to
 * attach to, so it replaces the view and offers a retry.
 */
function isFieldScoped(error: ApiError): boolean {
  return error.kind === 'validation' && error.field !== null;
}

export function App() {
  const { theme, toggle } = useTheme();
  const { state, run, reset } = useReconciliation();

  const error = state.status === 'error' ? state.error : null;
  const pageLevelError = error && !isFieldScoped(error) ? error : null;

  return (
    <div className={styles.shell}>
      <a className="skip-link" href="#main">
        Skip to content
      </a>

      <header className={styles.header}>
        <div className={`${styles.container} ${styles.headerInner}`}>
          <div className={styles.brand}>
            <span className={styles.wordmark}>Sakshya</span>
            <span className={styles.wordmarkGloss}>
              साक्ष्य &middot; evidence
            </span>
          </div>
          <div className={styles.headerActions}>
            <Button
              variant="ghost"
              iconOnly
              onClick={toggle}
              aria-label={
                theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'
              }
            >
              {theme === 'dark' ? (
                <Sun size={16} weight="duotone" />
              ) : (
                <Moon size={16} weight="duotone" />
              )}
            </Button>
          </div>
        </div>
      </header>

      <main className={styles.main} id="main">
        <div className={styles.container}>
          {state.status === 'success' ? (
            <ResultsView data={state.data} onReset={reset} />
          ) : pageLevelError ? (
            <div className={styles.errorWrap}>
              <ErrorState
                title={
                  pageLevelError.kind === 'network'
                    ? 'Cannot reach the reconciliation server'
                    : pageLevelError.kind === 'server'
                      ? 'The engine failed while reconciling'
                      : 'Something went wrong'
                }
                body={pageLevelError.message}
                hint={
                  pageLevelError.kind === 'network'
                    ? 'make api    # or: uv run uvicorn gstrecon.api.main:app --port 8000'
                    : undefined
                }
                onRetry={reset}
              />
            </div>
          ) : (
            <UploadPanel
              onSubmit={run}
              running={state.status === 'running'}
              error={error}
            />
          )}
        </div>
      </main>

      <footer className={styles.footer}>
        <div className={`${styles.container} ${styles.footerInner}`}>
          <span>
            Deterministic engine — no model, no vector store, no network call.
          </span>
          <span>
            Matching follows GSTN&rsquo;s six-category, seven-parameter scheme.
          </span>
        </div>
      </footer>
    </div>
  );
}
