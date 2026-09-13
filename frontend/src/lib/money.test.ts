import { describe, expect, it } from 'vitest';

import { m } from '@/test/fixtures';
import {
  compareMoney,
  formatAmount,
  formatBytes,
  formatDate,
  formatRupees,
  formatSigned,
  isNegative,
  isZero,
  magnitude,
} from './money';

describe('formatAmount', () => {
  it('groups digits the Indian way, not the Western way', () => {
    // 9,62,626.14 -- lakh grouping. A CA reading 962,626.14 has to stop and
    // re-parse it, which is exactly the friction this app should not add.
    expect(formatAmount(m('962626.14'))).toBe('9,62,626.14');
    expect(formatAmount(m('10000000'))).toBe('1,00,00,000.00');
  });

  it('always shows exactly two decimal places', () => {
    expect(formatAmount(m('1000'))).toBe('1,000.00');
    expect(formatAmount(m('0'))).toBe('0.00');
  });

  it('preserves precision that a float round-trip would lose', () => {
    // 0.1 + 0.2 territory. The engine sends exact decimal strings precisely
    // so these survive; if this ever fails, the string contract has been
    // broken somewhere upstream.
    expect(formatAmount(m('1234.56'))).toBe('1,234.56');
    expect(formatAmount(m('0.07'))).toBe('0.07');
  });

  it('degrades to the raw value rather than throwing on garbage', () => {
    expect(formatAmount('not-a-number')).toBe('not-a-number');
  });
});

describe('isZero', () => {
  it.each(['0', '0.00', '-0.00', '0.000', '-0'])(
    'treats %s as nil',
    (value) => {
      expect(isZero(m(value))).toBe(true);
    },
  );

  it.each(['0.01', '-0.01', '1', '-1234.56'])(
    'treats %s as non-nil',
    (value) => {
      expect(isZero(m(value))).toBe(false);
    },
  );
});

describe('isNegative', () => {
  it('recognises a negative amount', () => {
    expect(isNegative(m('-58567.40'))).toBe(true);
  });

  it('does not call negative zero negative', () => {
    // Otherwise a bridge that ties to nil could render as "−₹0.00", which
    // reads as a variance when it is the absence of one.
    expect(isNegative(m('-0.00'))).toBe(false);
  });
});

describe('formatRupees', () => {
  it('prefixes the rupee sign', () => {
    expect(formatRupees(m('962626.14'))).toBe('₹9,62,626.14');
  });

  it('renders a negative with a true minus sign, before the symbol', () => {
    expect(formatRupees(m('-1234.56'))).toBe('−₹1,234.56');
  });
});

describe('formatSigned', () => {
  it('marks a deduction and an addition distinctly', () => {
    expect(formatSigned(m('-16812.36'))).toBe('−₹16,812.36');
    expect(formatSigned(m('21694.14'))).toBe('+₹21,694.14');
  });

  it('gives nil no sign at all', () => {
    expect(formatSigned(m('0.00'))).toBe('₹0.00');
  });
});

describe('compareMoney', () => {
  it('orders numerically, not lexicographically', () => {
    // '9.00' > '10.00' as strings. Sorting the ITC-at-risk column by string
    // would put small amounts above large ones.
    const sorted = [m('9.00'), m('10.00'), m('100.00')].sort(compareMoney);
    expect(sorted).toEqual(['9.00', '10.00', '100.00']);
  });

  it('handles negatives', () => {
    expect(compareMoney(m('-5.00'), m('5.00'))).toBeLessThan(0);
  });
});

describe('magnitude', () => {
  it('is sign-independent, for bar widths', () => {
    expect(magnitude(m('-58567.40'))).toBe(58567.4);
    expect(magnitude(m('58567.40'))).toBe(58567.4);
  });
});

describe('formatDate', () => {
  it('renders an ISO date readably', () => {
    expect(formatDate('2024-04-01')).toBe('01 Apr 2024');
  });

  it('returns the input unchanged when it is not a date', () => {
    expect(formatDate('not-a-date')).toBe('not-a-date');
  });
});

describe('formatBytes', () => {
  it.each([
    [512, '512 B'],
    [2048, '2.0 KB'],
    [5 * 1024 * 1024, '5.0 MB'],
  ])('formats %i as %s', (bytes, expected) => {
    expect(formatBytes(bytes)).toBe(expected);
  });
});
