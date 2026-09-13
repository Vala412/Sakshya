import type { ReactNode } from 'react';

import type { RunMetadata } from '@/api/types';
import { Badge } from '@/components/ui';
import { formatTimestamp } from '@/lib/money';

import styles from './results.module.css';

/**
 * The reproducibility record, mirroring the working paper's third sheet.
 *
 * Surfacing the input hashes in the UI is the point rather than a detail:
 * it is what lets a reviewer confirm that the screen in front of them was
 * produced from the file they think it was. Hashes are shown in full, not
 * truncated -- a prefix is enough to recognise a hash but not enough to
 * verify one, and verification is the only reason it is here.
 */
export function ReproducibilityPanel({ metadata }: { metadata: RunMetadata }) {
  const rows: Array<{ key: string; value: ReactNode }> = [
    { key: 'Engine version', value: metadata.gstrecon_version },
    { key: 'Generated at (UTC)', value: formatTimestamp(metadata.generated_at) },
    { key: 'Books file', value: metadata.books_filename },
    {
      key: 'Books SHA-256',
      value: <span className={styles.hashValue}>{metadata.books_sha256}</span>,
    },
    { key: 'GSTR-2B file', value: metadata.gstr2b_filename },
    {
      key: 'GSTR-2B SHA-256',
      value: <span className={styles.hashValue}>{metadata.gstr2b_sha256}</span>,
    },
    {
      key: 'Tax tolerance',
      value: `₹${metadata.tax_tolerance} per head (IGST, CGST, SGST, CESS individually)`,
    },
    {
      key: 'Invoice fuzzy threshold',
      value: String(metadata.invoice_fuzzy_threshold),
    },
    {
      key: 'GSTIN fuzzy threshold',
      value: String(metadata.gstin_fuzzy_threshold),
    },
  ];

  return (
    <div>
      <div className={styles.repro}>
        {rows.map((row) => (
          <div className={styles.reproRow} key={row.key}>
            <span className={styles.reproKey}>{row.key}</span>
            <span className={styles.reproValue}>{row.value}</span>
          </div>
        ))}
      </div>
      <p className={styles.reproNote}>
        <Badge tone="neutral" mono>
          Deterministic
        </Badge>{' '}
        Re-running the engine on the same two files with the same settings
        produces byte-identical output, including row order.
      </p>
    </div>
  );
}
