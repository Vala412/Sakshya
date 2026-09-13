import { motion, useReducedMotion } from 'motion/react';
import { SealCheck, WarningOctagon } from '@phosphor-icons/react';

import type { ItcBridge } from '@/api/types';
import { cx } from '@/lib/cx';
import {
  formatRupees,
  formatSigned,
  isZero,
  toNumberForLayout,
} from '@/lib/money';

import styles from './results.module.css';

/**
 * The ITC bridge, drawn as a waterfall.
 *
 * Why a waterfall and not a bar chart: the bridge is a running
 * decomposition -- books total, minus and plus a sequence of adjustments,
 * landing on the 2B total with nil left over. A bar chart would show the
 * same numbers as unrelated magnitudes and throw away the one property that
 * matters, which is that each step starts where the previous one ended.
 * Floating the bars at their running position is what makes "ties to nil"
 * something you can see rather than something the page asserts.
 *
 * Geometry is computed from parsed numbers; every *displayed* figure is
 * formatted from the original exact string. Parsing is for pixels only.
 */

interface Step {
  key: string;
  label: string;
  codes: string;
  count: number | null;
  /** Exact string, for display. */
  amount: string;
  kind: 'opening' | 'delta' | 'closing';
  /** Running position before and after this step, in rupees. Layout only. */
  start: number;
  end: number;
}

function buildSteps(bridge: ItcBridge): Step[] {
  const opening = toNumberForLayout(bridge.books_total);
  const steps: Step[] = [
    {
      key: 'opening',
      label: 'ITC as per books',
      codes: '',
      count: null,
      amount: bridge.books_total,
      kind: 'opening',
      start: 0,
      end: opening,
    },
  ];

  let running = opening;
  for (const [index, line] of bridge.lines.entries()) {
    const delta = toNumberForLayout(line.amount);
    const start = running;
    running += delta;
    steps.push({
      key: `line-${index}`,
      label: line.label,
      codes: line.reason_codes,
      count: line.document_count,
      amount: line.amount,
      kind: 'delta',
      start,
      end: running,
    });
  }

  steps.push({
    key: 'closing',
    label: 'ITC as per GSTR-2B (available)',
    codes: '',
    count: null,
    amount: bridge.gstr2b_total_available,
    kind: 'closing',
    start: 0,
    end: toNumberForLayout(bridge.gstr2b_total_available),
  });

  return steps;
}

