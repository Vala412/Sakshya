import { useState } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { ArrowCounterClockwise, DownloadSimple } from '@phosphor-icons/react';

import { workingPaperUrl } from '@/api/client';
import type { Finding, Reconciliation } from '@/api/types';
import { Button, Panel } from '@/components/ui';
import { EvidenceDrawer } from './EvidenceDrawer';
import { ExceptionRegister } from './ExceptionRegister';
import { ItcBridgeChart } from './ItcBridgeChart';
import { ReproducibilityPanel } from './ReproducibilityPanel';
import { SummaryHeader } from './SummaryHeader';

import styles from './results.module.css';

/**
 * Composition of the results workspace.
 *
 * Panels appear in the order a reviewer works: headline figures, the bridge
 * that proves the arithmetic, then the register they triage, then the
 * reproducibility record they cite. The register is not first because
 * "does this tie?" is what determines whether the exceptions are worth
 * reading at all.
 */
export function ResultsView({
  data,
  onReset,
}: {
  data: Reconciliation;
  onReset: () => void;
}) {
  const [selected, setSelected] = useState<Finding | null>(null);
  const reduceMotion = useReducedMotion();

  const panels = [
    <Panel
      key="bridge"
      title="ITC bridge"
      subtitle="How the credit claimed in your books reconciles to what GSTR-2B makes available."
    >
      <ItcBridgeChart bridge={data.bridge} />
    </Panel>,

    <Panel
      key="register"
      title="Exception register"
      subtitle={`${data.summary.finding_count} findings across the twelve reason codes.`}
      bodyless
    >
      <ExceptionRegister
        findings={data.findings}
        selectedId={selected?.id ?? null}
        onSelect={setSelected}
      />
    </Panel>,

    <Panel
      key="repro"
      title="Reproducibility"
      subtitle="What this working paper was produced from."
    >
      <ReproducibilityPanel metadata={data.metadata} />
    </Panel>,
  ];

  return (
    <div className={styles.results}>
      <header className={styles.resultsHead}>
        <div>
          <h1 className={styles.resultsTitle}>Reconciliation complete</h1>
          <p className={styles.resultsSubtitle}>
            {data.metadata.books_filename} against {data.metadata.gstr2b_filename}
          </p>
        </div>
        <div className={styles.resultsActions}>
          <Button variant="ghost" onClick={onReset}>
            <ArrowCounterClockwise size={15} weight="bold" />
            New reconciliation
          </Button>
          {/* A real navigation to the endpoint rather than fetching a blob:
              this keeps the server's Content-Disposition filename and avoids
              holding a multi-megabyte xlsx in memory to hand it straight
              back to the browser. */}
          <Button
            variant="primary"
            onClick={() => {
              window.location.href = workingPaperUrl(data.run_id);
            }}
          >
            <DownloadSimple size={15} weight="bold" />
            Download working paper
          </Button>
        </div>
      </header>

      <SummaryHeader data={data} />

      {panels.map((panel, index) => (
        <motion.div
          key={panel.key}
          initial={reduceMotion ? false : { opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={
            reduceMotion
              ? { duration: 0 }
              : {
                  delay: 0.06 + index * 0.07,
                  duration: 0.4,
                  ease: [0.22, 1, 0.36, 1],
                }
          }
        >
          {panel}
        </motion.div>
      ))}

      <EvidenceDrawer finding={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
