/**
 * Server state for the one long-running operation this app performs.
 *
 * Deliberately a hook over `useState` rather than a data-fetching library:
 * there is exactly one mutation and one small reference query here, neither
 * is cached, refetched, paginated, or shared across routes. Adding React
 * Query for this would be ~13 kB and a second mental model for no behaviour
 * we would actually use.
 *
 * The UI state (which finding is open, which filters are set) deliberately
 * does NOT live here -- it belongs to the components that own it.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { ApiRequestError, isAbort, reconcile } from '@/api/client';
import type { ApiError, Reconciliation } from '@/api/types';

/**
 * Explicit finite states. The spec calls for initial / loading / success /
 * empty / validation-failure / backend-failure to all be distinguishable;
 * modelling them as a union rather than three booleans makes the impossible
 * combinations (loading AND error) unrepresentable.
 */
export type ReconciliationState =
  | { status: 'idle' }
  | { status: 'running' }
  | { status: 'success'; data: Reconciliation }
  | { status: 'error'; error: ApiError };

export interface UseReconciliation {
  state: ReconciliationState;
  run: (input: { books: File; gstr2b: File; taxTolerance: string }) => void;
  reset: () => void;
}

export function useReconciliation(): UseReconciliation {
  const [state, setState] = useState<ReconciliationState>({ status: 'idle' });
  const controller = useRef<AbortController | null>(null);

  // Abort any in-flight reconciliation if the component unmounts, so a
  // late response cannot call setState on a dead component.
  useEffect(() => () => controller.current?.abort(), []);

  const run = useCallback(
    ({
      books,
      gstr2b,
      taxTolerance,
    }: {
      books: File;
      gstr2b: File;
      taxTolerance: string;
    }) => {
      // Supersede an in-flight run rather than queueing: the user pressing
      // reconcile again means they want the new inputs, not both.
      controller.current?.abort();
      const next = new AbortController();
      controller.current = next;
      setState({ status: 'running' });

      reconcile({ books, gstr2b, taxTolerance, signal: next.signal })
        .then((data) => {
          if (next.signal.aborted) return;
          setState({ status: 'success', data });
        })
        .catch((error: unknown) => {
          // A superseded request is not a failure the user should see.
          if (isAbort(error) || next.signal.aborted) return;
          setState({
            status: 'error',
            error:
              error instanceof ApiRequestError
                ? error.detail
                : {
                    kind: 'unknown',
                    code: 'unexpected',
                    message:
                      'Something went wrong in this app while handling the response.',
                    field: null,
                    status: null,
                  },
          });
        });
    },
    [],
  );

  const reset = useCallback(() => {
    controller.current?.abort();
    setState({ status: 'idle' });
  }, []);

  return { state, run, reset };
}
