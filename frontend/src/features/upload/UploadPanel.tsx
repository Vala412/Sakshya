import { useState } from 'react';
import {
  ArrowRight,
  FileText,
  Fingerprint,
  ShieldCheck,
  Scales,
} from '@phosphor-icons/react';

import type { ApiError } from '@/api/types';
import { Button, Panel } from '@/components/ui';
import { Dropzone } from './Dropzone';

import styles from './upload.module.css';

export interface UploadSubmission {
  books: File;
  gstr2b: File;
  taxTolerance: string;
}

export interface UploadPanelProps {
  onSubmit: (submission: UploadSubmission) => void;
  running: boolean;
  /** Server-side error from the last attempt, if any. */
  error: ApiError | null;
}

/** Client-side validation, kept to what the browser can know for certain. */
interface LocalErrors {
  books?: string;
  gstr2b?: string;
  taxTolerance?: string;
}

function validate(
  books: File | null,
  gstr2b: File | null,
  tolerance: string,
): LocalErrors {
  const errors: LocalErrors = {};
  if (!books) errors.books = 'Select your purchase-register CSV export.';
  if (!gstr2b) errors.gstr2b = 'Select your GSTR-2B JSON export.';

  const trimmed = tolerance.trim();
  if (trimmed === '') {
    errors.taxTolerance = 'Enter a tolerance, or 0 for exact matching.';
  } else if (!/^\d+(\.\d+)?$/.test(trimmed)) {
    errors.taxTolerance = 'Enter a non-negative amount in rupees, e.g. 0 or 5.';
  }
  // Deliberately NOT enforcing GSTN's documented 0-10 range here. The server
  // accepts any non-negative value, and a client-side rule the API does not
  // share is exactly the kind of drift that makes a UI lie about what the
  // engine will do.
  return errors;
}

