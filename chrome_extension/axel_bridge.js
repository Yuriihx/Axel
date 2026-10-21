(() => {
  'use strict';
  if (location.origin !== 'https://axel-ghl.onrender.com') return;

  const REQUEST_EVENT = 'axel-ghl-token-request';
  const RESPONSE_EVENT = 'axel-ghl-token-response';
  const AVAILABLE_EVENT = 'axel-ghl-token-available';

  function emit(name, detail) {
    window.dispatchEvent(new CustomEvent(name, { detail }));
  }

  window.addEventListener(REQUEST_EVENT, async event => {
    const data = event.detail || {};
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
        tokenId: reply && reply.tokenId || ''
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

