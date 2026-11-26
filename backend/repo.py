"""Acesso ao DynamoDB (single-table).

Itens:
    PK            SK               GSI1PK   GSI1SK
    SOCIO#<id>    PERFIL           SOCIOS   <nome normalizado>#<id>   ficha do socio
    SOCIO#<id>    PERIODO#<pid>    PERIODOS <dataInicio>#<pid>        historico de planos
    SOCIO#<id>    PAGAMENTO#<mes>  PAGAMENTOS <mes>#<id>              pagamento de um mes (AAAA-MM)
    NIF#<nif>     NIF              -        -                         garante NIF unico
    PLANO#<id>    PLANO            PLANOS   <nome normalizado>#<id>   definicao do plano

O <pid> dos periodos e um ULID: ordena pela data de criacao, por isso uma
Query a SOCIO#<id> devolve a ficha e o historico ja ordenado, num so pedido.
As datas ficam em atributos (e nao na SK) para poderem ser corrigidas sem
apagar e recriar itens.

Precos em CENTIMOS (int): 2100 = 21,00 EUR. Evita erros de virgula flutuante.
"""

import os
from decimal import Decimal
from functools import cache

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from validacao import ErroApi, normalizar

CHAVES = ("PK", "SK", "GSI1PK", "GSI1SK")


@cache
def tabela():
    # Criada na 1.a utilizacao (nao no import) e reaproveitada entre invocacoes
    # enquanto a Lambda estiver "quente".
    return boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])


def _cliente():
    # O client do resource aceita tipos Python normais (str, int, dict) nas
    # transacoes, em vez do formato {"S": ...} do client de baixo nivel.
    return tabela().meta.client


def _limpo(item: dict) -> dict:
    """Tira as chaves internas e converte Decimal (como o boto3 devolve numeros)."""

    def conv(v):
        if isinstance(v, Decimal):
            return int(v) if v == v.to_integral_value() else float(v)
        if isinstance(v, dict):
            return {k: conv(x) for k, x in v.items()}
        if isinstance(v, list):
            return [conv(x) for x in v]
        return v

    return {k: conv(v) for k, v in item.items() if k not in CHAVES}


def _query_tudo(**kwargs) -> list[dict]:
    """Query com paginacao: cada pagina traz no maximo 1 MB."""
    itens, inicio = [], None
    while True:
        if inicio:
            kwargs["ExclusiveStartKey"] = inicio
        resp = tabela().query(**kwargs)
        itens += resp["Items"]
        inicio = resp.get("LastEvaluatedKey")
        if not inicio:
            return itens


def _transacao(itens: list[dict], conflitos: dict[int, str]):
    """Escreve tudo ou nada. `conflitos` mapeia indice do item -> mensagem 409
    quando a condicao desse item falha (ex.: NIF ja existe)."""
    for it in itens:
        for op in it.values():
            op["TableName"] = tabela().name
    try:
        _cliente().transact_write_items(TransactItems=itens)
    except ClientError as e:
        if e.response["Error"]["Code"] != "TransactionCanceledException":
            raise
        motivos = e.response.get("CancellationReasons", [])
        for i, m in enumerate(motivos):
            if m.get("Code") == "ConditionalCheckFailed":
                raise ErroApi(409, conflitos.get(i, "Os dados foram alterados entretanto; recarrega e tenta de novo")) from None
        raise


# ================================================================ planos
def _item_plano(p: dict) -> dict:
    return {
        "PK": f"PLANO#{p['id']}",
        "SK": "PLANO",
        "GSI1PK": "PLANOS",
        "GSI1SK": f"{normalizar(p['nome'])}#{p['id']}",
        **p,
    }


def listar_planos() -> list[dict]:
    itens = _query_tudo(IndexName="GSI1", KeyConditionExpression=Key("GSI1PK").eq("PLANOS"))
    return [_limpo(i) for i in itens]


def obter_plano(plano_id: str) -> dict | None:
    item = tabela().get_item(Key={"PK": f"PLANO#{plano_id}", "SK": "PLANO"}).get("Item")
    return _limpo(item) if item else None


def gravar_plano(plano: dict, *, novo: bool):
    cond = "attribute_not_exists(PK)" if novo else "attribute_exists(PK)"
    tabela().put_item(Item=_item_plano(plano), ConditionExpression=cond)


# ================================================================ socios
def _chave_socio(socio_id: str) -> dict:
    return {"PK": f"SOCIO#{socio_id}", "SK": "PERFIL"}


def _item_socio(s: dict) -> dict:
    return {
        **_chave_socio(s["id"]),
        "GSI1PK": "SOCIOS",
        "GSI1SK": f"{normalizar(s['nome'])}#{s['id']}",
        **s,
    }


def _item_periodo(socio_id: str, p: dict) -> dict:
    # No GSI1 sob PERIODOS: uma so Query devolve o historico de TODOS os socios
    # (para a receita por mes), sem Scan a tabela.
    return {
        "PK": f"SOCIO#{socio_id}",
        "SK": f"PERIODO#{p['id']}",
        "GSI1PK": "PERIODOS",
        "GSI1SK": f"{p['dataInicio']}#{p['id']}",
        **p,
    }


def _item_nif(nif: str, socio_id: str) -> dict:
    return {"PK": f"NIF#{nif}", "SK": "NIF", "tipo": "NIF", "socioId": socio_id}


def listar_socios() -> list[dict]:
    # Com ~300 socios (~300 KB) isto e 1 pedido e ~40 unidades de leitura.
    itens = _query_tudo(IndexName="GSI1", KeyConditionExpression=Key("GSI1PK").eq("SOCIOS"))
    return [_limpo(i) for i in itens]


