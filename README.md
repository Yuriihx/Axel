# AXEL — hospedagem gratuita

Este pacote preserva o sistema Flask, incluindo os botões prontos, o rodapé do corpo Padrão e a confirmação de empresa divergente. A versão hospedada acrescenta login e armazenamento PostgreSQL, para que os reinícios do servidor não apaguem subcontas, corpos salvos ou configurações.

## Instalação publicada

- **Render Free:** executa o servidor Python, sem disco pago.
- **Neon Free:** mantém os cinco registros do AXEL em PostgreSQL, separados dos arquivos temporários do servidor.
- **Acesso:** usuário e senha do administrador; todas as telas e APIs do sistema exigem sessão autenticada.

Publicado e verificado em 16/10/2026: [abrir AXEL](https://axel-ghl.onrender.com). O serviço `axel-ghl` está no Render Free, em Yuri's workspace. O banco usa o projeto Neon **AXEL GHL** (`withered-darkness-70106807`), branch `axel-render` (`br-shy-breeze-b7ppj7ks`), banco `axel`. Reutilize esses recursos.

As credenciais do administrador foram entregues separadamente. A senha e a conexão do banco ficam nas variáveis do Render; não devem ser incluídas no repositório.

## Limites do gratuito

Condições consultadas em 16/10/2026:

- Render suspende o serviço após 15 minutos sem uso; a primeira abertura depois disso pode demorar. O plano tem cotas de horas, tráfego e compilação.
- Neon Free oferece 1 GB de armazenamento e 100 CU-horas de banco por projeto/mês. O banco reduz o consumo quando está inativo.
- Os planos gratuitos têm limites de disponibilidade e uso. Mantenha os dois serviços no plano Free; não habilite upgrades ou extras pagos sem autorização.

Fontes: [Render Free](https://render.com/docs/free) e [Neon Free](https://neon.com/pricing).

## Republicação

1. Usar o projeto Neon existente **AXEL GHL** e disponibilizar a conexão Render à conversa responsável pela publicação. Não criar outro projeto Neon para repetir esta preparação.
2. Conectar ao Render um repositório Git contendo os arquivos deste pacote na raiz. Não incluir credenciais, arquivos `.env` reais nem dados do AXEL.
3. Criar o serviço a partir de `render.yaml` e confirmar que o plano escolhido é **Free**, sem disco pago.
4. Configurar `DATABASE_URL` com a conexão PostgreSQL fornecida pelo Neon, com SSL obrigatório. Guardar a conexão como variável secreta do Render.
5. Configurar `AXEL_ADMIN_PASSWORD` com pelo menos 7 caracteres. O usuário inicial é `admin`; a chave de sessão `AXEL_SECRET_KEY` é gerada pelo provedor.
6. Aguardar a implantação e conferir o endereço HTTPS emitido pelo Render. A tela inicial deve exigir login e as APIs sem sessão devem retornar 401.
7. Entrar e cadastrar as subcontas. Nenhum dado ou token do computador é importado automaticamente.

O comando de inicialização prepara uma tabela com `CREATE TABLE IF NOT EXISTS`, verifica a conexão e inicia Gunicorn. Se o banco estiver indisponível, o serviço não trata essa falha como uma configuração vazia.

## Variáveis

| Nome | Valor ou finalidade |
| --- | --- |
| `AXEL_STORAGE_MODE` | `postgres` na hospedagem gratuita |
| `DATABASE_URL` | Conexão secreta do Neon, com SSL |
| `AXEL_ADMIN_USER` | Usuário de login; inicialmente `admin` |
| `AXEL_ADMIN_PASSWORD` | Senha secreta, mínimo 7 caracteres |
| `AXEL_SECRET_KEY` | Chave secreta de sessão, mínimo 32 caracteres |
| `AXEL_DATA_DIR` | `/tmp/axel`, usada apenas como pasta de execução no modo PostgreSQL |

O modo `files` permanece disponível para execução com disco persistente. Na configuração gratuita, os dados são lidos e gravados no banco; não dependem de `/tmp/axel` sobreviver.

## Uso

As configurações pertencem ao administrador desta instalação; não há separação por usuário. Os lotes continuam dependendo da aba aberta e os tokens do GHL continuam sujeitos à expiração do próprio GHL. As mídias continuam sendo enviadas ao GHL.

Gunicorn usa uma instância com um processo e quatro threads, preservando os bloqueios do código original. As atualizações automáticas por push estão desativadas.

## Verificação

`python -m unittest discover -s tests -v`

Os testes locais de autenticação bloqueiam rede externa e usam dados descartáveis. Os testes de armazenamento executam o contrato SQL com um adaptador SQLite de teste, incluindo uma rota real do AXEL; eles não substituem o teste de conexão com PostgreSQL/Neon feito durante a implantação.

Os arquivos principais são `axel_ghl21.py`, `wsgi.py`, `postgres_store.py`, `init_storage.py`, `gunicorn.conf.py`, `requirements.txt`, `.python-version` e `render.yaml`. `.gitignore` exclui arquivos sensíveis e dados de execução.


Validação da instalação publicada: `/healthz` respondeu 200, login do administrador funcionou, a API anônima retornou 401 e um registro temporário foi gravado e lido no banco por outra sessão. O registro foi removido e os corpos anteriores foram preservados. Nenhuma chamada de criação ou exclusão de modelo foi enviada ao GHL.
