/**
 * Reusable primitives, shared across features.
 *
 * Grouped in one module because each is small and they are always imported
 * together; splitting them into six files would add navigation cost without
 * improving anything. Feature-specific components live under `features/`.
 */

import { forwardRef } from 'react';
import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { ArrowClockwise, WarningCircle } from '@phosphor-icons/react';

import type { Severity } from '@/api/types';
import { SEVERITY_LABEL } from '@/lib/reasonCodes';
import { cx } from '@/lib/cx';

import styles from './ui.module.css';

/* -------------------------------------------------------------------- */

type BadgeTone = Severity | 'neutral' | 'nil';

export function Badge({
  tone = 'neutral',
  mono = false,
  dot = false,
  children,
}: {
  tone?: BadgeTone;
  mono?: boolean;
  dot?: boolean;
  children: ReactNode;
}) {
  return (
    <span
      className={cx(styles.badge, styles[tone], mono && styles.mono)}
    >
      {dot ? <span className={styles.badgeDot} aria-hidden="true" /> : null}
      {children}
    </span>
  );
}

/**
 * Severity badge.
 *
 * Carries a dot glyph as well as colour. Colour alone would fail both a
 * greyscale print of the working paper and a red-green colour-vision
 * deficiency, and severity is exactly the field a reviewer triages on.
 */
export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <Badge tone={severity} dot>
      {SEVERITY_LABEL[severity]}
    </Badge>
  );
}

/* -------------------------------------------------------------------- */

type ButtonVariant = 'primary' | 'secondary' | 'ghost';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  iconOnly?: boolean;
}

/**
 * Ref-forwarding so callers can drive focus.
 *
 * Needed by the evidence drawer, which must move focus to its close button
 * on open and hand it back on close. Without a ref that reaches the real
 * `<button>`, a modal dialog cannot meet the focus-management requirement.
 */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  function Button(
    { variant = 'secondary', iconOnly = false, className, type = 'button', ...rest },
    ref,
  ) {
    return (
      <button
        ref={ref}
        type={type}
        className={cx(
          styles.button,
          styles[variant],
          iconOnly && styles.iconButton,
          className,
        )}
        {...rest}
      />
    );
  },
);

/* -------------------------------------------------------------------- */

export function Panel({
  title,
  subtitle,
  actions,
  children,
  bodyless = false,
  className,
  id,
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  /** Skip body padding, for panels that own a full-bleed table. */
  bodyless?: boolean;
  className?: string;
  id?: string;
}) {
  return (
    <section className={cx(styles.panel, className)} id={id}>
      {title ? (
        <header className={styles.panelHeader}>
          <div>
            <h2 className={styles.panelTitle}>{title}</h2>
            {subtitle ? (
              <p className={styles.panelSubtitle}>{subtitle}</p>
            ) : null}
          </div>
          {actions}
        </header>
      ) : null}
      <div className={bodyless ? undefined : styles.panelBody}>{children}</div>
    </section>
  );
}

/* -------------------------------------------------------------------- */

export function Skeleton({
  width = '100%',
  height = 16,
  radius,
}: {
  width?: string | number;
  height?: string | number;
  radius?: string;
}) {
  return (
    <div
      className={styles.skeleton}
      style={{ width, height, ...(radius ? { borderRadius: radius } : {}) }}
      aria-hidden="true"
    />
  );
}

/* -------------------------------------------------------------------- */

export function EmptyState({
  icon,
  title,
  body,
  action,
}: {
  icon: ReactNode;
  title: string;
  body: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className={styles.state}>
      <div className={styles.stateIcon} aria-hidden="true">
        {icon}
      </div>
      <p className={styles.stateTitle}>{title}</p>
      <p className={styles.stateBody}>{body}</p>
      {action ? <div className={styles.stateActions}>{action}</div> : null}
    </div>
  );
}

/**
 * Failure view.
 *
 * `hint` carries the operator-actionable detail (for a dropped connection,
 * the command that starts the server). An error message that says only
 * "something went wrong" wastes the one moment the reader is paying full
 * attention.
 */
export function ErrorState({
  title,
  body,
  hint,
  onRetry,
}: {
  title: string;
  body: ReactNode;
  hint?: string;
  onRetry?: () => void;
}) {
  return (
    <div className={styles.state} role="alert">
      <div
        className={cx(styles.stateIcon, styles.stateIconError)}
        aria-hidden="true"
      >
        <WarningCircle size={22} weight="duotone" />
      </div>
      <p className={styles.stateTitle}>{title}</p>
      <p className={styles.stateBody}>{body}</p>
      {hint ? <p className={styles.stateHint}>{hint}</p> : null}
      {onRetry ? (
        <div className={styles.stateActions}>
          <Button variant="secondary" onClick={onRetry}>
            <ArrowClockwise size={15} weight="bold" />
            Try again
          </Button>
        </div>
      ) : null}
    </div>
  );
}
