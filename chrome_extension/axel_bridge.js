(() => {
  'use strict';
  const production = location.origin === 'https://axel-ghl.onrender.com';
  const local = location.protocol === 'http:' &&
    (location.hostname === '127.0.0.1' || location.hostname === 'localhost') &&
    location.port === '5057';
  if (!production && !local) return;

  const REQUEST_EVENT = 'axel-ghl-token-request';
  const RESPONSE_EVENT = 'axel-ghl-token-response';
  const AVAILABLE_EVENT = 'axel-ghl-token-available';
  const PAGE_SOURCE = 'AXEL_GHL_PAGE_V1';
  const EXTENSION_SOURCE = 'AXEL_GHL_EXTENSION_V1';

  function emit(type, detail) {
    window.postMessage({ source: EXTENSION_SOURCE, type, detail }, location.origin);
  }

  window.addEventListener('message', async event => {
    if (event.source !== window || event.origin !== location.origin) return;
    const envelope = event.data;
    if (!envelope || envelope.source !== PAGE_SOURCE || envelope.type !== REQUEST_EVENT) return;
    const data = envelope.detail || {};
    if (data.version !== 1 || !Number.isInteger(data.requestId) ||
        typeof data.locationId !== 'string' || !/^[A-Za-z0-9_-]{5,100}$/.test(data.locationId)) return;
    try {
      const reply = await chrome.runtime.sendMessage({ type: 'GET_TOKENS', locationId: data.locationId });
      emit(RESPONSE_EVENT, {
        version: 1,
        requestId: data.requestId,
        locationId: data.locationId,
        ok: !!(reply && reply.ok),
        authToken: reply && reply.authToken || '',
        tokenId: reply && reply.tokenId || '',
        capturedForLocationId: reply && reply.capturedForLocationId || ''
      });
    } catch (_) {
      emit(RESPONSE_EVENT, { version: 1, requestId: data.requestId, locationId: data.locationId, ok: false });
    }
  });

  chrome.runtime.onMessage.addListener(message => {
    if (message && message.type === 'TOKEN_AVAILABLE' && typeof message.locationId === 'string') {
      emit(AVAILABLE_EVENT, { version: 1, locationId: message.locationId });
    }
  });
})();
