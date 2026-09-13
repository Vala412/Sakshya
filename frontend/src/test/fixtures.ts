/** Builders for test data shaped like the real API response. */

import type {
  ApiDocument,
  Finding,
  ItcBridge,
  Money,
  Reconciliation,
  RunMetadata,
  Severity,
} from '@/api/types';

/** Cast a literal to the branded Money type. */
export const m = (value: string): Money => value as Money;

export function makeDocument(overrides: Partial<ApiDocument> = {}): ApiDocument {
  return {
    source: 'books',
    doc_type: 'invoice',
    supplier_gstin: '27AAPFU0939F1ZV',
    supplier_name: 'Rajgarhia Steel Traders',
    invoice_number: 'INV/0001',
    invoice_date: '2024-04-01',
    taxable_value: m('1000.00'),
    tax: {
      igst: m('180.00'),
      cgst: m('0.00'),
      sgst: m('0.00'),
      cess: m('0.00'),
      total: m('180.00'),
    },
    itc_availability: null,
    return_period: '042024',
    row_ref: 'books.csv:7',
    ...overrides,
  };
}

export function makeFinding(overrides: Partial<Finding> = {}): Finding {
  return {
    id: 0,
    reason_code: 'EX-04',
    severity: 'high',
    description: 'Tax amount mismatch',
    match_category: 'unmatched',
    books_doc: makeDocument(),
    gstr2b_doc: makeDocument({
      source: 'gstr_2b',
      row_ref: 'gstr2b.json#b2b[0].inv[0]',
      tax: {
        igst: m('175.00'),
        cgst: m('0.00'),
        sgst: m('0.00'),
        cess: m('0.00'),
        total: m('175.00'),
      },
    }),
    itc_at_risk: m('5.00'),
    evidence: 'books=books.csv:7 2b=gstr2b.json#b2b[0].inv[0] mismatched=[total_tax_amount]',
    mismatched_parameters: ['total_tax_amount', 'tax_amount_head_wise'],
    ...overrides,
  };
}

export function makeFindings(): Finding[] {
  return [
    makeFinding({ id: 0, reason_code: 'EX-04', severity: 'high', itc_at_risk: m('5.00') }),
    makeFinding({
      id: 1,
      reason_code: 'EX-03',
      severity: 'medium',
      description: 'Taxable value mismatch',
      itc_at_risk: m('1200.00'),
      mismatched_parameters: ['taxable_value'],
    }),
    makeFinding({
      id: 2,
      reason_code: 'EX-02',
      severity: 'low',
      description: 'In GSTR-2B, not in books',
      match_category: 'in_2b_not_books',
      books_doc: null,
      itc_at_risk: m('0.00'),
      mismatched_parameters: [],
      gstr2b_doc: makeDocument({
        source: 'gstr_2b',
        invoice_number: 'DN/0001',
        supplier_name: 'Kanhaiya Polymers',
        row_ref: 'gstr2b.json#cdnr[0].nt[1]',
      }),
    }),
    makeFinding({
      id: 3,
      reason_code: 'EX-10',
      severity: 'high',
      description: 'Duplicate booking',
      itc_at_risk: m('9800.50'),
      mismatched_parameters: [],
    }),
  ];
}

export function makeBridge(overrides: Partial<ItcBridge> = {}): ItcBridge {
  return {
    books_total: m('962626.14'),
    gstr2b_total_available: m('857749.60'),
    gstr2b_total_blocked: m('59855.40'),
    lines: [
      {
        label: 'In books, not in GSTR-2B',
        reason_codes: 'EX-01 / EX-12',
        document_count: 27,
        amount: m('-16812.36'),
      },
      {
        label: 'Duplicate booking (books side)',
        reason_codes: 'EX-10',
        document_count: 13,
        amount: m('-51190.92'),
      },
      {
        label: 'In GSTR-2B, not in books',
        reason_codes: 'EX-02 / EX-11',
        document_count: 27,
        amount: m('21694.14'),
      },
      {
        label: 'Tax/value variance on matched documents',
        reason_codes: 'EX-03 / EX-04 / EX-05',
        document_count: 196,
        amount: m('-58567.40'),
      },
    ],
    closing_variance: m('0.00'),
    ...overrides,
  };
}

export function makeMetadata(overrides: Partial<RunMetadata> = {}): RunMetadata {
  return {
    gstrecon_version: '0.1.0',
    generated_at: '2026-09-13T08:50:37+00:00',
    books_filename: 'books.csv',
    books_sha256: '3adc4f23807551509751565eea23aa1f3adc4f23807551509751565eea23aa1f',
    gstr2b_filename: 'gstr2b.json',
    gstr2b_sha256: 'c9cd37de56e4cc57b8c89e2621fdaa1fc9cd37de56e4cc57b8c89e2621fdaa1f',
    tax_tolerance: m('0'),
    invoice_fuzzy_threshold: 88,
    gstin_fuzzy_threshold: 85,
    ...overrides,
  };
}

export function makeReconciliation(
  overrides: Partial<Reconciliation> = {},
): Reconciliation {
  const findings = overrides.findings ?? makeFindings();
  const bySeverity: Partial<Record<Severity, number>> = {};
  for (const finding of findings) {
    bySeverity[finding.severity] = (bySeverity[finding.severity] ?? 0) + 1;
  }
  return {
    run_id: 'run-abc123',
    summary: {
      books_document_count: 236,
      gstr2b_document_count: 223,
      finding_count: findings.length,
      findings_by_severity: bySeverity,
      findings_by_reason_code: {},
      matches_by_category: {},
      total_itc_at_risk: m('11005.50'),
    },
    bridge: makeBridge(),
    findings,
    metadata: makeMetadata(),
    ...overrides,
  };
}
