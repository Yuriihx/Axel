# Extensão do Chrome para o AXEL

A captura também funciona no domínio GHL personalizado `app.grupohrz.com`.

1. No AXEL, clique em **Baixar extensão atualizada do AXEL** e extraia o arquivo ZIP. Se já instalou uma versão antiga, substitua os arquivos e atualize/recarregue a extensão em `chrome://extensions`.
2. No Chrome, abra `chrome://extensions` e ligue **Modo do desenvolvedor**.
3. Clique em **Carregar sem compactação** e escolha a pasta `axel-chrome-extension` extraída. Se o Chrome pedir, permita o acesso ao endereço local do AXEL. Atualize a aba do AXEL.
4. Abra o AXEL e o GHL no mesmo perfil do Google Chrome onde a extensão foi instalada. No GHL, abra a subconta e entre em **WhatsApp → Modelos**.
5. Volte ao AXEL e selecione a mesma subconta. Clique em **Pegar token** para buscar a captura feita pela extensão. Se necessário, também é possível preencher `Authorization` e `token-id` manualmente.

A extensão aceita o AXEL hospedado e o AXEL local em `http://127.0.0.1:5057` ou `http://localhost:5057`.

A extensão observa somente chamadas HTTPS ao endpoint de modelos de WhatsApp do GHL e lê os cabeçalhos `Authorization` e `token-id` dessas chamadas. As sessões ficam em `chrome.storage.session`, na memória da extensão, e são apagadas quando o Chrome reinicia, a extensão é desativada ou atualizada. O popup mostra apenas os `Location IDs` e horários de captura; nunca mostra os tokens. O AXEL recebe os tokens somente quando a subconta correspondente está selecionada.

A captura requer uma sessão válida do GHL. Para renovar, abra ou atualize **WhatsApp → Modelos** na subconta. A extensão não usa `webRequest`, depurador, acesso a todas as páginas ou conexão com servidores externos.
