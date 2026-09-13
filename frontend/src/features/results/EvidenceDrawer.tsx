import { useEffect, useRef } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import { ArrowsLeftRight, X } from '@phosphor-icons/react';

import type { ApiDocument, Finding, GstnParameter } from '@/api/types';
import { Badge, Button, SeverityBadge } from '@/components/ui';
import { cx } from '@/lib/cx';
import { formatAmount, formatDate } from '@/lib/money';
import {
  DOC_TYPE_LABEL,
  MATCH_CATEGORY_LABEL,
  PARAMETER_LABEL,
  presentReasonCode,
} from '@/lib/reasonCodes';

import styles from './results.module.css';

/**
 * The evidence trail for one finding.
 *
 * This is the component that makes the tool defensible rather than merely
 * informative: it puts the books row and the GSTR-2B row side by side and
 * marks exactly which of GSTN's seven parameters disagreed, using the
 * parameter list the engine emitted. Nothing here is recomputed in the
 * browser -- if the drawer highlighted a field it decided looked different,
 * it could disagree with the classifier that raised the finding.
 */

interface ComparisonRow {
  /** Present when this row corresponds to an official GSTN parameter. */
  parameter: GstnParameter | null;
  label: string;
  books: string | null;
  gstr2b: string | null;
  /** Indented under the head-wise row. */
  nested?: boolean;
}

function value<T>(doc: ApiDocument | null, read: (d: ApiDocument) => T): T | null {
  return doc ? read(doc) : null;
}

function buildRows(finding: Finding): ComparisonRow[] {
  const books = finding.books_doc;
  const gstr2b = finding.gstr2b_doc;

  return [
    {
      parameter: 'gstin',
      label: PARAMETER_LABEL.gstin,
      books: value(books, (d) => d.supplier_gstin),
      gstr2b: value(gstr2b, (d) => d.supplier_gstin),
    },
    {
      parameter: 'document_type',
      label: PARAMETER_LABEL.document_type,
      books: value(books, (d) => DOC_TYPE_LABEL[d.doc_type] ?? d.doc_type),
      gstr2b: value(gstr2b, (d) => DOC_TYPE_LABEL[d.doc_type] ?? d.doc_type),
    },
    {
      parameter: 'document_number',
      label: PARAMETER_LABEL.document_number,
      books: value(books, (d) => d.invoice_number),
      gstr2b: value(gstr2b, (d) => d.invoice_number),
    },
    {
      parameter: 'document_date',
      label: PARAMETER_LABEL.document_date,
      books: value(books, (d) => formatDate(d.invoice_date)),
      gstr2b: value(gstr2b, (d) => formatDate(d.invoice_date)),
    },
    {
      parameter: 'taxable_value',
      label: PARAMETER_LABEL.taxable_value,
      books: value(books, (d) => formatAmount(d.taxable_value)),
      gstr2b: value(gstr2b, (d) => formatAmount(d.taxable_value)),
    },
    {
      parameter: 'total_tax_amount',
      label: PARAMETER_LABEL.total_tax_amount,
      books: value(books, (d) => formatAmount(d.tax.total)),
      gstr2b: value(gstr2b, (d) => formatAmount(d.tax.total)),
    },
    // The four heads are shown individually beneath the head-wise parameter
    // because that is how GSTN checks them -- per head, never on the sum.
    // Collapsing them would hide exactly what an EX-05 is about.
    {
      parameter: 'tax_amount_head_wise',
      label: PARAMETER_LABEL.tax_amount_head_wise,
      books: null,
      gstr2b: null,
    },
    ...(['igst', 'cgst', 'sgst', 'cess'] as const).map((head) => ({
      parameter: null,
      label: head.toUpperCase(),
      books: value(books, (d) => formatAmount(d.tax[head])),
      gstr2b: value(gstr2b, (d) => formatAmount(d.tax[head])),
      nested: true,
    })),
    {
      parameter: null,
      label: 'ITC availability',
      books: value(books, () => '—'),
      gstr2b: value(gstr2b, (d) =>
        d.itc_availability === 'N'
          ? 'Not available'
          : d.itc_availability === 'Y'
            ? 'Available'
            : '—',
      ),
    },
    {
      parameter: null,
      label: 'Return period',
      books: value(books, (d) => d.return_period ?? '—'),
      gstr2b: value(gstr2b, (d) => d.return_period ?? '—'),
    },
    {
      parameter: null,
      label: 'Source row',
      books: value(books, (d) => d.row_ref),
      gstr2b: value(gstr2b, (d) => d.row_ref),
    },
  ];
}

export function EvidenceDrawer({
  finding,
  onClose,
}: {
  finding: Finding | null;
  onClose: () => void;
}) {
  const reduceMotion = useReducedMotion();
  const closeRef = useRef<HTMLButtonElement>(null);
  // Where focus was before the drawer opened, so it can be handed back.
  const restoreTo = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!finding) return;
    restoreTo.current = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose();
    }
    document.addEventListener('keydown', onKeyDown);
    // Freeze the page behind the drawer: scrolling the register while a
    // drawer covers it is disorienting and loses the reader's place.
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    return () => {
      document.removeEventListener('keydown', onKeyDown);
      document.body.style.overflow = previousOverflow;
      restoreTo.current?.focus();
    };
  }, [finding, onClose]);

  return (
    <AnimatePresence>
      {finding ? (
        <>
          <motion.div
            className={styles.scrim}
            onClick={onClose}
            initial={reduceMotion ? false : { opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: reduceMotion ? 0 : 0.18 }}
          />
          <motion.aside
            className={styles.drawer}
            role="dialog"
            aria-modal="true"
            aria-label={`Evidence for ${finding.reason_code}`}
            initial={reduceMotion ? false : { x: '100%' }}
            animate={{ x: 0 }}
            exit={reduceMotion ? { opacity: 0 } : { x: '100%' }}
            transition={
              reduceMotion
                ? { duration: 0 }
                : { type: 'spring', stiffness: 380, damping: 38, mass: 0.9 }
            }
          >
            <DrawerContents
              finding={finding}
              onClose={onClose}
              closeRef={closeRef}
            />
          </motion.aside>
        </>
      ) : null}
    </AnimatePresence>
  );
}