export function UploadPanel({ onSubmit, running, error }: UploadPanelProps) {
  const [books, setBooks] = useState<File | null>(null);
  const [gstr2b, setGstr2b] = useState<File | null>(null);
  const [taxTolerance, setTaxTolerance] = useState('0');
  const [localErrors, setLocalErrors] = useState<LocalErrors>({});
  const [submitted, setSubmitted] = useState(false);

  // Server-reported field errors merge with local ones. The server wins:
  // it saw the actual bytes, the client only saw a filename.
  const fieldErrors: LocalErrors = { ...localErrors };
  if (error?.field === 'books') fieldErrors.books = error.message;
  if (error?.field === 'gstr2b') fieldErrors.gstr2b = error.message;
  if (error?.field === 'tax_tolerance') fieldErrors.taxTolerance = error.message;

  function handleSubmit() {
    const errors = validate(books, gstr2b, taxTolerance);
    setLocalErrors(errors);
    setSubmitted(true);
    if (Object.keys(errors).length > 0 || !books || !gstr2b) return;
    onSubmit({ books, gstr2b, taxTolerance: taxTolerance.trim() });
  }

  // Re-validate as the user fixes things, but only after a first attempt --
  // showing errors before anyone has tried to submit is hostile.
  function revalidate(next: {
    books?: File | null;
    gstr2b?: File | null;
    taxTolerance?: string;
  }) {
    if (!submitted) return;
    setLocalErrors(
      validate(
        next.books !== undefined ? next.books : books,
        next.gstr2b !== undefined ? next.gstr2b : gstr2b,
        next.taxTolerance !== undefined ? next.taxTolerance : taxTolerance,
      ),
    );
  }

  return (
    <div className={styles.layout}>
      <div className={styles.lede}>
        <h1 className={styles.headline}>
          Prove every claimed rupee.{' '}
          <span className={styles.headlineAccent}>Not just match them.</span>
        </h1>
        <p className={styles.sub}>
          Reconcile your purchase register against GSTR-2B and get an
          audit-defensible working paper: an ITC bridge that ties to nil, and
          every exception traced back to the line it came from.
        </p>

        <div className={styles.credentials}>
          <div className={styles.credential}>
            <Scales size={16} className={styles.credentialIcon} weight="duotone" />
            <p className={styles.credentialText}>
              <strong>GSTN&rsquo;s own taxonomy.</strong> Six match categories
              and seven parameters, with tolerance applied per tax head — never
              on the summed total.
            </p>
          </div>
          <div className={styles.credential}>
            <Fingerprint size={16} className={styles.credentialIcon} weight="duotone" />
            <p className={styles.credentialText}>
              <strong>Reproducible by construction.</strong> Both inputs are
              SHA-256 hashed and the output order is deterministic across runs.
            </p>
          </div>
          <div className={styles.credential}>
            <ShieldCheck size={16} className={styles.credentialIcon} weight="duotone" />
            <p className={styles.credentialText}>
              <strong>Nothing leaves this machine.</strong> The engine is fully
              deterministic — no model, no vector store, no network call.
            </p>
          </div>
        </div>
      </div>

      <Panel
        title="Run a reconciliation"
        subtitle="Both exports are required."
      >
        {running ? (
          <RunningState booksName={books?.name} gstr2bName={gstr2b?.name} />
        ) : (
          <>
            <div className={styles.fields}>
              <Dropzone
                label="Books — purchase register"
                hint="Tally CSV export. Drop it here or browse."
                accept=".csv,text/csv"
                file={books}
                error={fieldErrors.books}
                onSelect={(file) => {
                  setBooks(file);
                  revalidate({ books: file });
                }}
              />
              <Dropzone
                label="GSTR-2B"
                hint="JSON export from the GST portal."
                accept=".json,application/json"
                file={gstr2b}
                error={fieldErrors.gstr2b}
                onSelect={(file) => {
                  setGstr2b(file);
                  revalidate({ gstr2b: file });
                }}
              />

              <div className={styles.toleranceRow}>
                <div className={styles.field}>
                  <label className={styles.fieldLabel} htmlFor="tax-tolerance">
                    Tax tolerance (₹ per head)
                  </label>
                  <input
                    id="tax-tolerance"
                    className={styles.input}
                    inputMode="decimal"
                    value={taxTolerance}
                    aria-invalid={Boolean(fieldErrors.taxTolerance)}
                    aria-describedby="tax-tolerance-help"
                    onChange={(event) => {
                      setTaxTolerance(event.target.value);
                      revalidate({ taxTolerance: event.target.value });
                    }}
                  />
                  <p className={styles.fieldHelp} id="tax-tolerance-help">
                    Applied to IGST, CGST, SGST and CESS individually. GSTN&rsquo;s
                    Matching Offline Tool allows 0&ndash;10.
                  </p>
                </div>
              </div>

              {fieldErrors.taxTolerance ? (
                <p className={styles.fieldError} role="alert">
                  {fieldErrors.taxTolerance}
                </p>
              ) : null}
            </div>

            <div className={styles.submitRow}>
              <span className={styles.submitNote}>
                <FileText size={14} weight="duotone" />
                Produces a three-sheet .xlsx working paper
              </span>
              <Button variant="primary" onClick={handleSubmit}>
                Reconcile
                <ArrowRight size={15} weight="bold" />
              </Button>
            </div>
          </>
        )}
      </Panel>
    </div>
  );
}

/**
 * In-flight view.
 *
 * Shows an indeterminate sweep, not a progress bar. The engine runs
 * ingestion, matching, classification, and the bridge in a single
 * server-side pass and reports nothing until it finishes, so any percentage
 * shown here would be invented. A fake progress bar on a financial tool is
 * a small lie in exactly the place trust is being established.
 */
function RunningState({
  booksName,
  gstr2bName,
}: {
  booksName?: string | undefined;
  gstr2bName?: string | undefined;
}) {
  return (
    <div className={styles.running} aria-live="polite">
      <div className={styles.scanFile}>
        <FileText size={16} weight="duotone" style={{ color: 'var(--text-3)' }} />
        <span className={styles.scanName}>{booksName ?? 'books.csv'}</span>
      </div>
      <div className={styles.scanFile}>
        <FileText size={16} weight="duotone" style={{ color: 'var(--text-3)' }} />
        <span className={styles.scanName}>{gstr2bName ?? 'gstr2b.json'}</span>
      </div>
      <p className={styles.scanStatus}>
        <span className={styles.scanDots} aria-hidden="true">
          <span className={styles.scanDot} />
          <span className={styles.scanDot} />
          <span className={styles.scanDot} />
        </span>
        Matching documents and classifying exceptions
      </p>
    </div>
  );
}
