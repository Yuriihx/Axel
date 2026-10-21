'use strict';

const GHL_HOSTS = new Set([
  'app.gohighlevel.com',
  'app.msgsndr.com',
  'app.leadconnectorhq.com',
  'app.grupohrz.com'
]);
const AXEL_URL_PATTERNS = [
  'https://axel-ghl.onrender.com/*',
  'http://127.0.0.1/*',
  'http://localhost/*'
];
const TEMPLATE_PATH = /^\/phone-system\/whatsapp\/location\/([A-Za-z0-9_-]{5,100})\/template\/?$/;
const TOKEN_PREFIX = 'token:';

async function lockSessionStorage() {
  try { await chrome.storage.session.setAccessLevel({ accessLevel: 'TRUSTED_CONTEXTS' }); } catch (_) {}
}
chrome.runtime.onInstalled.addListener(lockSessionStorage);
chrome.runtime.onStartup.addListener(lockSessionStorage);
lockSessionStorage();

function validToken(value) {
  return typeof value === 'string' && value.length >= 20 && value.length <= 12000 && !/[\r\n]/.test(value);
}

function validLocation(value) {
  return typeof value === 'string' && /^[A-Za-z0-9_-]{5,100}$/.test(value);
}

function isGhlSender(sender, locationId, requestUrl) {
  if (!sender || sender.frameId !== 0 || !sender.tab || !sender.tab.url) return false;
  try {
    const page = new URL(sender.tab.url);
    const source = new URL(requestUrl);
    const match = TEMPLATE_PATH.exec(source.pathname);
    return page.protocol === 'https:' && GHL_HOSTS.has(page.hostname) &&
      source.origin === 'https://backend.leadconnectorhq.com' && match && match[1] === locationId;
  } catch (_) { return false; }
}

function isAxelSender(sender) {
  if (!sender || sender.frameId !== 0 || !sender.tab || !sender.tab.url) return false;
  try {
    const page = new URL(sender.tab.url);
    if (page.origin === 'https://axel-ghl.onrender.com') return true;
    return page.protocol === 'http:' &&
      (page.hostname === '127.0.0.1' || page.hostname === 'localhost') &&
      page.port === '5057';
  } catch (_) { return false; }
}

async function notifyAxel(locationId) {
  const tabs = await chrome.tabs.query({ url: AXEL_URL_PATTERNS });
  await Promise.all(tabs.map(tab => chrome.tabs.sendMessage(tab.id, {
    type: 'TOKEN_AVAILABLE', locationId
  }).catch(() => {})));
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || typeof message.type !== 'string') return false;

  if (message.type === 'CAPTURE_TOKENS') {
    const locationId = message.locationId;
    const authToken = typeof message.authToken === 'string'
      ? message.authToken.replace(/^Bearer\s+/i, '').trim() : '';
    const tokenId = typeof message.tokenId === 'string' ? message.tokenId.trim() : '';
    if (!validLocation(locationId) || !isGhlSender(sender, locationId, message.requestUrl) ||
        !validToken(authToken) || !validToken(tokenId)) return false;
    const record = { locationId, authToken, tokenId, capturedAt: Date.now() };
    chrome.storage.session.set({ [TOKEN_PREFIX + locationId]: record }).then(() => notifyAxel(locationId));
    return false;
  }

  if (message.type === 'GET_TOKENS') {
    if (!isAxelSender(sender) || !validLocation(message.locationId)) return false;
    chrome.storage.session.get(TOKEN_PREFIX + message.locationId).then(result => {
      const record = result[TOKEN_PREFIX + message.locationId];
      sendResponse(record ? {
        ok: true, authToken: record.authToken, tokenId: record.tokenId, capturedAt: record.capturedAt
      } : { ok: false });
    }).catch(() => sendResponse({ ok: false }));
    return true;
  }

  if (message.type === 'GET_STATUS') {
    if (!sender.url || !sender.url.startsWith(chrome.runtime.getURL(''))) return false;
    chrome.storage.session.get(null).then(all => {
      const accounts = Object.entries(all)
        .filter(([key]) => key.startsWith(TOKEN_PREFIX))
        .map(([, value]) => ({ locationId: value.locationId, capturedAt: value.capturedAt }))
        .sort((a, b) => b.capturedAt - a.capturedAt);
      sendResponse({ accounts });
    }).catch(() => sendResponse({ accounts: [] }));
    return true;
  }

  if (message.type === 'CLEAR_TOKENS') {
    if (!sender.url || !sender.url.startsWith(chrome.runtime.getURL(''))) return false;
    chrome.storage.session.get(null).then(all => {
      const keys = Object.keys(all).filter(key => key.startsWith(TOKEN_PREFIX));
      return chrome.storage.session.remove(keys);
    }).then(() => sendResponse({ ok: true })).catch(() => sendResponse({ ok: false }));
    return true;
  }
  return false;
});
