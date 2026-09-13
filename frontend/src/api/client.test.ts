import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  ApiRequestError,
  fetchReasonCodes,
  isAbort,
  reconcile,
  workingPaperUrl,
} from './client';

const file = (name: string, body = 'x') => new File([body], name);

function mockFetch(response: Partial<Response> & { json?: () => Promise<unknown> }) {
  return vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({}),
    ...response,
  } as Response);
}

beforeEach(() => {
  vi.stubGlobal('fetch', mockFetch({}));
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('error normalisation', () => {
  it('maps the API error envelope onto the client shape', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch({
        ok: false,
        status: 422,
        json: async () => ({
          error: 'invalid_books_file',
          message: "Missing expected column 'GSTIN'",
          field: 'books',
        }),
      }),
    );

    await expect(
      reconcile({ books: file('b.csv'), gstr2b: file('g.json'), taxTolerance: '0' }),
    ).rejects.toMatchObject({
      detail: {
        kind: 'validation',
        code: 'invalid_books_file',
        message: "Missing expected column 'GSTIN'",
        field: 'books',
        status: 422,
      },
    });
  });

  it.each([
    [400, 'validation'],
    [413, 'validation'],
    [422, 'validation'],
    [404, 'not_found'],
    [500, 'server'],
    [503, 'server'],
    [418, 'unknown'],
  ])('classifies HTTP %i as %s', async (status, kind) => {
    vi.stubGlobal(
      'fetch',
      mockFetch({ ok: false, status, json: async () => ({ error: 'x', message: 'y' }) }),
    );

    await expect(fetchReasonCodes()).rejects.toMatchObject({ detail: { kind } });
  });

  it('rejects an unknown field name rather than trusting it', async () => {
    // The field drives which dropzone shows the error. An arbitrary string
    // from the wire must not end up in that slot.
    vi.stubGlobal(
      'fetch',
      mockFetch({
        ok: false,
        status: 422,
        json: async () => ({ error: 'e', message: 'm', field: 'evil_field' }),
      }),
    );

    await expect(fetchReasonCodes()).rejects.toMatchObject({
      detail: { field: null },
    });
  });

  it('survives an error body that is not the expected envelope', async () => {
    // A proxy 502 returns HTML, not JSON. Throwing while handling a failure
    // would replace a useful message with an unhandled rejection.
    vi.stubGlobal(
      'fetch',
      mockFetch({
        ok: false,
        status: 502,
        json: async () => {
          throw new SyntaxError('Unexpected token <');
        },
      }),
    );

    await expect(fetchReasonCodes()).rejects.toMatchObject({
      detail: { kind: 'server', code: 'request_failed', status: 502 },
    });
  });

  it('falls back when the envelope carries an empty message', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch({ ok: false, status: 500, json: async () => ({ error: 'e', message: '  ' }) }),
    );

    await expect(fetchReasonCodes()).rejects.toMatchObject({
      detail: { message: 'The server responded with 500.' },
    });
  });

  it('reports an unreachable server with an actionable message', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));

    await expect(fetchReasonCodes()).rejects.toMatchObject({
      detail: {
        kind: 'network',
        code: 'network_error',
        message: expect.stringContaining('port 8000'),
      },
    });
  });

  it('distinguishes an abort from a real failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new DOMException('aborted', 'AbortError')),
    );

    const error = await fetchReasonCodes().catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiRequestError);
    expect(isAbort(error)).toBe(true);
  });

  it('flags a 200 whose body is not readable JSON', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch({
        ok: true,
        status: 200,
        json: async () => {
          throw new SyntaxError('bad json');
        },
      }),
    );

    await expect(fetchReasonCodes()).rejects.toMatchObject({
      detail: { code: 'malformed_response' },
    });
  });
});

describe('reconcile request', () => {
  it('posts multipart form data without setting Content-Type by hand', async () => {
    const spy = mockFetch({});
    vi.stubGlobal('fetch', spy);

    await reconcile({
      books: file('books.csv'),
      gstr2b: file('gstr2b.json'),
      taxTolerance: '5',
    });

    const [url, init] = spy.mock.calls[0]!;
    expect(url).toBe('/api/reconcile');
    expect(init.method).toBe('POST');
    expect(init.body).toBeInstanceOf(FormData);
    // Setting it manually omits the multipart boundary and breaks parsing
    // server-side; the browser must generate the header itself.
    expect(init.headers).toBeUndefined();

    const body = init.body as FormData;
    expect((body.get('books') as File).name).toBe('books.csv');
    expect(body.get('tax_tolerance')).toBe('5');
  });
});

describe('workingPaperUrl', () => {
  it('builds a same-origin download URL', () => {
    expect(workingPaperUrl('abc123')).toBe('/api/runs/abc123/working-paper');
  });

  it('encodes a run id rather than interpolating it raw', () => {
    expect(workingPaperUrl('a/../b')).toBe('/api/runs/a%2F..%2Fb/working-paper');
  });
});
