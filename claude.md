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
Cognito tier LITE, AllowAdminCreateUserOnly: true: sem registo público. Só existe UM utilizador gestor (o dono do ginásio) — por agora não usar grupos/roles. Contas criadas via consola/admin-create-user com email_verified=true; primeiro login força nova password (challenge NEW_PASSWORD_REQUIRED). App client sem secret, fluxo SRP.
Frontend: React 19 + Vite 8 + react-router-dom 7 (v8 existe mas não foi usado), JS (sem TypeScript). Login feito à mão com aws-amplify/auth (signIn SRP, confirmSignIn para NEW_PASSWORD_REQUIRED, resetPassword) em vez do <Authenticator> — controlo total do design e bundle menor. Sem package-lock.json (npm não corre localmente): versões exatas no package.json e o workflow usa npm install (npm ci se um dia houver lock). Estética do site ativofitness.pages.dev: preto #0c0c0d, vermelho #c8102e/#e3263f, Anton (títulos) + Montserrat; login em fundo bege #f0dbc0 com o logo do site (PNG branco) pintado a preto via CSS filter. Logo importado em src/assets (Vite põe hash no nome → compatível com cache immutable). Sócios e planos carregados uma vez (DadosProvider); pesquisa e estatísticas calculadas no browser. Chamadas à API com Authorization: Bearer <accessToken> via fetchAuthSession(). Variáveis VITE_API_URL, VITE_USER_POOL_ID, VITE_USER_POOL_CLIENT_ID injetadas pelo workflow a partir dos Outputs da stack.
CloudFront: OAC, PriceClass_100, CachingOptimized, 403/404 → /index.html (SPA routing). Assets com cache 1 ano immutable; index.html com no-cache; invalidação /* em cada deploy.
Estrutura do repo
.github/workflows/deploy.yml   # pipeline completa (name: Deploy)
template.yaml                  # SAM — TEM de estar na raiz
backend/app.py                 # rotas + regras de negócio
backend/repo.py                # acesso ao DynamoDB (itens, transações)
backend/validacao.py           # validação de campos, NIF, ULID, datas (Europe/Lisbon)
backend/requirements.txt       # aws-lambda-powertools>=3,<4, tzdata
tests/test_api.py              # pytest + moto (DynamoDB simulado); correm SÓ no GitHub Actions (passo "Testes", antes do deploy)
scripts/planos.json            # planos mensais com ids fixos; carregar UMA vez: aws dynamodb batch-write-item --region eu-west-1 --request-items file://scripts/planos.json (voltar a correr repõe os preços originais)
requirements-dev.txt           # deps dos testes, instaladas só no CI
NÃO instalar nada nem correr testes no PC do Dinis (sem venv, pip, uv). Testes e builds correm no GitHub Actions. Localmente só git e AWS CLI.
frontend/src/App.jsx           # sessão, router, navegação
frontend/src/Login.jsx         # login / 1.º acesso / recuperar password
frontend/src/dados.jsx         # contexto com sócios + planos
frontend/src/pages/            # Socios, SocioForm, SocioFicha, Estatisticas, Planos

Domínio e modelo de dados
"Sócios" = clientes do ginásio (não confundir com o utilizador Cognito, que é só o dono).
Sócio: id (ULID interno), nome, nif (obrigatório, único, dígito de controlo validado), dataNascimento, dataEntrada (hoje ou anterior, nunca futura), morada, localidade, notas, plano obrigatório, estado ATIVO/INATIVO (sair = inativar, nunca apagar).
Planos: mensais, sem fidelização, 1× a 6× por semana = 21/23/25/27/29/30 €. Preços em cêntimos (int).
Histórico de planos importa: cada mudança fecha o período atual (dataFim exclusiva = início do seguinte) e abre outro. Períodos guardam cópia de nome/preço do plano (mudar o preço não reescreve o histórico).
Máx. ~300 sócios → GET /socios devolve todos (~300 KB, 1 Query); pesquisa por nome/NIF e estatísticas (por plano, localidade, idade, aniversariantes, inativos) calculadas no frontend, sem GSIs extra. Idade nunca é guardada. Rever se passar de alguns milhares.
Itens (single-table):
  SOCIO#<id> / PERFIL            GSI1: SOCIOS / <nome normalizado>#<id>   (planoId, planoDesde, periodoAtual copiados para a ficha)
  SOCIO#<id> / PERIODO#<ulid>    histórico (ULID ordena por criação; datas em atributos para se poderem corrigir)
  NIF#<nif>  / NIF               garante unicidade via transação com attribute_not_exists
  PLANO#<id> / PLANO             GSI1: PLANOS / <nome normalizado>#<id>
Escritas de sócio são transações; ficha usa lock otimista (condição atualizadoEm = valor lido).
API: GET/POST /planos, PUT /planos/{id}; GET /socios[?estado=], GET/PUT /socios/{id}, POST /socios (planoId obrigatório), POST /socios/{id}/plano {planoId, data?}, /inativar {data?}, /reativar {planoId, data?}. Erros: {"message"} com 400/404/409.
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
Estado atual (2026-11-26)
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
Push a partir deste PC é feito com a conta GitHub dinisacn1 (colaboradora do repo diniss12/gymsoftware).
Pendente de limpeza: actions do workflow (checkout@v4, setup-python@v5, configure-aws-credentials@v4, setup-sam@v2) usam Node 20 descontinuado.
Próximos passos
Primeiro login do dono (definir password definitiva) e testar GET /me com access token. O app client só permite SRP, por isso o token obtém-se pelo frontend ou por um script SRP (ex.: pycognito), não com aws cognito-idp initiate-auth USER_PASSWORD_AUTH.
Modelar pagamentos/quotas em atraso e entradas (check-ins) — padrões de acesso primeiro; vezesPorSemana do plano limita entradas.
Criar o frontend em frontend/ (React + Vite + Amplify).