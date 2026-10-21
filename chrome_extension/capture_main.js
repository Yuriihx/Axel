(() => {
  'use strict';
  if (window.__axelGhlCaptureInstalled) return;
  window.__axelGhlCaptureInstalled = true;

  const TARGET_ORIGIN = 'https://backend.leadconnectorhq.com';
  const TARGET_PATH = /^\/phone-system\/whatsapp\/location\/([A-Za-z0-9_-]{5,100})\/template\/?$/;
  const EVENT_NAME = 'axel-ghl-capture-v1';
  let lastPair = '';
  let lastSentAt = 0;

  function tokenHeader(headers, name) {
    if (!headers) return '';
    try { return new Headers(headers).get(name) || ''; } catch (_) { return ''; }
  }

  function inspect(urlValue, headers) {
    try {
      const url = new URL(urlValue, location.href);
      if (url.origin !== TARGET_ORIGIN) return;
      const match = TARGET_PATH.exec(url.pathname);
      if (!match) return;
      let authorization = tokenHeader(headers, 'authorization').trim();
      const tokenId = tokenHeader(headers, 'token-id').trim();
      authorization = authorization.replace(/^Bearer\s+/i, '').trim();
      if (!authorization || !tokenId || /[\r\n]/.test(authorization + tokenId)) return;
      if (authorization.length > 12000 || tokenId.length > 12000) return;
      const pair = `${match[1]}:${authorization}:${tokenId}`;
      const now = Date.now();
      if (pair === lastPair && now - lastSentAt < 5000) return;
      lastPair = pair;
      lastSentAt = now;
      window.postMessage({
        source: 'AXEL_GHL_CAPTURE_V1',
        requestUrl: url.href,
        locationId: match[1],
        authToken: authorization,
        tokenId
      }, location.origin);
    } catch (_) {
      // Requests unrelated to the exact GHL template endpoint are ignored.
    }
  }

  const originalFetch = window.fetch;
  if (typeof originalFetch === 'function') {
    window.fetch = function(input, init) {
      try {
        const request = input instanceof Request ? input : null;
        const url = request ? request.url : String(input);
        const headers = init && Object.prototype.hasOwnProperty.call(init, 'headers')
          ? init.headers : (request ? request.headers : null);
        inspect(url, headers);
      } catch (_) {}
      return Reflect.apply(originalFetch, this, arguments);
    };
  }

  const xhrMeta = new WeakMap();
  const originalOpen = XMLHttpRequest.prototype.open;
  const originalSetRequestHeader = XMLHttpRequest.prototype.setRequestHeader;
  const originalSend = XMLHttpRequest.prototype.send;

  XMLHttpRequest.prototype.open = function(method, url) {
    xhrMeta.set(this, { url: String(url), headers: new Headers() });
    return Reflect.apply(originalOpen, this, arguments);
  };
  XMLHttpRequest.prototype.setRequestHeader = function(name, value) {
    const meta = xhrMeta.get(this);
    if (meta && /^(authorization|token-id)$/i.test(String(name))) {
      try { meta.headers.set(String(name), String(value)); } catch (_) {}
    }
    return Reflect.apply(originalSetRequestHeader, this, arguments);
  };
  XMLHttpRequest.prototype.send = function() {
    const meta = xhrMeta.get(this);
    if (meta) inspect(meta.url, meta.headers);
    return Reflect.apply(originalSend, this, arguments);
  };
})();

