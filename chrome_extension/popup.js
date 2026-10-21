const list = document.getElementById('accounts');
const statusEl = document.getElementById('status');

function formatTime(timestamp) {
  try { return new Date(timestamp).toLocaleString('pt-BR'); } catch (_) { return 'sessão atual'; }
}

async function refresh() {
  const result = await chrome.runtime.sendMessage({ type: 'GET_STATUS' }).catch(() => ({ accounts: [] }));
  const accounts = result && Array.isArray(result.accounts) ? result.accounts : [];
  list.replaceChildren();
  if (!accounts.length) {
    statusEl.textContent = 'Nenhuma sessão capturada nesta janela do Chrome. Abra WhatsApp → Modelos no GHL.';
    return;
  }
  statusEl.textContent = `Sessões temporárias disponíveis: ${accounts.length}.`;
  for (const account of accounts) {
    const row = document.createElement('li');
    row.textContent = account.locationId || 'Subconta GHL';
    const time = document.createElement('span');
    time.textContent = `Capturada em ${formatTime(account.capturedAt)}`;
    row.append(time);
    list.append(row);
  }
}

document.getElementById('clear').addEventListener('click', async () => {
  const result = await chrome.runtime.sendMessage({ type: 'CLEAR_TOKENS' }).catch(() => ({ ok: false }));
  statusEl.textContent = result && result.ok ? 'Sessões temporárias apagadas.' : 'Não consegui limpar as sessões.';
  await refresh();
});

refresh();

