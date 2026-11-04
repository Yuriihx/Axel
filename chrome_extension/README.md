# Extensão AXEL para Chrome e Opera

A extensão usa a arquitetura Chromium e funciona no Chrome e no Opera. A captura também reconhece o domínio GHL personalizado `app.grupohrz.com`.

## Instalação no Chrome

1. No AXEL, clique em **Baixar para Chrome** e extraia o ZIP.
2. Abra `chrome://extensions`, ligue **Modo do desenvolvedor** e clique em **Carregar sem compactação**.
3. Selecione a pasta `axel-chrome-extension` extraída. Se o navegador pedir, permita o acesso ao AXEL e atualize a aba do AXEL.

## Instalação no Opera

1. No AXEL aberto no Opera, clique em **Baixar para Opera** e extraia o ZIP.
2. Abra `opera://extensions` e ligue **Modo do desenvolvedor**.
3. Clique em **Carregar sem compactação** e selecione a pasta `axel-opera-extension` extraída. Se o Opera pedir, permita o acesso ao AXEL e atualize a aba do AXEL.

## Capturar a sessão

Mantenha o AXEL e o GHL abertos no mesmo perfil do navegador onde instalou a extensão. No GHL, abra a subconta e entre em **WhatsApp → Modelos**; depois volte ao AXEL e clique em **Pegar token**. Se não houver captura específica para o `Location ID` selecionado, o AXEL pode reutilizar a captura mais recente nas outras subcontas acessíveis. Também é possível preencher `Authorization` e `token-id` manualmente.

A extensão aceita o AXEL hospedado e o AXEL local em `http://127.0.0.1:5057` ou `http://localhost:5057`.

A extensão observa somente chamadas HTTPS ao endpoint de modelos de WhatsApp do GHL e lê os cabeçalhos `Authorization` e `token-id` dessas chamadas. As sessões ficam em `chrome.storage.session`, na memória da extensão, e são apagadas quando o navegador reinicia, a extensão é desativada ou atualizada. O popup mostra apenas os `Location IDs` e horários de captura; nunca mostra os tokens.

A captura requer uma sessão válida do GHL. Para renovar, abra ou atualize **WhatsApp → Modelos** na subconta. A extensão não usa `webRequest`, depurador, acesso a todas as páginas ou conexão com servidores externos.
