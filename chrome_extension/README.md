# Extensão do Chrome para o AXEL

A captura também funciona no domínio GHL personalizado `app.grupohrz.com`.

1. No AXEL, clique em **Baixar extensão atualizada do AXEL** e extraia o arquivo ZIP. Se já instalou uma versão antiga, substitua os arquivos e atualize/recarregue a extensão em `chrome://extensions`.
2. No Chrome, abra `chrome://extensions` e ligue **Modo do desenvolvedor**.
3. Clique em **Carregar sem compactação** e escolha a pasta `axel-chrome-extension` extraída. Se o Chrome pedir, permita o acesso ao endereço local do AXEL. Atualize a aba do AXEL.
4. Abra o AXEL e o GHL no mesmo perfil do Google Chrome onde a extensão foi instalada. No GHL, abra a subconta e entre em **WhatsApp → Modelos**.
5. Volte ao AXEL e clique em **Pegar token**. Se não houver uma captura específica para o `Location ID` selecionado, o AXEL reutiliza a sessão mais recente capturada pela extensão. Também é possível preencher `Authorization` e `token-id` manualmente; o par permanece disponível ao trocar o `Location ID`.

A extensão aceita o AXEL hospedado e o AXEL local em `http://127.0.0.1:5057` ou `http://localhost:5057`.

A extensão observa somente chamadas HTTPS ao endpoint de modelos de WhatsApp do GHL e lê os cabeçalhos `Authorization` e `token-id` dessas chamadas. As sessões ficam em `chrome.storage.session`, na memória da extensão, e são apagadas quando o Chrome reinicia, a extensão é desativada ou atualizada. O popup mostra apenas os `Location IDs` e horários de captura; nunca mostra os tokens. O AXEL prefere a captura exata da subconta selecionada e, se ela não existir, usa a captura mais recente para permitir a reutilização do par nas subcontas acessíveis.

A captura requer uma sessão válida do GHL. Para renovar, abra ou atualize **WhatsApp → Modelos** na subconta. A extensão não usa `webRequest`, depurador, acesso a todas as páginas ou conexão com servidores externos.
