import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { m, makeBridge } from '@/test/fixtures';
import { ItcBridgeChart } from './ItcBridgeChart';

describe('ITC bridge', () => {
  it('opens at the books total and closes at the 2B total', () => {
    render(<ItcBridgeChart bridge={makeBridge()} />);

    expect(screen.getByText('ITC as per books')).toBeInTheDocument();
    expect(screen.getByText('₹9,62,626.14')).toBeInTheDocument();
    expect(
      screen.getByText('ITC as per GSTR-2B (available)'),
    ).toBeInTheDocument();
    expect(screen.getByText('₹8,57,749.60')).toBeInTheDocument();
  });

  it('signs each adjustment so direction is readable at a glance', () => {
    render(<ItcBridgeChart bridge={makeBridge()} />);

    expect(screen.getByText('−₹16,812.36')).toBeInTheDocument();
    expect(screen.getByText('+₹21,694.14')).toBeInTheDocument();
  });

  it('cites the reason codes behind every line', () => {
    render(<ItcBridgeChart bridge={makeBridge()} />);

    expect(screen.getByText('EX-01 / EX-12')).toBeInTheDocument();
    expect(screen.getByText('EX-03 / EX-04 / EX-05')).toBeInTheDocument();
  });

  it('pluralises the document count correctly', () => {
    const bridge = makeBridge({
      lines: [
        {
          label: 'Single document line',
          reason_codes: 'EX-10',
          document_count: 1,
          amount: m('-100.00'),
        },
      ],
    });
    render(<ItcBridgeChart bridge={bridge} />);

    expect(screen.getByText('1 document')).toBeInTheDocument();
  });
});

describe('nil-variance proof', () => {
  it('states that the bridge ties, and why that is structural', () => {
    render(<ItcBridgeChart bridge={makeBridge()} />);

    expect(screen.getByText('Closing variance is nil')).toBeInTheDocument();
    // The claim the whole product rests on: it ties by construction, not
    // because a separately-computed figure happened to agree.
    expect(
      screen.getByText(/ties by construction, not.*by assertion/is),
    ).toBeInTheDocument();
  });

  it('mentions blocked credit excluded from the 2B total', () => {
    render(<ItcBridgeChart bridge={makeBridge()} />);
    expect(screen.getByText('₹59,855.40')).toBeInTheDocument();
  });

  it('omits the blocked-credit note when there is none', () => {
    render(
      <ItcBridgeChart
        bridge={makeBridge({ gstr2b_total_blocked: m('0.00') })}
      />,
    );
    expect(screen.queryByText(/flagged unavailable/i)).not.toBeInTheDocument();
  });

  it('raises the alarm loudly when the bridge does NOT tie', () => {
    // This branch should never render against a correct engine, which is
    // exactly why it needs a test -- an untested failure path is one that
    // silently renders as success the day it finally fires.
    render(
      <ItcBridgeChart
        bridge={makeBridge({ closing_variance: m('-12.50') })}
      />,
    );

    expect(screen.getByText('Closing variance is −₹12.50')).toBeInTheDocument();
    expect(
      screen.getByText(/treat this working paper as unreliable/i),
    ).toBeInTheDocument();
    expect(screen.queryByText('Closing variance is nil')).not.toBeInTheDocument();
  });

  it('treats a signed zero as nil, not as a variance', () => {
    // '-0.00' is a legitimate way for a decimal decomposition to land on
    // zero. Rendering it as "−₹0.00 does not tie" would be a false alarm on
    // the single most important number in the product.
    render(
      <ItcBridgeChart bridge={makeBridge({ closing_variance: m('-0.00') })} />,
    );

    expect(screen.getByText('Closing variance is nil')).toBeInTheDocument();
  });
});
