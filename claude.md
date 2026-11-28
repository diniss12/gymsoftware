gymsoftware — contexto do projeto

App de gestão de ginásio (sócios, planos, pagamentos, entradas), versão serverless na AWS de um projeto anterior (Ativo Fitness: Spring Boot + React + H2, distribuído como fat JAR). Objetivo principal: gastar o mínimo possível de créditos AWS.

O dono do projeto (Dinis) prefere perceber como as coisas funcionam por dentro — explica o porquê das decisões, não só os passos. Comunica em português de Portugal.

Arquitetura
Browser ──► CloudFront ──(OAC/SigV4)──► S3 privado          (frontend React/Vite)
   ├──SRP──► Cognito User Pool ──► JWT
   └──Bearer JWT──► API Gateway HTTP API (JWT authorizer)
                       └──► 1 Lambda Python 3.13 arm64 ──► DynamoDB
GitHub Actions ──OIDC──► STS ──► SAM/CloudFormation (stack "gymsoftware")

Decisões tomadas (e porquê):

Serverless, tudo pay-per-use: nada fica ligado à espera; custo ~0 com tráfego de ginásio.
DynamoDB em vez de RDS/Aurora: relacional obrigaria a VPC → NAT Gateway (~30 €/mês) e problemas de pool de ligações com Lambda. DynamoDB fala HTTPS+IAM, sem VPC. On-demand, single-table design (PK/SK + GSI1), PITR ligado, DeletionPolicy: Retain.
Python em vez de Java: cold starts de ~200 ms vs segundos com JVM/Spring.
Uma Lambda só ("lambdalith") com router do Powertools for AWS Lambda (APIGatewayHttpResolver) — menos cold starts.
arm64 (Graviton), 256 MB, timeout 10 s. Log group com retenção 14 dias.
HTTP API (não REST API): mais barata. JWT authorizer valida tokens do Cognito antes da Lambda correr. GET /health é pública (smoke test); GET/POST/PUT/DELETE /{proxy+} exigem JWT. NUNCA usar ANY nem criar rota OPTIONS: o preflight CORS (sem token) apanharia o authorizer → 401 → "Failed to fetch" no browser. Sem rota OPTIONS o API Gateway responde ao preflight sozinho.
Cognito tier LITE, AllowAdminCreateUserOnly: true: sem registo público. MFA TOTP (app autenticadora, grátis): MfaConfiguration OPTIONAL (ON só na criação do pool), mas a app obriga a configurar (ConfigurarMFA em Login.jsx, verificado com fetchMFAPreference no App.jsx) e depois o Cognito pede o código em cada login. Perder o telemóvel → admin-set-user-mfa-preference pela CLI para desativar e voltar a configurar. CORS só aceita o domínio do CloudFront (localhost retirado). Só existe UM utilizador gestor (o dono do ginásio) — por agora não usar grupos/roles. Contas criadas via consola/admin-create-user com email_verified=true; primeiro login força nova password (challenge NEW_PASSWORD_REQUIRED). App client sem secret, fluxo SRP.
Frontend: React 19 + Vite 8 + react-router-dom 7 (v8 existe mas não foi usado), JS (sem TypeScript). Login feito à mão com aws-amplify/auth (signIn SRP, confirmSignIn para NEW_PASSWORD_REQUIRED, resetPassword) em vez do <Authenticator> — controlo total do design e bundle menor. Sem package-lock.json (npm não corre localmente): versões exatas no package.json e o workflow usa npm install (npm ci se um dia houver lock). Estética do site ativofitness.pages.dev: preto #0c0c0d, vermelho #c8102e/#e3263f, Anton (títulos) + Montserrat; login em fundo bege #f0dbc0 com o logo do site (PNG branco) pintado a preto via CSS filter. Logo importado em src/assets (Vite põe hash no nome → compatível com cache immutable). Sócios e planos carregados uma vez (DadosProvider); pesquisa e estatísticas calculadas no browser. Chamadas à API com Authorization: Bearer <accessToken> via fetchAuthSession(). Variáveis VITE_API_URL, VITE_USER_POOL_ID, VITE_USER_POOL_CLIENT_ID injetadas pelo workflow a partir dos Outputs da stack.
CloudFront: OAC, PriceClass_100, CachingOptimized, 403/404 → /index.html (SPA routing). Response headers policy (SecurityHeaders): CSP estrita (só 'self', Google Fonts, *.execute-api e cognito-idp da região; sem inline scripts), HSTS 2 anos, X-Frame-Options DENY, nosniff, Referrer-Policy. Se a app partir com erro de CSP na consola do browser, é aqui que se acrescenta a origem em falta. Assets com cache 1 ano immutable; index.html com no-cache; invalidação /* em cada deploy.
Estrutura do repo
.github/workflows/deploy.yml   # pipeline completa (name: Deploy)
template.yaml                  # SAM — TEM de estar na raiz
backend/app.py                 # rotas + regras de negócio
backend/repo.py                # acesso ao DynamoDB (itens, transações)
backend/validacao.py           # validação de campos, NIF, ULID, datas (Europe/Lisbon)
backend/chat.py                # Lambda do assistente (POST /chat): loop Bedrock Converse + ferramentas de leitura + propor_pagamento
backend/regras.py              # FONTE ÚNICA das regras de pagamentos/receita (meses devidos, prazos, atrasos, receita prevista, recebido por método); funções puras usadas pela API e pelo chat
backend/requirements.txt       # aws-lambda-powertools>=3,<4, tzdata
tests/test_chat.py             # ferramentas do chat (moto) + loop com modelo falso (sem Bedrock)
tests/test_regras.py           # testes puros das regras (casos-limite)
tests/test_api.py              # pytest + moto (DynamoDB simulado); correm SÓ no GitHub Actions (passo "Testes", antes do deploy)
scripts/planos.json            # planos mensais com ids fixos; carregar UMA vez: aws dynamodb batch-write-item --region eu-west-1 --request-items file://scripts/planos.json (voltar a correr repõe os preços originais)
requirements-dev.txt           # deps dos testes, instaladas só no CI
NÃO instalar nada nem correr testes no PC do Dinis (sem venv, pip, uv). Testes e builds correm no GitHub Actions. Localmente só git e AWS CLI.
frontend/src/App.jsx           # sessão, router, navegação
frontend/src/Login.jsx         # login / 1.º acesso / recuperar password
frontend/src/dados.jsx         # contexto com sócios + planos
frontend/src/api.js            # fetch com Bearer accessToken; erros → Error(message)
frontend/src/util.js           # formatação: euros/cêntimos, datas, idade, NIF, nomes de meses (SEM regras de pagamento: essas estão no regras.py)
frontend/src/Assistente.jsx     # botão flutuante + barra lateral do chat (conversa mantém-se ao navegar)
frontend/src/pages/            # Inicio (painel de atrasos), Socios, SocioForm, SocioFicha, Pagamentos (componentes usados na ficha), Estatisticas, Planos, comum (Aguardar/Cabecalho/Erro)

Domínio e modelo de dados
"Sócios" = clientes do ginásio (não confundir com o utilizador Cognito, que é só o dono).
Sócio: id (ULID interno), nome, nif (obrigatório, único, dígito de controlo validado), sexo ('M'/'F', obrigatório), dataNascimento, dataEntrada (hoje ou anterior, nunca futura), morada, localidade, notas, plano obrigatório, estado ATIVO/INATIVO (sair = inativar, nunca apagar).
Planos: mensais, sem fidelização, 1× a 6× por semana = 21/23/25/27/29/30 €. Preços em cêntimos (int).
Histórico de planos importa: cada mudança fecha o período atual (dataFim exclusiva = início do seguinte) e abre outro. Períodos guardam cópia de nome/preço do plano (mudar o preço não reescreve o histórico).
Receita por mês (estatísticas): conta o último plano em vigor de cada sócio em cada mês; é receita PREVISTA pelos planos (não pelos pagamentos recebidos). Também há receita por sexo.
Máx. ~300 sócios → GET /socios devolve todos (~300 KB, 1 Query); pesquisa por nome/NIF e estatísticas (por plano, localidade, idade, aniversariantes, inativos) calculadas no frontend, sem GSIs extra. Idade nunca é guardada. Rever se passar de alguns milhares.
Itens (single-table):
  SOCIO#<id> / PERFIL            GSI1: SOCIOS / <nome normalizado>#<id>   (planoId, planoDesde, periodoAtual copiados para a ficha)
  SOCIO#<id> / PERIODO#<ulid>    GSI1: PERIODOS / <dataInicio>#<ulid>   histórico (ULID ordena por criação; datas em atributos). No GSI1 para GET /periodos (receita por mês) sem Scan.
  SOCIO#<id> / PAGAMENTO#<AAAA-MM>  GSI1: PAGAMENTOS / <mes>#<socioId>   1 pagamento por sócio e mês (attribute_not_exists → 409); campos: mes, valor (cêntimos), metodo MBWAY|DINHEIRO, dataPagamento, notas. Apagar = DELETE para corrigir.
  NIF#<nif>  / NIF               garante unicidade via transação com attribute_not_exists
  PLANO#<id> / PLANO             GSI1: PLANOS / <nome normalizado>#<id>
Pagamentos (regras em backend/regras.py; o frontend só mostra o que GET /resumo/* e GET /socios/{id} devolvem): mensalidade do mês M vence no dia 8 de M+1 (DIA_LIMITE); depois fica "em atraso" no painel Início (/). Um sócio deve cada mês em que teve plano em vigor (≥1 dia), pelo preço do último plano desse mês. Cobrança só a partir de INICIO_COBRANCA = 2026-11 (meses anteriores nunca são dívida). Pode pagar-se adiantado até ao mês seguinte. Estatística "pagamentos por método" = valor recebido nos últimos 12 meses por dataPagamento.
Escritas de sócio são transações; ficha usa lock otimista (condição atualizadoEm = valor lido).
Caso-limite conhecido: POST /socios/{id}/plano com data = dataInicio do período atual cria um período de 0 dias (não parte nada, mas suja o histórico).
API: GET/POST /planos, PUT /planos/{id}; GET /periodos (todos, com socioId); GET /pagamentos[?desde=AAAA-MM]; POST /socios/{id}/pagamentos {mes, valor, metodo, dataPagamento?, notas?}; DELETE /socios/{id}/pagamentos/{mes}; GET /socios/{id} inclui historico + pagamentos + situacao {emAtraso, dentroDoPrazo} (cada mês com prazo); GET /resumo/pagamentos (painel do Início); GET /resumo/receita {prevista: 12 meses, porMetodo: recebido 12 meses por dataPagamento}; GET /socios[?estado=], GET/PUT /socios/{id}, POST /socios (planoId obrigatório), POST /socios/{id}/plano {planoId, data?}, /inativar {data?}, /reativar {planoId, data?}. Erros: {"message"} com 400/404/409.
Assistente (chat)
Lambda própria (ChatFunction, handler chat.lambda_handler, mesmo código em backend/) com role SÓ DE LEITURA na tabela + UpdateItem limitado por IAM a chaves LIMITE#* (contador diário, CHAT_LIMITE_DIA=50 perguntas/dia → 429). Rota POST /chat (mais específica que /{proxy+}), timeout 29 s, máx. 5 chamadas ao modelo por pergunta.
Modelo: Amazon Nova Lite via Bedrock Converse API (parâmetro ChatModelId = eu.amazon.nova-lite-v1:0 + ChatFoundationModel para o IAM). Claude Haiku 5.5 no Bedrock dá "not available for this account" (provavelmente conta no Free plan); trocar de modelo = mudar os dois parâmetros.
Ferramentas: listar_socios, procurar_socio, ficha_socio, pagamentos_em_atraso, receita, resumo_socios, listar_planos, propor_pagamento. Valores já em euros (arredondados em Python); números vêm sempre do regras.py. Sem NIF/nascimento/morada nos resultados.
propor_pagamento NÃO grava: devolve uma proposta; o frontend (barra lateral do assistente: botão flutuante no canto inferior direito, src/Assistente.jsx, montado em todas as páginas) mostra um cartão e só ao Confirmar chama POST /socios/{id}/pagamentos (API normal). Criar sócios pelo chat: não (usa o formulário).
Nova Lite escreve raciocínio em <thinking>…</thinking> (em inglês): chat.limpar() tira-o antes de responder; o system prompt insiste em PT-PT e trata "clientes" = "sócios".
Histórico da conversa só no browser; enviado inteiro em cada pedido (máx. 20 mensagens).
AWS
Conta 659791935620, região eu-west-1, stack gymsoftware.
Role de deploy: arn:aws:iam::659791935620:role/GitHubActions-diniss12-gymsoftware (ARN, região e stack estão hardcoded no deploy.yml, sem secrets/variables no GitHub).
Trust policy: o repo usa immutable subject claims do GitHub, por isso o sub é repo:diniss12@156342499/gymsoftware@1451948703:ref:refs/heads/main (StringEquals, só branch main). O formato antigo repo:diniss12/gymsoftware:* NÃO funciona.
Permissions policy inline gymsoftware-deploy: scoped por prefixo gymsoftware-* (Lambda, DynamoDB, IAM roles + PassRole só para lambda.amazonaws.com, logs, S3) + stacks gymsoftware e aws-sam-cli-managed-default, transform Serverless, apigateway:* em eu-west-1, cognito-idp:* (eu-west-1), cloudfront:*. Se um deploy falhar com AccessDenied, acrescentar só a ação em falta.
sam deploy usa --resolve-s3 --capabilities CAPABILITY_IAM --no-confirm-changeset --no-fail-on-empty-changeset.
Outputs da stack (não são segredos; o workflow lê-os sozinho)
ApiUrl: https://2mluqhv8f0.execute-api.eu-west-1.amazonaws.com
FrontendUrl: https://d3c8egkeabgy51.cloudfront.net
UserPoolId: eu-west-1_29CN68hcU — UserPoolClientId: lt2hfdp1tj6og7976kvi79sup
TableName: gymsoftware-Table-1EZNU9XMSH04V — FrontendBucketName: gymsoftware-frontendbucket-c4mvihqk1umt — DistributionId: E3N3HW601HPY3F
Estado atual (2026-11-27)
✅ OIDC GitHub → AWS a funcionar.
✅ Workflow completo (name: Deploy) no repo; run do commit 6b1686a passou todos os passos (frontend saltado).
✅ Stack gymsoftware CREATE_COMPLETE (criada 2026-11-10). Policy gymsoftware-deploy aplicada na role.
✅ GET /health → 200; GET /me sem token → 401 (JWT authorizer a bloquear antes da Lambda).
✅ Utilizador do dono criado no Cognito (2026-11-26) via admin-create-user, email_verified=true, password temporária enviada por email pelo Cognito; estado FORCE_CHANGE_PASSWORD até ao primeiro login. Com UsernameAttributes: [email] o Username interno é o sub (UUID); o login faz-se com o email.
⚠️ A CLI local tem estado a usar a conta root — migrar para um utilizador do IAM Identity Center (AdministratorAccess) e garantir MFA na root.
Decidido: manter o Cognito apesar de haver só 1 utilizador (custo 0 no LITE; evita implementar hashing, bloqueio de força bruta, sessões e recuperação à mão).
✅ Backend de sócios e planos deployed (commit b5396c4, 2026-11-26); 24 testes passam no passo "Testes" do pipeline. GET /socios e /planos testados por invocação direta da Lambda → 200 [].
✅ 6 planos mensais carregados na tabela a partir de scripts/planos.json (2026-11-26) — NÃO voltar a correr o batch-write (repõe preços originais); alterações a planos passam a ser via API.
✅ Frontend deployed (commit 66c121a, 2026-11-26): build no CI passou, CloudFront serve index (no-cache) + bundle (immutable) com VITE_* injetadas; rotas SPA dão 200. Ainda por validar no browser: primeiro login do dono e fluxo completo.
✅ CORS corrigido (commit 303ff7d): rotas GET/POST/PUT/DELETE explícitas em vez de ANY /{proxy+}.
✅ Sexo do sócio + receita por mês e por sexo nas estatísticas (commit a46397b).
✅ Pagamentos (commit 4bde3e6, 2026-11-26): backend (POST/DELETE por sócio e mês, GET /pagamentos) + frontend (registo e histórico na ficha, atrasos no Início, estatística por método).
Push a partir deste PC é feito com a conta GitHub dinisacn1 (colaboradora do repo diniss12/gymsoftware).
Pendente de limpeza: actions do workflow (checkout@v4, setup-python@v5, configure-aws-credentials@v4, setup-sam@v2) usam Node 20 descontinuado.
Próximos passos
Primeiro login do dono (definir password definitiva) e testar GET /me com access token. O app client só permite SRP, por isso o token obtém-se pelo frontend ou por um script SRP (ex.: pycognito), não com aws cognito-idp initiate-auth USER_PASSWORD_AUTH.
Modelar entradas (check-ins) — padrões de acesso primeiro; vezesPorSemana do plano limita entradas.
Atualizar as actions do workflow para versões com Node 24.
Migrar a CLI local da conta root para IAM Identity Center.