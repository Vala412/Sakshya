import { useMemo, useState } from 'react';
import {
  CaretDown,
  CaretUp,
  CheckCircle,
  MagnifyingGlass,
} from '@phosphor-icons/react';

import type { Finding, Severity } from '@/api/types';
import { Badge, EmptyState, SeverityBadge } from '@/components/ui';
import { cx } from '@/lib/cx';
import { compareMoney, formatRupees } from '@/lib/money';
import {
  MATCH_CATEGORY_LABEL,
  SEVERITY_RANK,
  presentReasonCode,
} from '@/lib/reasonCodes';

import styles from './results.module.css';

type SortKey = 'severity' | 'reason_code' | 'itc_at_risk';
type SortDirection = 'asc' | 'desc';
type SeverityFilter = Severity | 'all';

export interface ExceptionRegisterProps {
  findings: Finding[];
  selectedId: number | null;
  onSelect: (finding: Finding) => void;
}

/**
 * The exception register.
 *
 * Filter and sort state is local: nothing outside this component needs to
 * know which severity chip is active, and lifting it would make the parent
 * re-render the bridge chart every time someone types in the search box.
 */
export function ExceptionRegister({
  findings,
  selectedId,
  onSelect,
}: ExceptionRegisterProps) {
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>('all');
  const [query, setQuery] = useState('');
  const [sortKey, setSortKey] = useState<SortKey>('severity');
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc');

  const severityCounts = useMemo(() => {
    const counts: Record<SeverityFilter, number> = {
      all: findings.length,
      high: 0,
      medium: 0,
      low: 0,
    };
    for (const finding of findings) counts[finding.severity] += 1;
    return counts;
  }, [findings]);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const filtered = findings.filter((finding) => {
      if (severityFilter !== 'all' && finding.severity !== severityFilter) {
        return false;
      }
      if (!needle) return true;
      // Searches what the reader can actually see or would paste in from
      // elsewhere: the code, both plain and technical descriptions, the
      // supplier GSTIN, the invoice number, and the row reference.
      const haystack = [
        finding.reason_code,
        finding.description,
        presentReasonCode(finding.reason_code).title,
        finding.books_doc?.invoice_number,
        finding.gstr2b_doc?.invoice_number,
        finding.books_doc?.supplier_gstin,
        finding.gstr2b_doc?.supplier_gstin,
        finding.books_doc?.supplier_name,
        finding.gstr2b_doc?.supplier_name,
        finding.books_doc?.row_ref,
        finding.gstr2b_doc?.row_ref,
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
      return haystack.includes(needle);
    });

    const direction = sortDirection === 'asc' ? 1 : -1;
    // Sorting a copy: the prop array belongs to the caller, and sorting in
    // place would mutate the reconciliation result the drawer reads from.
    return [...filtered].sort((a, b) => {
      let result: number;
      if (sortKey === 'severity') {
        result = SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity];
        // Ties broken by exposure, so the worst money surfaces first within
        // a severity band rather than falling back on engine order.
        if (result === 0) result = -compareMoney(a.itc_at_risk, b.itc_at_risk);
      } else if (sortKey === 'itc_at_risk') {
        result = compareMoney(a.itc_at_risk, b.itc_at_risk);
      } else {
        result = a.reason_code.localeCompare(b.reason_code);
      }
      return result * direction;
    });
  }, [findings, severityFilter, query, sortKey, sortDirection]);

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDirection((current) => (current === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      // Money reads most-exposed-first; the others read naturally ascending.
      setSortDirection(key === 'itc_at_risk' ? 'desc' : 'asc');
    }
  }

  const filters: Array<{ value: SeverityFilter; label: string }> = [
    { value: 'all', label: 'All' },
    { value: 'high', label: 'High' },
    { value: 'medium', label: 'Medium' },
    { value: 'low', label: 'Low' },
  ];

  return (
    <div>
      <div className={styles.toolbar}>
        <div className={styles.search}>
          <MagnifyingGlass
            size={14}
            className={styles.searchIcon}
            aria-hidden="true"
          />
          <input
            className={styles.searchInput}
            type="search"
            value={query}
            placeholder="Search code, supplier, invoice, or row reference"
            aria-label="Search exceptions"
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>

        <div className={styles.sortField}>
          <label className="visually-hidden" htmlFor="register-sort">
            Sort findings
          </label>
          <select
            id="register-sort"
            className={styles.sortSelect}
            value={`${sortKey}:${sortDirection}`}
            onChange={(event) => {
              const [key, direction] = event.target.value.split(':');
              setSortKey(key as SortKey);
              setSortDirection(direction as SortDirection);
            }}
          >
            <option value="severity:asc">Severity — worst first</option>
            <option value="severity:desc">Severity — least first</option>
            <option value="reason_code:asc">Code — A to Z</option>
            <option value="reason_code:desc">Code — Z to A</option>
            <option value="itc_at_risk:desc">ITC at risk — high to low</option>
            <option value="itc_at_risk:asc">ITC at risk — low to high</option>
          </select>
        </div>

        <div
          className={styles.filterGroup}
          role="group"
          aria-label="Filter by severity"
        >
          {filters.map((filter) => (
            <button
              key={filter.value}
              type="button"
              className={cx(
                styles.filterChip,
                severityFilter === filter.value && styles.filterChipActive,
              )}
              aria-pressed={severityFilter === filter.value}
              onClick={() => setSeverityFilter(filter.value)}
            >
              {filter.label}
              <span className={styles.filterCount}>
                {severityCounts[filter.value]}
              </span>
            </button>
          ))}
        </div>
      </div>

      {findings.length === 0 ? (
        <EmptyState
          icon={<CheckCircle size={22} weight="duotone" />}
          title="No exceptions raised"
          body="Every document in your books matched a GSTR-2B document on all seven GSTN parameters. The working paper is still generated, and the bridge below shows the full decomposition."
        />
      ) : visible.length === 0 ? (
        <EmptyState
          icon={<MagnifyingGlass size={20} weight="duotone" />}
          title="Nothing matches these filters"
          body={
            <>
              {findings.length} exceptions were raised, but none match the
              current search and severity filter.
            </>
          }
        />
      ) : (
        <>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <caption className="visually-hidden">
                Exception register. {visible.length} of {findings.length}{' '}
                findings shown. Select a row to open its evidence trail.
              </caption>
              <thead>
                <tr>
                  <SortableHeader
                    label="Severity"
                    active={sortKey === 'severity'}
                    direction={sortDirection}
                    onClick={() => toggleSort('severity')}
                  />
                  <SortableHeader
                    label="Code"
                    active={sortKey === 'reason_code'}
                    direction={sortDirection}
                    onClick={() => toggleSort('reason_code')}
                  />
                  <th scope="col">Finding</th>
                  <th scope="col">Supplier</th>
                  <th scope="col">Document</th>
                  <SortableHeader
                    label="ITC at risk"
                    numeric
                    active={sortKey === 'itc_at_risk'}
                    direction={sortDirection}
                    onClick={() => toggleSort('itc_at_risk')}
                  />
                </tr>
              </thead>
              <tbody>
                {visible.map((finding) => {
                  const doc = finding.books_doc ?? finding.gstr2b_doc;
                  const presentation = presentReasonCode(finding.reason_code);
                  return (
                    <tr
                      key={finding.id}
                      className={cx(
                        styles.row,
                        finding.severity === 'high' && styles.rowHigh,
                        finding.severity === 'medium' && styles.rowMedium,
                        finding.severity === 'low' && styles.rowLow,
                        selectedId === finding.id && styles.rowActive,
                      )}
                      // Clicking anywhere on the row is a mouse convenience
                      // only. The row deliberately carries NO role or
                      // tabIndex: `role="button"` on a <tr> overrides its
                      // implicit `row` role and destroys the table semantics
                      // a screen-reader user navigates by. The real,
                      // focusable control is the button in the Finding cell.
                      onClick={() => onSelect(finding)}
                    >
                      <td>
                        <span className={styles.cellLabel}>Severity</span>
                        <SeverityBadge severity={finding.severity} />
                      </td>
                      <td className={styles.cellCode}>
                        <span className={styles.cellLabel}>Code</span>
                        {finding.reason_code}
                      </td>
                      <td className={styles.cellTitle}>
                        <span className={styles.cellLabel}>Finding</span>
                        <button
                          type="button"
                          className={styles.rowButton}
                          title={presentation.title}
                          aria-label={`${finding.reason_code}: ${presentation.title}. Open evidence trail.`}
                          onClick={(event) => {
                            // The row handler would otherwise fire too and
                            // open the drawer twice.
                            event.stopPropagation();
                            onSelect(finding);
                          }}
                        >
                          {presentation.title}
                        </button>
                        <span
                          className={styles.cellTitleSub}
                          title={MATCH_CATEGORY_LABEL[finding.match_category]}
                        >
                          {MATCH_CATEGORY_LABEL[finding.match_category]}
                        </span>
                      </td>
                      <td>
                        <span className={styles.cellLabel}>Supplier</span>
                        {doc ? (
                          <>
                            <span className={styles.cellTitleText}>
                              {doc.supplier_name ?? '—'}
                            </span>
                            <span className={styles.cellRef}>
                              {doc.supplier_gstin}
                            </span>
                          </>
                        ) : (
                          <span className={styles.cellMuted}>—</span>
                        )}
                      </td>
                      <td>
                        <span className={styles.cellLabel}>Document</span>
                        {doc ? (
                          <>
                            <span className={styles.cellTitleText}>
                              {doc.invoice_number}
                            </span>
                            <span className={styles.cellRef}>{doc.row_ref}</span>
                          </>
                        ) : (
                          <span className={styles.cellMuted}>—</span>
                        )}
                      </td>
                      <td className={cx(styles.cellNumeric, 'num')}>
                        <span className={styles.cellLabel}>ITC at risk</span>
                        {formatRupees(finding.itc_at_risk)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className={styles.tableFooter}>
            <span>
              Showing {visible.length} of {findings.length} findings
            </span>
            <span>
              <Badge tone="neutral" mono>
                Select any row for its evidence trail
              </Badge>
            </span>
          </div>
        </>
      )}
    </div>
  );
}

function SortableHeader({
  label,
  active,
  direction,
  numeric = false,
  onClick,
}: {
  label: string;
  active: boolean;
  direction: SortDirection;
  numeric?: boolean;
  onClick: () => void;
}) {
  return (
    <th
      scope="col"
      className={cx(styles.thSortable, numeric && styles.thNumeric)}
      aria-sort={
        active
          ? direction === 'asc'
            ? 'ascending'
            : 'descending'
          : 'none'
      }
    >
      <button type="button" className={styles.thButton} onClick={onClick}>
        {label}
        {active ? (
          direction === 'asc' ? (
            <CaretUp size={10} weight="bold" aria-hidden="true" />
          ) : (
            <CaretDown size={10} weight="bold" aria-hidden="true" />
          )
        ) : null}
      </button>
    </th>
  );
}
