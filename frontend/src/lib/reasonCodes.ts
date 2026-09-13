/**
 * Plain-language layer over the twelve reason codes.
 *
 * IMPORTANT: severity and the canonical description are NOT duplicated here.
 * Those come from `GET /api/reason-codes`, which reads the engine's own
 * tables -- a second copy would be a second source of truth and would drift
 * the first time a severity is retuned in `exceptions.py`.
 *
 * What lives here is presentation copy the backend has no opinion about:
 * a human title, what the finding means in a sentence, and what the person
 * reading it is expected to do next. "Tax head mismatch (total agrees,
 * head-wise split doesn't)" is precise and correct, and it is also not what
 * you want as a column heading someone scans 159 times.
 */

import type { GstnParameter, MatchCategory, Severity } from '@/api/types';

export interface ReasonCodePresentation {
  /** Short human title for dense contexts (table cells, chips). */
  title: string;
  /** One sentence on what actually happened. */
  meaning: string;
  /** What the reviewer does about it. */
  action: string;
}

const PRESENTATION: Record<string, ReasonCodePresentation> = {
  'EX-01': {
    title: 'Claimed but not filed by supplier',
    meaning:
      'Your books claim credit on this document, but it does not appear in GSTR-2B at all.',
    action:
      'Chase the supplier to file it. Credit claimed against a document absent from 2B is the classic Section 16(2)(aa) exposure.',
  },
  'EX-02': {
    title: 'Filed by supplier, not in books',
    meaning:
      'The supplier reported this document in GSTR-2B, but your books have no matching entry.',
    action:
      'Check whether the purchase was missed in Tally, or belongs to a different period or entity.',
  },
  'EX-03': {
    title: 'Taxable value differs',
    meaning:
      'The document matched, but the taxable value in your books differs from what the supplier filed.',
    action:
      'Reconcile against the physical invoice. One of the two sides was keyed wrong.',
  },
  'EX-04': {
    title: 'Tax amount differs',
    meaning:
      'The document matched, but the total tax differs between your books and GSTR-2B.',
    action:
      'Credit can only be claimed to the extent reflected in 2B. Confirm the correct figure before filing.',
  },
  'EX-05': {
    title: 'Tax split differs',
    meaning:
      'The total tax agrees, but the IGST/CGST/SGST/CESS split does not — usually an inter- vs intra-state classification error.',
    action:
      'Determine the correct place of supply. The total being right does not make the heads right.',
  },
  'EX-06': {
    title: 'GSTIN invalid or mismatched',
    meaning:
      'The supplier GSTIN fails validation, or differs between your books and 2B.',
    action:
      'Correct the GSTIN in your master data. Credit against an invalid GSTIN is not defensible.',
  },
  'EX-07': {
    title: 'Invoice number differs',
    meaning:
      'The documents match on every other parameter, but the invoice number was keyed differently.',
    action:
      'Usually cosmetic (slashes, leading zeros, spacing). Confirm it is the same document, then normalise your entry.',
  },
  'EX-08': {
    title: 'Period timing difference',
    meaning:
      'The same document appears in both, but in different return periods.',
    action:
      'Normally a cut-off difference that resolves next period. Confirm it is timing, not omission.',
  },
  'EX-09': {
    title: 'Credit blocked in 2B but claimed',
    meaning:
      'GSTR-2B marks this document’s ITC as unavailable, yet your books claim it.',
    action:
      'Reverse the credit. 2B flags this where the supplier is non-compliant or the credit is blocked under Section 17(5).',
  },
  'EX-10': {
    title: 'Duplicate booking',
    meaning:
      'The same document has been booked more than once, so the credit is counted twice.',
    action:
      'Reverse the surplus entry. This inflates ITC directly and is the most mechanically indefensible finding here.',
  },
  'EX-11': {
    title: 'Credit note not reversed',
    meaning:
      'The supplier issued a credit note in 2B, but your books have not reversed the corresponding credit.',
    action:
      'Pass the reversal. Credit already taken against a reversed invoice has to come back.',
  },
  'EX-12': {
    title: 'Credit note not yet in 2B',
    meaning:
      'You have booked a credit note that the supplier has not yet reported.',
    action:
      'Conservative position; usually resolves when the supplier files. Monitor rather than act.',
  },
};

const FALLBACK: ReasonCodePresentation = {
  title: 'Unrecognised reason code',
  meaning:
    'The engine produced a code this interface does not have copy for. The technical description above is authoritative.',
  action: 'Review the evidence trail directly.',
};

/**
 * Presentation copy for a code.
 *
 * Falls back rather than throwing: if the engine gains an EX-13 before this
 * file does, the register must still render every other row. The canonical
 * description from the API is always shown alongside, so an unmapped code
 * degrades to "less friendly", never to "wrong".
 */
export function presentReasonCode(code: string): ReasonCodePresentation {
  return PRESENTATION[code] ?? FALLBACK;
}

export function hasPresentation(code: string): boolean {
  return code in PRESENTATION;
}

/** Sort order for severity: worst first. */
export const SEVERITY_RANK: Record<Severity, number> = {
  high: 0,
  medium: 1,
  low: 2,
};

export const SEVERITY_LABEL: Record<Severity, string> = {
  high: 'High',
  medium: 'Medium',
  low: 'Low',
};

export const MATCH_CATEGORY_LABEL: Record<MatchCategory, string> = {
  exact_match: 'Exact match',
  partial_match: 'Partial match',
  probable_match: 'Probable match',
  unmatched: 'Unmatched',
  in_2b_not_books: 'Only in GSTR-2B',
  in_books_not_2b: 'Only in books',
};

/**
 * GSTN's own parameter names, rendered readably.
 *
 * The raw snake_case value is still shown next to these in the evidence
 * drawer: the friendly label is for scanning, the official name is what an
 * auditor cites.
 */
export const PARAMETER_LABEL: Record<GstnParameter, string> = {
  gstin: 'Supplier GSTIN',
  document_type: 'Document type',
  document_number: 'Document number',
  document_date: 'Document date',
  taxable_value: 'Taxable value',
  total_tax_amount: 'Total tax',
  tax_amount_head_wise: 'Tax split (head-wise)',
};

export const DOC_TYPE_LABEL: Record<string, string> = {
  invoice: 'Invoice',
  credit_note: 'Credit note',
  debit_note: 'Debit note',
};
