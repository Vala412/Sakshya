import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { makeFindings } from '@/test/fixtures';
import { ExceptionRegister } from './ExceptionRegister';

function renderRegister(findings = makeFindings()) {
  const onSelect = vi.fn();
  render(
    <ExceptionRegister
      findings={findings}
      selectedId={null}
      onSelect={onSelect}
    />,
  );
  return { onSelect };
}

/** Data rows only, skipping the header row. */
function bodyRows() {
  const table = screen.getByRole('table');
  const [, ...rows] = within(table).getAllByRole('row');
  return rows;
}

describe('reason code rendering', () => {
  it('shows the plain-language title rather than raw backend terminology', () => {
    renderRegister();
    // The engine's own description is "Tax amount mismatch"; the register
    // leads with language a reviewer can triage on.
    expect(screen.getByText('Tax amount differs')).toBeInTheDocument();
    expect(screen.getByText('Duplicate booking')).toBeInTheDocument();
  });

  it('still shows the machine code, which is what gets cited', () => {
    renderRegister();
    expect(screen.getByText('EX-04')).toBeInTheDocument();
    expect(screen.getByText('EX-10')).toBeInTheDocument();
  });

  it('renders a code it has no copy for without dropping the row', () => {
    // Guards the fallback in presentReasonCode: if the engine gains EX-13
    // before the frontend does, the register must still render every row.
    const findings = makeFindings();
    findings[0] = { ...findings[0]!, reason_code: 'EX-99' };
    renderRegister(findings);

    expect(bodyRows()).toHaveLength(4);
    expect(screen.getByText('EX-99')).toBeInTheDocument();
  });

  it('formats ITC at risk as Indian-grouped rupees', () => {
    renderRegister();
    expect(screen.getByText('₹9,800.50')).toBeInTheDocument();
  });
});

describe('severity filtering', () => {
  it('narrows the table to the chosen severity', async () => {
    const user = userEvent.setup();
    renderRegister();
    expect(bodyRows()).toHaveLength(4);

    await user.click(screen.getByRole('button', { name: /^High/ }));

    expect(bodyRows()).toHaveLength(2);
    expect(screen.queryByText('Taxable value differs')).not.toBeInTheDocument();
  });

  it('marks the active filter for assistive technology', async () => {
    const user = userEvent.setup();
    renderRegister();
    const high = screen.getByRole('button', { name: /^High/ });

    expect(high).toHaveAttribute('aria-pressed', 'false');
    await user.click(high);
    expect(high).toHaveAttribute('aria-pressed', 'true');
  });
});

describe('search', () => {
  it('matches on supplier name', async () => {
    const user = userEvent.setup();
    renderRegister();

    await user.type(screen.getByRole('searchbox'), 'Kanhaiya');

    expect(bodyRows()).toHaveLength(1);
    expect(screen.getByText('Kanhaiya Polymers')).toBeInTheDocument();
  });

  it('matches on the row reference an auditor would paste in', async () => {
    const user = userEvent.setup();
    renderRegister();

    await user.type(screen.getByRole('searchbox'), 'cdnr[0]');

    expect(bodyRows()).toHaveLength(1);
  });

  it('explains an empty result instead of showing a blank table', async () => {
    const user = userEvent.setup();
    renderRegister();

    await user.type(screen.getByRole('searchbox'), 'zzzz-no-such-thing');

    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    expect(screen.getByText('Nothing matches these filters')).toBeInTheDocument();
  });
});

describe('sorting', () => {
  it('defaults to worst-severity-first, breaking ties by exposure', () => {
    renderRegister();
    const rows = bodyRows();

    // Both EX-10 (9800.50) and EX-04 (5.00) are high; the larger exposure
    // must lead, otherwise the default view buries the biggest problem.
    expect(within(rows[0]!).getByText('EX-10')).toBeInTheDocument();
    expect(within(rows[1]!).getByText('EX-04')).toBeInTheDocument();
  });

  it('sorts by ITC at risk, descending on first click', async () => {
    const user = userEvent.setup();
    renderRegister();

    await user.click(screen.getByRole('button', { name: /ITC at risk/ }));
    const rows = bodyRows();

    expect(within(rows[0]!).getByText('₹9,800.50')).toBeInTheDocument();
    expect(within(rows[3]!).getByText('₹0.00')).toBeInTheDocument();
  });

  it('reverses on a second click and reports direction via aria-sort', async () => {
    const user = userEvent.setup();
    renderRegister();
    const header = screen.getByRole('button', { name: /ITC at risk/ });

    await user.click(header);
    expect(header.closest('th')).toHaveAttribute('aria-sort', 'descending');

    await user.click(header);
    expect(header.closest('th')).toHaveAttribute('aria-sort', 'ascending');
    expect(within(bodyRows()[0]!).getByText('₹0.00')).toBeInTheDocument();
  });

  it('does not mutate the findings array it was given', async () => {
    const user = userEvent.setup();
    const findings = makeFindings();
    const originalOrder = findings.map((f) => f.id);
    render(
      <ExceptionRegister
        findings={findings}
        selectedId={null}
        onSelect={vi.fn()}
      />,
    );

    await user.click(screen.getByRole('button', { name: /ITC at risk/ }));

    expect(findings.map((f) => f.id)).toEqual(originalOrder);
  });
});

