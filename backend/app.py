"""API do gymsoftware: uma unica Lambda com router (lambdalith).

A autenticacao acontece ANTES de chegar aqui: o JWT authorizer do API Gateway
valida o token do Cognito e so deixa passar pedidos validos (exceto /health).
As claims do token chegam ja validadas em requestContext.authorizer.jwt.claims.

Regras de negocio ficam aqui; o acesso ao DynamoDB fica no repo.py; a
validacao de campos no validacao.py.
"""

import json
from datetime import date

from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver, Response
from aws_lambda_powertools.logging import correlation_paths
from aws_lambda_powertools.utilities.typing import LambdaContext

import repo
import validacao as v
from validacao import ErroApi

logger = Logger()
app = APIGatewayHttpResolver()


@app.exception_handler(ErroApi)
def _erro_api(e: ErroApi):
    return Response(
        status_code=e.status,
        content_type="application/json",
        body=json.dumps({"message": e.mensagem}, ensure_ascii=False),
    )


def corpo() -> dict:
    if not app.current_event.body:
        return {}  # ex.: POST /inativar sem corpo -> data = hoje
    try:
        body = app.current_event.json_body
    except (json.JSONDecodeError, TypeError):
        raise ErroApi(400, "Corpo do pedido não é JSON válido") from None
    if not isinstance(body, dict):
        raise ErroApi(400, "Corpo do pedido tem de ser um objeto JSON")
    return body


# ================================================================ sistema
@app.get("/health")
def health():
    """Rota publica, usada pelo smoke test do workflow de deploy."""
    return {"status": "ok"}


@app.get("/me")
def me():
    """Devolve quem fez o pedido, a partir das claims do access token."""
    claims = app.current_event.request_context.authorizer.jwt_claim or {}
    return {"sub": claims.get("sub"), "username": claims.get("username")}


# ================================================================ planos
def _campos_plano(body: dict) -> dict:
    vezes = body.get("vezesPorSemana")
    return {
        "nome": v.texto(body, "nome", max_len=60),
        "periodicidade": "MENSAL",  # por agora so existem planos mensais
        # None = sem limite de entradas por semana
        "vezesPorSemana": None if vezes is None else v.inteiro(body, "vezesPorSemana", minimo=1, maximo=7),
        "precoMensal": v.inteiro(body, "precoMensal", minimo=0, maximo=100_000),  # centimos
        "ativo": body.get("ativo", True) is not False,
    }


def _plano_ativo(plano_id) -> dict:
    if not isinstance(plano_id, str) or not plano_id:
        raise ErroApi(400, "'planoId' é obrigatório")
    plano = repo.obter_plano(plano_id)
    if not plano:
        raise ErroApi(400, "Plano não existe")
    if not plano["ativo"]:
        raise ErroApi(400, "Plano está desativado")
    return plano


@app.get("/planos")
def listar_planos():
    return repo.listar_planos()


@app.post("/planos")
def criar_plano():
    plano = {"tipo": "PLANO", "id": v.novo_id(), **_campos_plano(corpo())}
    repo.gravar_plano(plano, novo=True)
    return Response(status_code=201, content_type="application/json", body=json.dumps(plano, ensure_ascii=False))


@app.put("/planos/<plano_id>")
def atualizar_plano(plano_id: str):
    if not repo.obter_plano(plano_id):
        raise ErroApi(404, "Plano não encontrado")
    # Mudar o preco aqui NAO altera o historico dos socios: cada periodo
    # guarda uma copia do preco que estava em vigor quando comecou.
    plano = {"tipo": "PLANO", "id": plano_id, **_campos_plano(corpo())}
    repo.gravar_plano(plano, novo=False)
    return plano


# ================================================================ socios
def _campos_socio(body: dict) -> dict:
    nascimento = v.nao_futura(v.data(body, "dataNascimento"), "dataNascimento")
    if nascimento.year < 1900:
        raise ErroApi(400, "'dataNascimento' inválida")
    entrada = v.nao_futura(v.data(body, "dataEntrada", padrao=v.hoje()), "dataEntrada")
    if entrada < nascimento:
        raise ErroApi(400, "'dataEntrada' não pode ser anterior à data de nascimento")
    return {
        "nome": v.texto(body, "nome", max_len=120),
        "nif": v.nif(body),
        "dataNascimento": nascimento.isoformat(),
        "dataEntrada": entrada.isoformat(),
        "morada": v.texto(body, "morada", max_len=200, obrigatorio=False),
        "localidade": v.texto(body, "localidade", max_len=80, obrigatorio=False),
        "notas": v.texto(body, "notas", max_len=2000, obrigatorio=False),
    }


def _novo_periodo(plano: dict, inicio: date) -> dict:
    # Copia nome/preco/limite do plano: se o plano mudar de preco no futuro,
    # o historico continua a mostrar o que estava em vigor na altura.
    return {
        "tipo": "PERIODO",
        "id": v.novo_id(),
        "planoId": plano["id"],
        "planoNome": plano["nome"],
        "precoMensal": plano["precoMensal"],
        "vezesPorSemana": plano.get("vezesPorSemana"),
        "dataInicio": inicio.isoformat(),
    }


def _carregar(socio_id: str) -> tuple[dict, list[dict]]:
    r = repo.obter_socio(socio_id)
    if not r:
        raise ErroApi(404, "Sócio não encontrado")
    return r


def _periodo_atual(socio: dict, periodos: list[dict]) -> dict | None:
    return next((p for p in periodos if p["id"] == socio.get("periodoAtual")), None)


@app.get("/socios")
def listar_socios():
    estado = app.current_event.get_query_string_value("estado")
    socios = repo.listar_socios()
    if estado:
        socios = [s for s in socios if s["estado"] == estado.upper()]
    return socios


