import '@testing-library/jest-dom/vitest';

// jsdom implements neither of these, and both are used by components under
// test: useReducedMotion() reads matchMedia, and the theme hook reads it on
// mount. Without a stub, every test touching either crashes on import
// rather than on anything the test is actually asserting.
if (!window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}
