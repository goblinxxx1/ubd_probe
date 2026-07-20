global.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

if (!global.matchMedia) {
  global.matchMedia = (query) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    dispatchEvent() { return false; },
  });
}
