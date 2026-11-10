"""API do gymsoftware: uma unica Lambda com router (lambdalith).

A autenticacao acontece ANTES de chegar aqui: o JWT authorizer do API Gateway
valida o token do Cognito e so deixa passar pedidos validos (exceto /health).
As claims do token chegam ja validadas em requestContext.authorizer.jwt.claims.
"""

import os

from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver
from aws_lambda_powertools.logging import correlation_paths
from aws_lambda_powertools.utilities.typing import LambdaContext

TABLE_NAME = os.environ.get("TABLE_NAME", "")

logger = Logger()
app = APIGatewayHttpResolver()


@app.get("/health")
def health():
    """Rota publica, usada pelo smoke test do workflow de deploy."""
    return {"status": "ok"}


@app.get("/me")
def me():
    """Devolve quem fez o pedido, a partir das claims do access token."""
    claims = app.current_event.request_context.authorizer.jwt_claim or {}
    return {
        "sub": claims.get("sub"),
        "username": claims.get("username"),
    }


@logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_HTTP)
def lambda_handler(event: dict, context: LambdaContext) -> dict:
    return app.resolve(event, context)
