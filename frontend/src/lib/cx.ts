/** Conditional class names. Tiny on purpose -- a dependency for this is not
 * worth the bundle byte, and the whole API surface is one line. */
export function cx(
  ...parts: Array<string | false | null | undefined>
): string {
  return parts.filter(Boolean).join(' ');
}
