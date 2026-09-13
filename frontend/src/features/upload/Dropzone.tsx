import { useId, useRef, useState } from 'react';
import type { DragEvent } from 'react';
import {
  CheckCircle,
  FileArrowUp,
  WarningCircle,
} from '@phosphor-icons/react';

import { cx } from '@/lib/cx';
import { formatBytes } from '@/lib/money';

import styles from './upload.module.css';

export interface DropzoneProps {
  label: string;
  /** What a correct file looks like. Shown before selection. */
  hint: string;
  accept: string;
  file: File | null;
  onSelect: (file: File | null) => void;
  error?: string | undefined;
  disabled?: boolean;
}

/**
 * File intake supporting both drag-and-drop and the native picker.
 *
 * Built on a real, focusable `<input type="file">` overlaid on the visual
 * surface rather than a `<div onClick>` that opens a hidden input. That
 * choice is what gives keyboard operation, the native "no file selected"
 * semantics, form association, and screen-reader announcement for free --
 * all things a div-based dropzone has to reimplement and usually doesn't.
 */
export function Dropzone({
  label,
  hint,
  accept,
  file,
  onSelect,
  error,
  disabled = false,
}: DropzoneProps) {
  const inputId = useId();
  const errorId = `${inputId}-error`;
  const [dragging, setDragging] = useState(false);
  // Drag events fire for every child element; counting enter/leave pairs
  // avoids the flicker a naive boolean produces when the pointer crosses
  // the icon or the label inside the zone.
  const dragDepth = useRef(0);

  function handleDragEnter(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    if (disabled) return;
    dragDepth.current += 1;
    setDragging(true);
  }

  function handleDragLeave(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    dragDepth.current -= 1;
    if (dragDepth.current <= 0) {
      dragDepth.current = 0;
      setDragging(false);
    }
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    dragDepth.current = 0;
    setDragging(false);
    if (disabled) return;
    const dropped = event.dataTransfer.files?.[0];
    if (dropped) onSelect(dropped);
  }

  const state = error ? 'error' : file ? 'filled' : 'empty';

  return (
    <div>
      <div
        className={cx(
          styles.dropzone,
          dragging && styles.dropzoneActive,
          state === 'filled' && styles.dropzoneFilled,
          state === 'error' && styles.dropzoneError,
        )}
        onDragEnter={handleDragEnter}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <div className={styles.dropzoneRow}>
          <span
            className={cx(
              styles.dropzoneIcon,
              state === 'filled' && styles.dropzoneIconFilled,
              state === 'error' && styles.dropzoneIconError,
            )}
            aria-hidden="true"
          >
            {state === 'error' ? (
              <WarningCircle size={18} weight="duotone" />
            ) : state === 'filled' ? (
              <CheckCircle size={18} weight="duotone" />
            ) : (
              <FileArrowUp size={18} weight="duotone" />
            )}
          </span>

          <span className={styles.dropzoneMain}>
            <label className={styles.dropzoneLabel} htmlFor={inputId}>
              {label}
            </label>
            {file ? (
              <span className={styles.dropzoneFile}>
                {file.name} · {formatBytes(file.size)}
              </span>
            ) : (
              <span className={styles.dropzoneHint}>{hint}</span>
            )}
          </span>
        </div>

        <input
          id={inputId}
          className={styles.dropzoneInput}
          type="file"
          accept={accept}
          disabled={disabled}
          aria-invalid={Boolean(error)}
          aria-describedby={error ? errorId : undefined}
          onChange={(event) => onSelect(event.target.files?.[0] ?? null)}
          // Clearing on click lets the same file be re-selected after a
          // failed run; without it, picking the identical path fires no
          // change event and the retry silently does nothing.
          onClick={(event) => {
            (event.target as HTMLInputElement).value = '';
          }}
        />
      </div>

      {error ? (
        <p className={styles.fieldError} id={errorId} role="alert">
          <WarningCircle size={14} weight="fill" style={{ flexShrink: 0, marginTop: 1 }} />
          <span>{error}</span>
        </p>
      ) : null}
    </div>
  );
}
