const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '..', 'axel_bridge.js'), 'utf8');
const listeners = new Map();
const sent = [];
let runtimeListener;
const page = {
  addEventListener(type, listener) {
    const entries = listeners.get(type) || [];
    entries.push(listener);
    listeners.set(type, entries);
  },
  postMessage(message, targetOrigin) {
    sent.push({ message, targetOrigin });
  }
};
const location = { origin: 'https://axel-ghl.onrender.com', protocol: 'https:' };
const runtimeMessages = [];
const chrome = {
  runtime: {
    sendMessage: async message => {
      runtimeMessages.push(message);
      return {
        ok: true,
        authToken: 'fake-auth-token-for-test-only-123456',
        tokenId: 'fake-token-id-for-test-only-123456',
        capturedForLocationId: 'B9mGwaUVY58XeUwEobSW'
      };
    },
    onMessage: { addListener(listener) { runtimeListener = listener; } }
  }
};

vm.runInNewContext(source, { window: page, location, chrome, Number, String, Promise });

(async () => {
  const messageHandler = listeners.get('message')[0];
  await messageHandler({
    source: page,
    origin: location.origin,
    data: {
      source: 'AXEL_GHL_PAGE_V1',
      type: 'axel-ghl-token-request',
      detail: { version: 1, requestId: 7, locationId: 'B9mGwaUVY58XeUwEobSW' }
    }
  });
  assert.equal(runtimeMessages.length, 1);
  assert.equal(runtimeMessages[0].type, 'GET_TOKENS');
  assert.equal(runtimeMessages[0].locationId, 'B9mGwaUVY58XeUwEobSW');
  assert.equal(sent.length, 1);
  assert.equal(sent[0].targetOrigin, location.origin);
  assert.equal(sent[0].message.source, 'AXEL_GHL_EXTENSION_V1');
  assert.equal(sent[0].message.type, 'axel-ghl-token-response');
  assert.equal(sent[0].message.detail.requestId, 7);
  assert.equal(sent[0].message.detail.ok, true);

  const countBeforeInvalid = runtimeMessages.length;
  await messageHandler({
    source: page,
    origin: 'https://evil.example',
    data: { source: 'AXEL_GHL_PAGE_V1', type: 'axel-ghl-token-request', detail: { version: 1, requestId: 8, locationId: 'B9mGwaUVY58XeUwEobSW' } }
  });
  assert.equal(runtimeMessages.length, countBeforeInvalid, 'rejects requests from a different origin');

  runtimeListener({ type: 'TOKEN_AVAILABLE', locationId: 'B9mGwaUVY58XeUwEobSW' });
  assert.equal(sent.at(-1).message.type, 'axel-ghl-token-available');
  assert.equal(sent.at(-1).message.detail.locationId, 'B9mGwaUVY58XeUwEobSW');
  console.log('axel_bridge: page-extension messages and origin checks passed');
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});

