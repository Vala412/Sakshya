/**
 * The single place this app talks HTTP.
 *
 * No component calls `fetch` directly. Everything goes through here so that
 * error normalisation, the base URL, and the abort contract exist once
 * rather than being re-implemented (slightly differently) at each call site.
 */

import type {
  ApiError,
  ErrorField,
  Reconciliation,
  ReasonCode,
} from './types';

/**
 * Same-origin. In development Vite proxies `/api` to uvicorn on :8000 (see
 * vite.config.ts), so there is no environment-dependent base URL and no
 * chance of shipping a hardcoded localhost address to production.
 */
const BASE = '/api';

const ERROR_FIELDS: ReadonlySet<string> = new Set([
  'books',
  'gstr2b',
  'tax_tolerance',
]);

function toErrorField(value: unknown): ErrorField | null {
  return typeof value === 'string' && ERROR_FIELDS.has(value)
    ? (value as ErrorField)
    : null;
}

function kindForStatus(status: number): ApiError['kind'] {
  if (status === 404) return 'not_found';
  if (status === 400 || status === 413 || status === 422) return 'validation';
  if (status >= 500) return 'server';
  return 'unknown';
}

/**
 * Build an ApiError from a non-OK response.
 *
 * The body is treated as untrusted: the server's own envelope is the happy
 * path, but a proxy error page or an HTML 502 must not throw while we are
 * already handling a failure. Anything unparseable degrades to a generic
 * message carrying the real status.
 */
async function toApiError(response: Response): Promise<ApiError> {
  const status = response.status;
  const fallback: ApiError = {
    kind: kindForStatus(status),
    code: 'request_failed',
    message: `The server responded with ${status}.`,
    field: null,
    status,
  };

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    return fallback;
  }
  if (typeof body !== 'object' || body === null) return fallback;

  const envelope = body as Record<string, unknown>;
  return {
    kind: kindForStatus(status),
    code: typeof envelope.error === 'string' ? envelope.error : fallback.code,
    message:
      typeof envelope.message === 'string' && envelope.message.trim()
        ? envelope.message
        : fallback.message,
    field: toErrorField(envelope.field),
    status,
  };
}

/** A thrown ApiError. Carries the normalised shape rather than a string. */
export class ApiRequestError extends Error {
  readonly detail: ApiError;

  constructor(detail: ApiError) {
    super(detail.message);
    this.name = 'ApiRequestError';
    this.detail = detail;
  }
}

function networkError(cause: unknown): ApiRequestError {
  // An aborted request is the user navigating away or re-submitting, not a
  // failure worth showing. Callers check `isAbort` and drop it silently.
  const aborted = cause instanceof DOMException && cause.name === 'AbortError';
  return new ApiRequestError({
    kind: 'network',
    code: aborted ? 'aborted' : 'network_error',
    message: aborted
      ? 'Request cancelled.'
      : 'Could not reach the reconciliation server. Is it running on port 8000?',
    field: null,
    status: null,
  });
}

export function isAbort(error: unknown): boolean {
  return error instanceof ApiRequestError && error.detail.code === 'aborted';
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, init);
  } catch (cause) {
    throw networkError(cause);
  }

  if (!response.ok) throw new ApiRequestError(await toApiError(response));

  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiRequestError({
      kind: 'unknown',
      code: 'malformed_response',
      message: 'The server returned a response this app could not read.',
      field: null,
      status: response.status,
    });
  }
}

export interface ReconcileInput {
  books: File;
  gstr2b: File;
  taxTolerance: string;
  signal?: AbortSignal;
}

export function reconcile({
  books,
  gstr2b,
  taxTolerance,
  signal,
}: ReconcileInput): Promise<Reconciliation> {
  const form = new FormData();
  form.append('books', books);
  form.append('gstr2b', gstr2b);
  form.append('tax_tolerance', taxTolerance);
  // No explicit Content-Type: the browser must set the multipart boundary
  // itself, and supplying the header manually omits it and breaks parsing.
  return request<Reconciliation>('/reconcile', {
    method: 'POST',
    body: form,
    ...(signal ? { signal } : {}),
  });
}

export function fetchReasonCodes(signal?: AbortSignal): Promise<ReasonCode[]> {
  return request<ReasonCode[]>('/reason-codes', signal ? { signal } : {});
}

/**
 * URL for the working paper belonging to a run.
 *
 * Returned as a plain href rather than fetched into a blob: letting the
 * browser handle the download keeps the Content-Disposition filename and
 * avoids holding a multi-megabyte xlsx in memory.
 */
export function workingPaperUrl(runId: string): string {
  return `${BASE}/runs/${encodeURIComponent(runId)}/working-paper`;
}
