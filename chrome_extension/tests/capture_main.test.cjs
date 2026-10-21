const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const sent = [];
const originalFetch = function() { return Promise.resolve('fetch-result'); };

class MockXHR {
  open(method, url) { this.url = url; }
  setRequestHeader() {}
  send() { this.sent = true; }
}

const window = {
  fetch: originalFetch,
  postMessage(message) { sent.push(message); }
};
const context = vm.createContext({
  window,
  location: { origin: 'https://app.gohighlevel.com', href: 'https://app.gohighlevel.com/' },
  URL,
  Headers,
  Request,
  XMLHttpRequest: MockXHR,
  Date,
  WeakMap,
  Reflect,
  Object,
  String
});

const source = fs.readFileSync(path.join(__dirname, '..', 'capture_main.js'), 'utf8');
vm.runInContext(source, context, { filename: 'capture_main.js' });

async function main() {
  const loc = 'wWSWxY95nO4lw34aS6xF';
  const auth = 'eyJhbGciOiJtest.authorization.token';
  const tokenId = 'eyJhbGciOiJtest.tokenid.value';

  const result = await window.fetch(`https://backend.leadconnectorhq.com/phone-system/whatsapp/location/${loc}/template`, {
    method: 'GET',
    headers: { Authorization: `Bearer ${auth}`, 'token-id': tokenId }
  });
  assert.equal(result, 'fetch-result');
  assert.equal(sent.length, 1);
  assert.equal(sent[0].locationId, loc);
  assert.equal(sent[0].authToken, auth);
  assert.equal(sent[0].tokenId, tokenId);

  await window.fetch(`https://backend.leadconnectorhq.com/phone-system/whatsapp/location/${loc}/folder`, {
    headers: { Authorization: auth, 'token-id': tokenId }
  });
  await window.fetch(`https://example.com/phone-system/whatsapp/location/${loc}/template`, {
    headers: { Authorization: auth, 'token-id': tokenId }
  });
  assert.equal(sent.length, 1, 'non-template URLs must be ignored');

  const xhr = new context.XMLHttpRequest();
  const xhrAuth = 'eyJhbGciOiJanother.authorization.token';
  xhr.open('GET', `https://backend.leadconnectorhq.com/phone-system/whatsapp/location/${loc}/template`);
  xhr.setRequestHeader('Authorization', `Bearer ${xhrAuth}`);
  xhr.setRequestHeader('token-id', tokenId);
  xhr.send();
  assert.equal(xhr.sent, true);
  assert.equal(sent.length, 2, 'XHR template calls must also be captured');
  assert.equal(sent[1].requestUrl, `https://backend.leadconnectorhq.com/phone-system/whatsapp/location/${loc}/template`);
  assert.equal(sent[1].authToken, xhrAuth);
  console.log('capture_main: fetch and XHR restrictions passed');
}

main().catch(error => { console.error(error); process.exitCode = 1; });