describe('selection', () => {
  it('opens a finding when its title control is clicked', async () => {
    const user = userEvent.setup();
    const { onSelect } = renderRegister();

    await user.click(screen.getByRole('button', { name: /^EX-10/ }));

    expect(onSelect).toHaveBeenCalledOnce();
    expect(onSelect.mock.calls[0]![0].reason_code).toBe('EX-10');
  });

  it('opens it exactly once, not twice, despite the row also being clickable', () => {
    // The row carries a click handler for mouse convenience and the title is
    // a real button; without stopPropagation both fire and the drawer opens
    // on one finding then immediately re-opens on the same one.
    const { onSelect } = renderRegister();

    screen.getByRole('button', { name: /^EX-10/ }).click();

    expect(onSelect).toHaveBeenCalledOnce();
  });

  it('is reachable by keyboard and activates on Enter', async () => {
    const user = userEvent.setup();
    const { onSelect } = renderRegister();
    const control = screen.getByRole('button', { name: /^EX-10/ });

    // Focusable at all: a <div onClick> or a role-less <tr> would fail here.
    control.focus();
    expect(control).toHaveFocus();

    await user.keyboard('{Enter}');
    expect(onSelect).toHaveBeenCalledOnce();
  });

  it('also activates on Space, as a native button does', async () => {
    const user = userEvent.setup();
    const { onSelect } = renderRegister();

    screen.getByRole('button', { name: /^EX-10/ }).focus();
    await user.keyboard(' ');

    expect(onSelect).toHaveBeenCalledOnce();
  });

  it('keeps the table row semantics intact for screen readers', () => {
    // Regression guard: an earlier version put role="button" on the <tr>,
    // which overrode the implicit `row` role and made the register
    // un-navigable as a table.
    renderRegister();
    expect(bodyRows()).toHaveLength(4);
  });
});

describe('small-screen affordances', () => {
  // Below 820px the table re-flows into stacked cards: the column headers
  // are removed and each cell carries its own label. These behaviours are
  // in the DOM at every width (CSS decides visibility), so they are
  // testable in jsdom even though jsdom does no layout.

  it('gives every cell a label element, not a CSS ::before', () => {
    // Generated content is inconsistently exposed to screen readers, and in
    // card mode these labels are the only thing identifying a value once
    // the column headers are gone.
    renderRegister();
    const firstRow = bodyRows()[0]!;

    for (const label of [
      'Severity',
      'Code',
      'Finding',
      'Supplier',
      'Document',
      'ITC at risk',
    ]) {
      expect(within(firstRow).getByText(label)).toBeInTheDocument();
    }
  });

  it('offers a sort control that does not depend on the column headers', async () => {
    const user = userEvent.setup();
    renderRegister();

    await user.selectOptions(
      screen.getByRole('combobox', { name: /sort findings/i }),
      'itc_at_risk:desc',
    );

    expect(within(bodyRows()[0]!).getByText('₹9,800.50')).toBeInTheDocument();
  });

  it('keeps that control in sync with the header sort', async () => {
    // Two controls drive one piece of state. If they desynchronise, the
    // select silently misreports the order actually applied.
    const user = userEvent.setup();
    renderRegister();
    const select = screen.getByRole('combobox', { name: /sort findings/i });

    expect(select).toHaveValue('severity:asc');

    await user.click(screen.getByRole('button', { name: /ITC at risk/ }));
    expect(select).toHaveValue('itc_at_risk:desc');

    await user.click(screen.getByRole('button', { name: /ITC at risk/ }));
    expect(select).toHaveValue('itc_at_risk:asc');
  });

  it('labels the sort control for screen readers', () => {
    renderRegister();
    expect(
      screen.getByRole('combobox', { name: /sort findings/i }),
    ).toBeInTheDocument();
  });
});

describe('empty state', () => {
  it('distinguishes "nothing to report" from "nothing matched a filter"', () => {
    renderRegister([]);

    expect(screen.getByText('No exceptions raised')).toBeInTheDocument();
    // A clean reconciliation is a result, not an absence -- the copy has to
    // say so rather than leaving the reader wondering if it ran.
    expect(
      screen.getByText(/matched a GSTR-2B document on all seven/i),
    ).toBeInTheDocument();
  });
});
