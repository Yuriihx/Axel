const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const data = {};
let messageListener;
let notified = [];
const chrome = {
  storage: {
    session: {
      async setAccessLevel() {},
      async set(values) { Object.assign(data, values); },
      async get(keys) {
        if (keys === null) return { ...data };
        const names = Array.isArray(keys) ? keys : [keys];
        return Object.fromEntries(names.filter(key => key in data).map(key => [key, data[key]]));
      },
      async remove(keys) { for (const key of keys) delete data[key]; }
    }
  },
  runtime: {
    onInstalled: { addListener() {} },
    onStartup: { addListener() {} },
    onMessage: { addListener(listener) { messageListener = listener; } },
    getURL(path) { return `chrome-extension://test/${path}`; }
  },
  tabs: {
    async query() { return [{ id: 2 }]; },
    async sendMessage(tabId, message) { notified.push({ tabId, message }); }
  }
};

const context = vm.createContext({ chrome, URL, Promise, Set, Date, Object, Array, Number, String, RegExp, console });
const source = fs.readFileSync(path.join(__dirname, '..', 'service_worker.js'), 'utf8');
vm.runInContext(source, context, { filename: 'service_worker.js' });

const locationId = 'wWSWxY95nO4lw34aS6xF';
const requestUrl = `https://backend.leadconnectorhq.com/phone-system/whatsapp/location/${locationId}/template`;
const authToken = 'eyJhbGciOiJtest.authorization.token';
const tokenId = 'eyJhbGciOiJtest.tokenid.value';
const ghlSender = {
  frameId: 0,
  tab: { url: 'https://app.gohighlevel.com/v2/location/abc/whatsapp' }
};

async function send(message, sender) {
  let response;
  const asyncResponse = messageListener(message, sender, value => { response = value; });
  await new Promise(resolve => setTimeout(resolve, 0));
  return { asyncResponse, response };
}

async function main() {
  messageListener({
    type: 'CAPTURE_TOKENS', locationId, requestUrl,
    authToken, tokenId
  }, ghlSender, () => {});
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.ok(data[`token:${locationId}`], 'valid GHL template calls are saved in session storage');
  assert.equal(notified[0].message.type, 'TOKEN_AVAILABLE');
  assert.equal(notified[0].message.locationId, locationId);

  messageListener({
    type: 'CAPTURE_TOKENS', locationId, requestUrl: requestUrl.replace('/template', '/folder'),
    authToken, tokenId
  }, ghlSender, () => {});
  messageListener({
    type: 'CAPTURE_TOKENS', locationId, requestUrl,
    authToken, tokenId
  }, { ...ghlSender, tab: { url: 'https://example.com/' } }, () => {});
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(Object.keys(data).filter(key => key.startsWith('token:')).length, 1,
    'other endpoints and page origins are rejected');

  const result = await send({ type: 'GET_TOKENS', locationId }, {
    frameId: 0, tab: { url: 'https://axel-ghl.onrender.com/' }
  });
  assert.equal(result.asyncResponse, true);
  assert.equal(result.response.authToken, authToken);
  assert.equal(result.response.tokenId, tokenId);

  const denied = await send({ type: 'GET_TOKENS', locationId }, {
    frameId: 0, tab: { url: 'https://example.com/' }
  });
  assert.equal(denied.response, undefined, 'other sites cannot request captured tokens');
  console.log('service_worker: session storage and origin checks passed');
}

main().catch(error => { console.error(error); process.exitCode = 1; });

