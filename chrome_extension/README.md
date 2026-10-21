# Extensão do Chrome para o AXEL

1. No AXEL, clique em **Baixar extensão do AXEL** e extraia o arquivo ZIP.
2. No Chrome, abra `chrome://extensions` e ligue **Modo do desenvolvedor**.
3. Clique em **Carregar sem compactação** e escolha a pasta `axel-chrome-extension` extraída. Atualize a aba do AXEL.
4. Mantenha o Chrome conectado ao AXEL e ao GHL. No GHL, abra a subconta e entre em **WhatsApp → Modelos**.
5. Volte ao AXEL e selecione a mesma subconta. A sessão será preenchida automaticamente.

A extensão observa somente chamadas HTTPS ao endpoint de modelos de WhatsApp do GHL e lê os cabeçalhos `Authorization` e `token-id` dessas chamadas. As sessões ficam em `chrome.storage.session`, na memória da extensão, e são apagadas quando o Chrome reinicia, a extensão é desativada ou atualizada. O popup mostra apenas os `Location IDs` e horários de captura; nunca mostra os tokens. O AXEL recebe os tokens somente quando a subconta correspondente está selecionada.

A captura requer uma sessão válida do GHL. Para renovar, abra ou atualize **WhatsApp → Modelos** na subconta. A extensão não usa `webRequest`, depurador, acesso a todas as páginas ou conexão com servidores externos.

