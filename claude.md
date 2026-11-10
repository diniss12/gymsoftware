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
HTTP API (não REST API): mais barata. JWT authorizer valida tokens do Cognito antes da Lambda correr. GET /health é pública (smoke test); ANY /{proxy+} exige JWT.
Cognito tier LITE, AllowAdminCreateUserOnly: true: sem registo público. Só existe UM utilizador gestor (o dono do ginásio) — por agora não usar grupos/roles. Contas criadas via consola/admin-create-user com email_verified=true; primeiro login força nova password (challenge NEW_PASSWORD_REQUIRED). App client sem secret, fluxo SRP.
Frontend: React + Vite, Amplify <Authenticator hideSignUp>; chamadas à API com Authorization: Bearer <accessToken> via fetchAuthSession(). Variáveis VITE_API_URL, VITE_USER_POOL_ID, VITE_USER_POOL_CLIENT_ID injetadas pelo workflow a partir dos Outputs da stack.
CloudFront: OAC, PriceClass_100, CachingOptimized, 403/404 → /index.html (SPA routing). Assets com cache 1 ano immutable; index.html com no-cache; invalidação /* em cada deploy.
Estrutura do repo
.github/workflows/deploy.yml   # pipeline completa (name: Deploy)
template.yaml                  # SAM — TEM de estar na raiz
backend/app.py
backend/requirements.txt       # aws-lambda-powertools>=3,<4
frontend/                      # ainda não existe; passos do frontend no workflow são saltados até haver frontend/package.json
AWS
Conta 659791935620, região eu-west-1, stack gymsoftware.
Role de deploy: arn:aws:iam::659791935620:role/GitHubActions-diniss12-gymsoftware (ARN, região e stack estão hardcoded no deploy.yml, sem secrets/variables no GitHub).
Trust policy: o repo usa immutable subject claims do GitHub, por isso o sub é repo:diniss12@156342499/gymsoftware@1451948703:ref:refs/heads/main (StringEquals, só branch main). O formato antigo repo:diniss12/gymsoftware:* NÃO funciona.
Permissions policy inline gymsoftware-deploy: scoped por prefixo gymsoftware-* (Lambda, DynamoDB, IAM roles + PassRole só para lambda.amazonaws.com, logs, S3) + stacks gymsoftware e aws-sam-cli-managed-default, transform Serverless, apigateway:* em eu-west-1, cognito-idp:* (eu-west-1), cloudfront:*. Se um deploy falhar com AccessDenied, acrescentar só a ação em falta.
sam deploy usa --resolve-s3 --capabilities CAPABILITY_IAM --no-confirm-changeset --no-fail-on-empty-changeset.
Estado atual (2026-11-10)
✅ OIDC GitHub → AWS a funcionar (testado com sts get-caller-identity).
✅ template.yaml e deploy.yml validados com cfn-lint / actionlint.
❌ Stack gymsoftware ainda não existe na AWS: o workflow que corre no repo ainda é o de teste ("Deploy to AWS", com passos Debug OIDC claims / Test AWS Connection). É preciso substituí-lo pelo deploy.yml completo (name: Deploy) e remover o step de debug OIDC.
❓ Confirmar que a permissions policy está aplicada: aws iam list-role-policies --role-name GitHubActions-diniss12-gymsoftware deve mostrar gymsoftware-deploy.
Próximos passos
Substituir o workflow de teste pelo deploy.yml completo e fazer push para main; primeiro deploy ~5–10 min (CloudFront). Smoke test /health deve passar.
Criar o utilizador do dono do ginásio no Cognito e testar GET /me com o access token.
Modelar os dados em single-table a partir das entidades (sócios, planos, pagamentos, check-ins) — definir padrões de acesso primeiro.
Criar o frontend em frontend/ (React + Vite + Amplify).