export function ItcBridgeChart({ bridge }: { bridge: ItcBridge }) {
  const reduceMotion = useReducedMotion();
  const steps = buildSteps(bridge);

  // Scale to the largest running position so no bar overflows its track.
  // Guarded against a zero scale, which would make every width NaN%.
  const scale =
    Math.max(...steps.flatMap((step) => [Math.abs(step.start), Math.abs(step.end)]), 1) || 1;

  const tiesToNil = isZero(bridge.closing_variance);

  return (
    <div>
      <div className={styles.bridge}>
        {steps.map((step, index) => {
          const isTerminal = step.kind === 'closing';
          const low = Math.min(step.start, step.end);
          const high = Math.max(step.start, step.end);
          const left = (low / scale) * 100;
          const width = Math.max(((high - low) / scale) * 100, 0.4);
          const negative = step.end < step.start;

          return (
            <div
              key={step.key}
              className={cx(
                styles.bridgeRow,
                isTerminal && styles.bridgeRowTerminal,
              )}
            >
              <div className={styles.bridgeLabel}>
                <span
                  className={cx(
                    styles.bridgeLabelText,
                    step.kind !== 'delta' && styles.bridgeLabelStrong,
                  )}
                >
                  {step.label}
                </span>
                {step.codes ? (
                  <span className={styles.bridgeCodes} title={step.codes}>
                    {step.codes}
                  </span>
                ) : null}
              </div>

              {/* Decorative: every figure in this row is also present as
                  text, so the chart adds nothing a screen reader needs. */}
              <div className={styles.bridgeTrack} aria-hidden="true">
                <motion.div
                  className={cx(
                    styles.bridgeBar,
                    negative && styles.bridgeBarOrigin,
                    step.kind === 'opening' && styles.bridgeBarBase,
                    step.kind === 'closing' && styles.bridgeBarTotal,
                    step.kind === 'delta' &&
                      (negative
                        ? styles.bridgeBarNegative
                        : styles.bridgeBarPositive),
                  )}
                  style={{ left: `${left}%`, width: `${width}%` }}
                  initial={reduceMotion ? false : { scaleX: 0, opacity: 0 }}
                  animate={{ scaleX: 1, opacity: 1 }}
                  transition={
                    reduceMotion
                      ? { duration: 0 }
                      : {
                          // Cascading down the bridge in sequence is the
                          // point: it reads as the balance flowing from
                          // books down to 2B rather than as decoration.
                          delay: index * 0.055,
                          duration: 0.42,
                          ease: [0.22, 1, 0.36, 1],
                        }
                  }
                />
                {index > 0 && step.kind === 'delta' ? (
                  <span
                    className={styles.bridgeConnector}
                    style={{ left: `${(step.start / scale) * 100}%` }}
                  />
                ) : null}
              </div>

              <div className={styles.bridgeAmount}>
                <span
                  className={cx(
                    'num',
                    step.kind === 'delta' &&
                      (negative
                        ? styles.bridgeAmountNegative
                        : styles.bridgeAmountPositive),
                  )}
                >
                  {step.kind === 'delta'
                    ? formatSigned(step.amount)
                    : formatRupees(step.amount)}
                </span>
                {step.count !== null ? (
                  <span className={styles.bridgeCount}>
                    {step.count} {step.count === 1 ? 'document' : 'documents'}
                  </span>
                ) : null}
              </div>
            </div>
          );
        })}
      </div>

      <NilProof
        tiesToNil={tiesToNil}
        variance={bridge.closing_variance}
        blocked={bridge.gstr2b_total_blocked}
      />
    </div>
  );
}

/**
 * The closing-variance statement.
 *
 * Deliberately phrased as a consequence of the decomposition rather than as
 * a separate reassurance: every document contributes its signed tax to
 * exactly one line above, so nil here means the decomposition is complete.
 * The failure branch is real and is not styled as a warning-that-never-
 * fires -- if it ever renders, something in the engine is wrong and the
 * reader needs to know immediately.
 */
function NilProof({
  tiesToNil,
  variance,
  blocked,
}: {
  tiesToNil: boolean;
  variance: string;
  blocked: string;
}) {
  return (
    <div className={cx(styles.proof, !tiesToNil && styles.proofFailed)}>
      <span
        className={cx(styles.proofIcon, !tiesToNil && styles.proofIconFailed)}
        aria-hidden="true"
      >
        {tiesToNil ? (
          <SealCheck size={26} weight="duotone" />
        ) : (
          <WarningOctagon size={26} weight="duotone" />
        )}
      </span>
      <div>
        <p
          className={cx(
            styles.proofTitle,
            !tiesToNil && styles.proofTitleFailed,
          )}
        >
          {tiesToNil
            ? 'Closing variance is nil'
            : `Closing variance is ${formatRupees(variance)}`}
        </p>
        <p className={styles.proofBody}>
          {tiesToNil ? (
            <>
              Every document contributed to exactly one line above, so the
              decomposition is complete — the bridge ties by construction, not
              by assertion.
              {!isZero(blocked) ? (
                <>
                  {' '}
                  A further <strong>{formatRupees(blocked)}</strong> sits in
                  GSTR-2B but is flagged unavailable, so it is excluded from
                  the 2B total above.
                </>
              ) : null}
            </>
          ) : (
            <>
              The bridge should always tie to nil. A non-nil variance means a
              document was not allocated to any line — treat this working
              paper as unreliable and report it.
            </>
          )}
        </p>
      </div>
    </div>
  );
}
