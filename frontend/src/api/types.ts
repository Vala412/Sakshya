/**
 * TypeScript mirror of `src/gstrecon/api/schemas.py`.
 *
 * Hand-written rather than generated, and deliberately so: the generated
 * output for this contract would be a near-identical file plus a build step,
 * and `test_api.py` already pins the wire format from the other side. If
 * this file and the Pydantic schemas ever disagree, the API tests fail
 * first, which is where a contract break should surface.
 */

/**
 * An exact decimal, as sent by the API.
 *
 * Branded so a raw `string` cannot be passed where money is expected, and
 * money cannot be concatenated into a label without going through the
 * formatter. The engine works in `Decimal` precisely to avoid binary
 * floating point; parsing these into `number` for arithmetic would give
 * that away at the last step. Parse to `number` ONLY for sorting and chart
 * geometry -- never to compute a figure that is then displayed.
 */
export type Money = string & { readonly __brand: 'Money' };

export type Severity = 'high' | 'medium' | 'low';

export type MatchCategory =
  | 'exact_match'
  | 'partial_match'
  | 'probable_match'
  | 'unmatched'
  | 'in_2b_not_books'
  | 'in_books_not_2b';

export type DocSource = 'books' | 'gstr_2b';
export type DocType = 'invoice' | 'credit_note' | 'debit_note';
/** GSTR-2B's own availability flag. 'Y' available, 'N' blocked. */
export type ItcAvailability = 'Y' | 'N';

/**
 * GSTN's seven official matching parameters, snake_cased. The engine emits
 * these verbatim from the GSTN manual so a finding can cite the official
 * parameter name rather than one we invented.
 */
export type GstnParameter =
  | 'gstin'
  | 'document_type'
  | 'document_number'
  | 'document_date'
  | 'taxable_value'
  | 'total_tax_amount'
  | 'tax_amount_head_wise';

export interface TaxAmounts {
  igst: Money;
  cgst: Money;
  sgst: Money;
  cess: Money;
  total: Money;
}

export interface ApiDocument {
  source: DocSource;
  doc_type: DocType;
  supplier_gstin: string;
  supplier_name: string | null;
  /** ISO date, e.g. '2024-04-01'. */
  invoice_date: string;
  invoice_number: string;
  taxable_value: Money;
  tax: TaxAmounts;
  itc_availability: ItcAvailability | null;
  return_period: string | null;
  /** Provenance into the user's own file, e.g. 'books.csv:31'. */
  row_ref: string;
}

export interface Finding {
  id: number;
  reason_code: string;
  severity: Severity;
  description: string;
  match_category: MatchCategory;
  books_doc: ApiDocument | null;
  gstr2b_doc: ApiDocument | null;
  itc_at_risk: Money;
  evidence: string;
  mismatched_parameters: GstnParameter[];
}

export interface BridgeLine {
  label: string;
  reason_codes: string;
  document_count: number;
  amount: Money;
}

export interface ItcBridge {
  books_total: Money;
  gstr2b_total_available: Money;
  gstr2b_total_blocked: Money;
  /** Order is meaningful: a running decomposition down to nil. Never sort. */
  lines: BridgeLine[];
  closing_variance: Money;
}

export interface Summary {
  books_document_count: number;
  gstr2b_document_count: number;
  finding_count: number;
  findings_by_severity: Partial<Record<Severity, number>>;
  findings_by_reason_code: Record<string, number>;
  matches_by_category: Partial<Record<MatchCategory, number>>;
  /**
   * Headline figure only. Double-counts by design (one document can carry
   * several findings), so it is NOT the bridge's closing variance and must
   * never be labelled as net impact.
   */
  total_itc_at_risk: Money;
}

export interface RunMetadata {
  gstrecon_version: string;
  generated_at: string;
  books_filename: string;
  books_sha256: string;
  gstr2b_filename: string;
  gstr2b_sha256: string;
  tax_tolerance: Money;
  invoice_fuzzy_threshold: number;
  gstin_fuzzy_threshold: number;
}

export interface Reconciliation {
  run_id: string;
  summary: Summary;
  bridge: ItcBridge;
  findings: Finding[];
  metadata: RunMetadata;
}

export interface ReasonCode {
  code: string;
  description: string;
  severity: Severity;
}

/** Which upload an error belongs to, for attaching it to the right control. */
export type ErrorField = 'books' | 'gstr2b' | 'tax_tolerance';

/**
 * Normalised client-side error. Every failure path -- HTTP error envelope,
 * network drop, malformed JSON -- is mapped into this one shape so the UI
 * branches on `kind` instead of sniffing at exceptions.
 */
export interface ApiError {
  kind: 'validation' | 'not_found' | 'server' | 'network' | 'unknown';
  /** Machine code from the API envelope, e.g. 'invalid_books_file'. */
  code: string;
  message: string;
  field: ErrorField | null;
  status: number | null;
}