@app.get("/socios/<socio_id>")
def obter_socio(socio_id: str):
    socio, periodos = _carregar(socio_id)
    return {**socio, "historico": periodos}


@app.post("/socios")
def criar_socio():
    body = corpo()
    campos = _campos_socio(body)
    plano = _plano_ativo(body.get("planoId"))
    periodo = _novo_periodo(plano, date.fromisoformat(campos["dataEntrada"]))
    agora = v.agora_iso()
    socio = {
        "tipo": "SOCIO",
        "id": v.novo_id(),
        **campos,
        "estado": "ATIVO",
        "planoId": plano["id"],
        "planoDesde": periodo["dataInicio"],
        "periodoAtual": periodo["id"],
        "criadoEm": agora,
        "atualizadoEm": agora,
    }
    repo.criar_socio(socio, periodo)
    return Response(
        status_code=201,
        content_type="application/json",
        body=json.dumps({**socio, "historico": [periodo]}, ensure_ascii=False),
    )


@app.put("/socios/<socio_id>")
def atualizar_socio(socio_id: str):
    """Edita os dados pessoais. Plano e estado tem rotas proprias."""
    antes, periodos = _carregar(socio_id)
    campos = _campos_socio(corpo())
    depois = {**antes, **campos, "atualizadoEm": v.agora_iso()}

    # Corrigir a data de entrada move o inicio do 1.o periodo de plano.
    primeiro_ajustado = None
    if campos["dataEntrada"] != antes["dataEntrada"]:
        primeiro = periodos[0]
        if primeiro.get("dataFim") and campos["dataEntrada"] >= primeiro["dataFim"]:
            raise ErroApi(400, f"'dataEntrada' tem de ser anterior a {primeiro['dataFim']} (fim do primeiro plano)")
        primeiro_ajustado = {**primeiro, "dataInicio": campos["dataEntrada"]}
        if primeiro["id"] == antes.get("periodoAtual"):
            depois["planoDesde"] = campos["dataEntrada"]

    repo.atualizar_socio(antes, depois, primeiro_ajustado)
    periodos = [primeiro_ajustado if primeiro_ajustado and p["id"] == primeiro_ajustado["id"] else p for p in periodos]
    return {**depois, "historico": periodos}


@app.post("/socios/<socio_id>/plano")
def mudar_plano(socio_id: str):
    """Muda de plano a partir de `data` (por omissao hoje): fecha o periodo
    atual nessa data e abre um novo. dataFim e exclusiva (= inicio do seguinte)."""
    antes, periodos = _carregar(socio_id)
    if antes["estado"] != "ATIVO":
        raise ErroApi(409, "Sócio inativo: usa reativar")
    body = corpo()
    plano = _plano_ativo(body.get("planoId"))
    if plano["id"] == antes["planoId"]:
        raise ErroApi(400, "O sócio já está neste plano")
    data = v.nao_futura(v.data(body, "data", padrao=v.hoje()), "data")
    atual = _periodo_atual(antes, periodos)
    if data.isoformat() < atual["dataInicio"]:
        raise ErroApi(400, f"'data' não pode ser anterior a {atual['dataInicio']} (início do plano atual)")

    novo = _novo_periodo(plano, data)
    depois = {
        **antes,
        "planoId": plano["id"],
        "planoDesde": novo["dataInicio"],
        "periodoAtual": novo["id"],
        "atualizadoEm": v.agora_iso(),
    }
    repo.mudar_periodo(antes, depois, data.isoformat(), novo)
    return obter_socio(socio_id)


@app.post("/socios/<socio_id>/inativar")
def inativar(socio_id: str):
    """Marca como inativo (nada e apagado) e fecha o periodo de plano atual."""
    antes, periodos = _carregar(socio_id)
    if antes["estado"] != "ATIVO":
        raise ErroApi(409, "Sócio já está inativo")
    data = v.nao_futura(v.data(corpo(), "data", padrao=v.hoje()), "data")
    atual = _periodo_atual(antes, periodos)
    if data.isoformat() < atual["dataInicio"]:
        raise ErroApi(400, f"'data' não pode ser anterior a {atual['dataInicio']} (início do plano atual)")

    depois = {**antes, "estado": "INATIVO", "dataSaida": data.isoformat(), "atualizadoEm": v.agora_iso()}
    depois.pop("periodoAtual")  # planoId fica: e o ultimo plano que teve
    repo.mudar_periodo(antes, depois, data.isoformat(), None)
    return obter_socio(socio_id)


@app.post("/socios/<socio_id>/reativar")
def reativar(socio_id: str):
    """Volta a ativar com um plano (obrigatorio), a partir de `data`."""
    antes, _ = _carregar(socio_id)
    if antes["estado"] != "INATIVO":
        raise ErroApi(409, "Sócio já está ativo")
    body = corpo()
    plano = _plano_ativo(body.get("planoId"))
    data = v.nao_futura(v.data(body, "data", padrao=v.hoje()), "data")
    if data.isoformat() < antes["dataSaida"]:
        raise ErroApi(400, f"'data' não pode ser anterior a {antes['dataSaida']} (data de saída)")

    novo = _novo_periodo(plano, data)
    depois = {
        **antes,
        "estado": "ATIVO",
        "planoId": plano["id"],
        "planoDesde": novo["dataInicio"],
        "periodoAtual": novo["id"],
        "atualizadoEm": v.agora_iso(),
    }
    depois.pop("dataSaida")
    repo.mudar_periodo(antes, depois, None, novo)
    return obter_socio(socio_id)


@logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_HTTP)
def lambda_handler(event: dict, context: LambdaContext) -> dict:
    return app.resolve(event, context)
