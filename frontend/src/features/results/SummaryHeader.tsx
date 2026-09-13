import { SealCheck } from '@phosphor-icons/react';

import type { Reconciliation } from '@/api/types';
import { cx } from '@/lib/cx';
import { formatRupees, isZero } from '@/lib/money';

import styles from './results.module.css';

/**
 * Headline figures.
 *
 * Laid out as a divided band rather than a row of cards: at this density,
 * five bordered boxes each with its own shadow is noise. A 1px grid gap over
 * a border-coloured background gives the same separation for none of the
 * visual weight.
 */
export function SummaryHeader({ data }: { data: Reconciliation }) {
  const { summary, bridge } = data;
  const bySeverity = summary.findings_by_severity;
  const tiesToNil = isZero(bridge.closing_variance);

  const severityParts = (['high', 'medium', 'low'] as const)
    .map((level) => (bySeverity[level] ? `${bySeverity[level]} ${level}` : null))
    .filter(Boolean)
    .join(' · ');

  return (
    <div className={styles.summary}>
      <div className={styles.metric}>
        <span className={styles.metricLabel}>Books documents</span>
        <span className={cx(styles.metricValue, 'num')}>
          {summary.books_document_count}
        </span>
        <span className={styles.metricNote}>from your purchase register</span>
      </div>

      <div className={styles.metric}>
        <span className={styles.metricLabel}>GSTR-2B documents</span>
        <span className={cx(styles.metricValue, 'num')}>
          {summary.gstr2b_document_count}
        </span>
        <span className={styles.metricNote}>as filed by suppliers</span>
      </div>

      <div className={styles.metric}>
        <span className={styles.metricLabel}>Exceptions</span>
        <span className={cx(styles.metricValue, 'num')}>
          {summary.finding_count}
        </span>
        <span className={styles.metricNote}>
          {severityParts || 'none raised'}
        </span>
      </div>

      <div className={styles.metric}>
        <span className={styles.metricLabel}>ITC at risk</span>
        <span className={cx(styles.metricValue, 'num')}>
          {formatRupees(summary.total_itc_at_risk)}
        </span>
        {/* This figure double-counts by design: one document can carry
            several findings. Saying so here is not a caveat for lawyers --
            a reader who subtracts it from their claim would be wrong, and
            the bridge below is the number that actually nets. */}
        <span className={styles.metricNote}>
          summed per finding, not per document
        </span>
      </div>

      <div className={cx(styles.metric, tiesToNil && styles.metricProof)}>
        <span className={styles.metricLabel}>
          {tiesToNil ? (
            <SealCheck size={13} weight="fill" style={{ color: 'var(--nil)' }} />
          ) : null}
          Closing variance
        </span>
        <span
          className={cx(
            styles.metricValue,
            'num',
            tiesToNil && styles.metricNil,
          )}
        >
          {formatRupees(bridge.closing_variance)}
        </span>
        <span className={styles.metricNote}>
          {tiesToNil ? 'bridge ties to nil' : 'does not tie — see bridge'}
        </span>
      </div>
    </div>
  );
}
