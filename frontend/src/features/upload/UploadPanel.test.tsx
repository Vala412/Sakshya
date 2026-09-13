import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { ApiError } from '@/api/types';
import { UploadPanel } from './UploadPanel';

function setup(error: ApiError | null = null, running = false) {
  const onSubmit = vi.fn();
  render(<UploadPanel onSubmit={onSubmit} running={running} error={error} />);
  return { onSubmit, user: userEvent.setup() };
}

const booksFile = () =>
  new File(['Date,GSTIN\n'], 'books.csv', { type: 'text/csv' });
const gstr2bFile = () =>
  new File(['{}'], 'gstr2b.json', { type: 'application/json' });

function booksInput() {
  return screen.getByLabelText(/Books — purchase register/) as HTMLInputElement;
}
function gstr2bInput() {
  return screen.getByLabelText(/^GSTR-2B$/) as HTMLInputElement;
}

describe('validation', () => {
  it('does not shout before the user has tried anything', () => {
    setup();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('names both missing files on submit, and does not call the API', async () => {
    const { onSubmit, user } = setup();

    await user.click(screen.getByRole('button', { name: /Reconcile/ }));

    expect(onSubmit).not.toHaveBeenCalled();
    expect(
      screen.getByText('Select your purchase-register CSV export.'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Select your GSTR-2B JSON export.'),
    ).toBeInTheDocument();
  });

  it('clears a field error once that field is fixed', async () => {
    const { user } = setup();
    await user.click(screen.getByRole('button', { name: /Reconcile/ }));

    await user.upload(booksInput(), booksFile());

    expect(
      screen.queryByText('Select your purchase-register CSV export.'),
    ).not.toBeInTheDocument();
    // The other field's error must survive -- fixing one input should not
    // wipe feedback about the one still outstanding.
    expect(
      screen.getByText('Select your GSTR-2B JSON export.'),
    ).toBeInTheDocument();
  });

  it.each(['abc', '-1', ''])('rejects %o as a tolerance', async (value) => {
    const { onSubmit, user } = setup();
    await user.upload(booksInput(), booksFile());
    await user.upload(gstr2bInput(), gstr2bFile());

    const tolerance = screen.getByLabelText(/Tax tolerance/);
    await user.clear(tolerance);
    if (value) await user.type(tolerance, value);
    await user.click(screen.getByRole('button', { name: /Reconcile/ }));

    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('submits both files and the trimmed tolerance once valid', async () => {
    const { onSubmit, user } = setup();

    await user.upload(booksInput(), booksFile());
    await user.upload(gstr2bInput(), gstr2bFile());
    const tolerance = screen.getByLabelText(/Tax tolerance/);
    await user.clear(tolerance);
    await user.type(tolerance, '5');
    await user.click(screen.getByRole('button', { name: /Reconcile/ }));

    expect(onSubmit).toHaveBeenCalledOnce();
    const submission = onSubmit.mock.calls[0]![0];
    expect(submission.books.name).toBe('books.csv');
    expect(submission.gstr2b.name).toBe('gstr2b.json');
    expect(submission.taxTolerance).toBe('5');
  });

  it('accepts a decimal tolerance', async () => {
    const { onSubmit, user } = setup();
    await user.upload(booksInput(), booksFile());
    await user.upload(gstr2bInput(), gstr2bFile());
    const tolerance = screen.getByLabelText(/Tax tolerance/);
    await user.clear(tolerance);
    await user.type(tolerance, '0.50');
    await user.click(screen.getByRole('button', { name: /Reconcile/ }));

    expect(onSubmit).toHaveBeenCalledOnce();
  });
});

describe('server-reported errors', () => {
  it('attaches a books error to the books dropzone', () => {
    setup({
      kind: 'validation',
      code: 'invalid_books_file',
      message: "Missing expected field 'GSTIN' at row 4",
      field: 'books',
      status: 422,
    });

    expect(
      screen.getByText("Missing expected field 'GSTIN' at row 4"),
    ).toBeInTheDocument();
    expect(booksInput()).toHaveAttribute('aria-invalid', 'true');
    expect(gstr2bInput()).toHaveAttribute('aria-invalid', 'false');
  });

  it('attaches a GSTR-2B error to the GSTR-2B dropzone', () => {
    setup({
      kind: 'validation',
      code: 'invalid_gstr2b_file',
      message: 'Expecting value: line 1 column 3',
      field: 'gstr2b',
      status: 422,
    });

    expect(gstr2bInput()).toHaveAttribute('aria-invalid', 'true');
    expect(booksInput()).toHaveAttribute('aria-invalid', 'false');
  });

  it('associates the message with its input for screen readers', () => {
    setup({
      kind: 'validation',
      code: 'invalid_books_file',
      message: 'Bad column',
      field: 'books',
      status: 422,
    });

    const describedBy = booksInput().getAttribute('aria-describedby');
    expect(describedBy).toBeTruthy();
    expect(document.getElementById(describedBy!)).toHaveTextContent('Bad column');
  });
});

describe('running state', () => {
  it('replaces the form with an honest indeterminate indicator', () => {
    setup(null, true);

    expect(
      screen.queryByRole('button', { name: /Reconcile/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(/Matching documents and classifying exceptions/),
    ).toBeInTheDocument();
    // Deliberately no percentage anywhere: the engine reports nothing until
    // it finishes, so any number shown would be invented.
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });

  it('announces the change politely rather than silently swapping', () => {
    const { container } = render(
      <UploadPanel onSubmit={vi.fn()} running error={null} />,
    );
    expect(container.querySelector('[aria-live="polite"]')).toBeTruthy();
  });
});
