(() => {
  'use strict';
  window.addEventListener('message', event => {
    if (event.source !== window || event.origin !== location.origin) return;
    const data = event.data;
    if (!data || data.source !== 'AXEL_GHL_CAPTURE_V1') return;
    chrome.runtime.sendMessage({
      type: 'CAPTURE_TOKENS',
      requestUrl: data.requestUrl,
      locationId: data.locationId,
      authToken: data.authToken,
      tokenId: data.tokenId
    }).catch(() => {});
  });
})();