function DrawerContents({
  finding,
  onClose,
  closeRef,
}: {
  finding: Finding;
  onClose: () => void;
  closeRef: React.RefObject<HTMLButtonElement>;
}) {
  const presentation = presentReasonCode(finding.reason_code);
  const rows = buildRows(finding);
  const mismatched = new Set<GstnParameter>(finding.mismatched_parameters);
  const bothSides = Boolean(finding.books_doc && finding.gstr2b_doc);

  return (
    <>
      <header className={styles.drawerHeader}>
        <div>
          <div className={styles.drawerMeta}>
            <SeverityBadge severity={finding.severity} />
            <Badge tone="neutral" mono>
              {finding.reason_code}
            </Badge>
            <Badge tone="neutral">
              {MATCH_CATEGORY_LABEL[finding.match_category]}
            </Badge>
          </div>
          <h2 className={styles.drawerTitle}>{presentation.title}</h2>
        </div>
        <Button
          ref={closeRef}
          variant="ghost"
          iconOnly
          onClick={onClose}
          aria-label="Close evidence"
        >
          <X size={16} weight="bold" />
        </Button>
      </header>

      <div className={styles.drawerBody}>
        <section className={styles.drawerSection}>
          <h3 className={styles.drawerSectionTitle}>What this means</h3>
          <p className={styles.drawerProse}>{presentation.meaning}</p>
          <p className={styles.actionCallout}>{presentation.action}</p>
        </section>

        {mismatched.size > 0 ? (
          <section className={styles.drawerSection}>
            <h3 className={styles.drawerSectionTitle}>
              Parameters that disagreed
            </h3>
            <div className={styles.paramList}>
              {finding.mismatched_parameters.map((parameter) => (
                <Badge key={parameter} tone="high">
                  {PARAMETER_LABEL[parameter] ?? parameter}
                </Badge>
              ))}
            </div>
            <p className={styles.drawerProse}>
              Named from GSTN&rsquo;s own seven matching parameters, so this
              cites the official parameter rather than a label invented here.
            </p>
          </section>
        ) : null}

        <section className={styles.drawerSection}>
          <h3 className={styles.drawerSectionTitle}>
            {bothSides ? 'Books against GSTR-2B' : 'Document detail'}
          </h3>

          <div className={styles.compare}>
            <div className={styles.compareHead}>
              <span className={styles.compareHeadCell}>Parameter</span>
              <span className={styles.compareHeadCell}>Books</span>
              <span className={styles.compareHeadCell}>GSTR-2B</span>
            </div>

            {rows.map((row) => {
              const differs = row.parameter
                ? mismatched.has(row.parameter)
                : false;
              return (
                <div
                  key={row.label}
                  className={cx(
                    styles.compareRow,
                    differs && styles.compareRowDiff,
                  )}
                >
                  <span
                    className={cx(
                      styles.compareKey,
                      row.nested && styles.compareKeyNested,
                      differs && styles.compareKeyDiff,
                    )}
                    
                  >
                    {/* A glyph as well as the tint: the diff must survive a
                        greyscale print of the working paper. */}
                    {differs ? (
                      <ArrowsLeftRight size={11} weight="bold" aria-hidden="true" />
                    ) : null}
                    {row.label}
                  </span>
                  <Cell value={row.books} differs={differs} side="Books" divider />
                  <Cell value={row.gstr2b} differs={differs} side="GSTR-2B" />
                </div>
              );
            })}
          </div>
        </section>

        <section className={styles.drawerSection}>
          <h3 className={styles.drawerSectionTitle}>Evidence trail</h3>
          <p className={styles.evidenceString}>{finding.evidence}</p>
          <p className={styles.drawerProse}>
            Reproduced verbatim from the working paper, so this screen and the
            .xlsx cite the same provenance.
          </p>
        </section>
      </div>
    </>
  );
}

function Cell({
  value,
  differs,
  side,
  divider = false,
}: {
  value: string | null;
  differs: boolean;
  /** Which ledger this column is. Surfaced as a prefix once the columns
   * stack on narrow screens, where position alone no longer says which. */
  side: string;
  divider?: boolean;
}) {
  return (
    <span
      data-side={side}
      className={cx(
        styles.compareValue,
        divider && styles.compareDivider,
        value === null && styles.compareValueMissing,
        differs && value !== null && styles.compareValueDiff,
      )}
    >
      {/* An orphan finding has no counterpart, and saying so explicitly is
          the whole point of EX-01/EX-02 -- a blank cell would read as
          missing data rather than as the finding itself. */}
      {value ?? 'not present'}
    </span>
  );
}