def listar_periodos() -> list[dict]:
    itens = _query_tudo(IndexName="GSI1", KeyConditionExpression=Key("GSI1PK").eq("PERIODOS"))
    return [{**_limpo(i), "socioId": i["PK"].removeprefix("SOCIO#")} for i in itens]


def obter_socio_completo(socio_id: str) -> tuple[dict, list[dict], list[dict]] | None:
    """Ficha + historico de planos + pagamentos, numa so Query a particao do
    socio (tudo partilha PK = SOCIO#<id>). Periodos por ordem de criacao,
    pagamentos por mes (a SK PAGAMENTO#AAAA-MM ordena cronologicamente)."""
    itens = _query_tudo(KeyConditionExpression=Key("PK").eq(f"SOCIO#{socio_id}"))
    perfil = next((i for i in itens if i["SK"] == "PERFIL"), None)
    if not perfil:
        return None
    periodos = [_limpo(i) for i in itens if i["SK"].startswith("PERIODO#")]
    pagamentos = [_limpo(i) for i in itens if i["SK"].startswith("PAGAMENTO#")]
    return _limpo(perfil), periodos, pagamentos


def obter_socio(socio_id: str) -> tuple[dict, list[dict]] | None:
    r = obter_socio_completo(socio_id)
    return (r[0], r[1]) if r else None


# ================================================================ pagamentos
def _chave_pagamento(socio_id: str, mes: str) -> dict:
    return {"PK": f"SOCIO#{socio_id}", "SK": f"PAGAMENTO#{mes}"}


def criar_pagamento(p: dict):
    """Um pagamento por socio e mes: a SK inclui o mes e a condicao
    attribute_not_exists impede um segundo registo para o mesmo mes."""
    item = {
        **_chave_pagamento(p["socioId"], p["mes"]),
        # GSI1 PAGAMENTOS/<mes>#<socio>: todos os pagamentos a partir de um mes
        # numa Query (painel de atrasos e estatisticas), sem Scan.
        "GSI1PK": "PAGAMENTOS",
        "GSI1SK": f"{p['mes']}#{p['socioId']}",
        **p,
    }
    try:
        tabela().put_item(Item=item, ConditionExpression="attribute_not_exists(PK)")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise ErroApi(409, f"Já existe um pagamento registado para {p['mes']}") from None
        raise


def apagar_pagamento(socio_id: str, mes: str):
    try:
        tabela().delete_item(Key=_chave_pagamento(socio_id, mes), ConditionExpression="attribute_exists(PK)")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise ErroApi(404, "Pagamento não encontrado") from None
        raise


def listar_pagamentos(desde: str) -> list[dict]:
    itens = _query_tudo(
        IndexName="GSI1",
        KeyConditionExpression=Key("GSI1PK").eq("PAGAMENTOS") & Key("GSI1SK").gte(desde),
    )
    return [_limpo(i) for i in itens]


def _put(item: dict, cond: str | None = None, valores: dict | None = None) -> dict:
    op = {"Item": item}
    if cond:
        op["ConditionExpression"] = cond
    if valores:
        op["ExpressionAttributeValues"] = valores
    return {"Put": op}


def _fechar_periodo(socio_id: str, periodo_id: str, data_fim: str) -> dict:
    return {
        "Update": {
            "Key": {"PK": f"SOCIO#{socio_id}", "SK": f"PERIODO#{periodo_id}"},
            "UpdateExpression": "SET dataFim = :f",
            "ConditionExpression": "attribute_exists(PK) AND attribute_not_exists(dataFim)",
            "ExpressionAttributeValues": {":f": data_fim},
        }
    }


def criar_socio(socio: dict, periodo: dict):
    _transacao(
        [
            _put(_item_socio(socio), "attribute_not_exists(PK)"),
            _put(_item_nif(socio["nif"], socio["id"]), "attribute_not_exists(PK)"),
            _put(_item_periodo(socio["id"], periodo)),
        ],
        conflitos={1: "Já existe um sócio com este NIF"},
    )


def atualizar_socio(antes: dict, depois: dict, periodo_ajustado: dict | None):
    """Grava a ficha editada. A condicao `atualizadoEm = <valor lido>` e um
    lock otimista: se alguem gravou entretanto, falha em vez de sobrescrever."""
    itens = [
        _put(_item_socio(depois), "atualizadoEm = :v", {":v": antes["atualizadoEm"]}),
    ]
    conflitos = {}
    if depois["nif"] != antes["nif"]:
        itens.append({"Delete": {"Key": {"PK": f"NIF#{antes['nif']}", "SK": "NIF"}}})
        itens.append(_put(_item_nif(depois["nif"], depois["id"]), "attribute_not_exists(PK)"))
        conflitos[len(itens) - 1] = "Já existe um sócio com este NIF"
    if periodo_ajustado:
        itens.append(_put(_item_periodo(depois["id"], periodo_ajustado)))
    _transacao(itens, conflitos)


def mudar_periodo(antes: dict, depois: dict, data_fecho: str | None, novo_periodo: dict | None):
    """Fecha o periodo atual (se houver) e/ou abre um novo, e grava a ficha.
    Usado para mudar de plano, inativar e reativar."""
    itens = [_put(_item_socio(depois), "atualizadoEm = :v", {":v": antes["atualizadoEm"]})]
    if data_fecho and antes.get("periodoAtual"):
        itens.append(_fechar_periodo(antes["id"], antes["periodoAtual"], data_fecho))
    if novo_periodo:
        itens.append(_put(_item_periodo(antes["id"], novo_periodo)))
    _transacao(itens, {})
