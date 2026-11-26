"""Testes da API contra um DynamoDB simulado (moto), sem tocar na AWS.

Correm no GitHub Actions (passo "Testes" do deploy.yml), antes do deploy.
"""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

os.environ.update(
    AWS_DEFAULT_REGION="eu-west-1",
    AWS_ACCESS_KEY_ID="teste",  # credenciais falsas: garante que nada vai a AWS real
    AWS_SECRET_ACCESS_KEY="teste",
    TABLE_NAME="gymsoftware-teste",
    POWERTOOLS_SERVICE_NAME="gymsoftware",
)

import boto3  # noqa: E402
from moto import mock_aws  # noqa: E402

import app as api  # noqa: E402
import repo  # noqa: E402
import validacao  # noqa: E402

NIF_A = "123456789"  # NIFs com digito de controlo valido
NIF_B = "501964843"


class Ctx:
    function_name = "teste"
    memory_limit_in_mb = 256
    invoked_function_arn = "arn:aws:lambda:eu-west-1:000000000000:function:teste"
    aws_request_id = "req-1"


def pedido(metodo: str, caminho: str, body=None, query: dict | None = None, raw: str | None = None):
    evento = {
        "version": "2.0",
        "routeKey": "$default",
        "rawPath": caminho,
        "rawQueryString": "&".join(f"{k}={v}" for k, v in (query or {}).items()),
        "queryStringParameters": query,
        "headers": {"content-type": "application/json"},
        "requestContext": {
            "http": {"method": metodo, "path": caminho, "sourceIp": "1.1.1.1"},
            "requestId": "r",
            "stage": "$default",
            "authorizer": {"jwt": {"claims": {"sub": "u-1", "username": "u-1"}, "scopes": None}},
        },
        "body": raw if raw is not None else (None if body is None else json.dumps(body)),
        "isBase64Encoded": False,
    }
    r = api.lambda_handler(evento, Ctx())
    return r["statusCode"], json.loads(r["body"]) if r.get("body") else None


@pytest.fixture(autouse=True)
def dynamo():
    with mock_aws():
        boto3.client("dynamodb").create_table(
            TableName=os.environ["TABLE_NAME"],
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": n, "AttributeType": "S"} for n in ("PK", "SK", "GSI1PK", "GSI1SK")
            ],
            KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"}, {"AttributeName": "SK", "KeyType": "RANGE"}],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "GSI1",
                    "KeySchema": [
                        {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                        {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
        )
        repo.tabela.cache_clear()
        yield
        repo.tabela.cache_clear()


def criar_plano(vezes=3, preco=2500):
    s, p = pedido("POST", "/planos", {"nome": f"Mensal {vezes}x semana", "vezesPorSemana": vezes, "precoMensal": preco})
    assert s == 201, p
    return p


def dados_socio(plano_id, **extra):
    return {
        "nome": "Álvaro Silva",
        "nif": NIF_A,
        "dataNascimento": "1990-05-17",
        "dataEntrada": "2026-01-10",
        "morada": "Rua X, 1",
        "localidade": "Braga",
        "planoId": plano_id,
        **extra,
    }


# ---------------------------------------------------------------- validacao
@pytest.mark.parametrize("nif,ok", [("123456789", True), ("501964843", True), ("123456780", False), ("12345678", False), ("abcdefghi", False)])
def test_nif(nif, ok):
    assert validacao.nif_valido(nif) is ok


def test_ids_ordenados_e_unicos():
    ids = [validacao.novo_id() for _ in range(1000)]
    assert len(set(ids)) == 1000 and all(len(i) == 26 for i in ids)


# ---------------------------------------------------------------- planos
def test_planos_criar_listar_atualizar():
    p = criar_plano()
    assert p["precoMensal"] == 2500 and p["ativo"] is True
    s, lista = pedido("GET", "/planos")
    assert s == 200 and [x["id"] for x in lista] == [p["id"]]
    assert "PK" not in lista[0]  # chaves internas nao saem na API

    s, p2 = pedido("PUT", f"/planos/{p['id']}", {**p, "precoMensal": 2600})
    assert s == 200 and p2["precoMensal"] == 2600
    assert pedido("PUT", "/planos/naoexiste", p)[0] == 404


def test_plano_invalido():
    s, e = pedido("POST", "/planos", {"nome": "X", "precoMensal": 21.5})
    assert s == 400 and "precoMensal" in e["message"]


# ---------------------------------------------------------------- socios
def test_criar_e_obter_socio():
    plano = criar_plano()
    s, socio = pedido("POST", "/socios", dados_socio(plano["id"]))
    assert s == 201, socio
    assert socio["estado"] == "ATIVO" and socio["planoId"] == plano["id"]
    assert socio["historico"][0]["dataInicio"] == "2026-01-10"
    assert socio["historico"][0]["precoMensal"] == 2500

    s, lido = pedido("GET", f"/socios/{socio['id']}")
    assert s == 200 and lido["nome"] == "Álvaro Silva" and len(lido["historico"]) == 1
    assert pedido("GET", "/socios/naoexiste")[0] == 404


def test_data_entrada_por_omissao_e_hoje():
    plano = criar_plano()
    d = dados_socio(plano["id"])
    del d["dataEntrada"]
    s, socio = pedido("POST", "/socios", d)
    assert s == 201 and socio["dataEntrada"] == validacao.hoje().isoformat()


@pytest.mark.parametrize(
    "extra,mensagem",
    [
        ({"nif": "123456780"}, "NIF"),
        ({"nome": ""}, "nome"),
        ({"dataEntrada": "2999-01-01"}, "futura"),
        ({"dataNascimento": "17/05/1990"}, "AAAA-MM-DD"),
        ({"planoId": "naoexiste"}, "Plano"),
        ({"planoId": None}, "planoId"),
    ],
)
def test_socio_invalido(extra, mensagem):
    plano = criar_plano()
    s, e = pedido("POST", "/socios", dados_socio(plano["id"], **extra))
    assert s == 400 and mensagem in e["message"]


def test_nif_unico():
    plano = criar_plano()
    assert pedido("POST", "/socios", dados_socio(plano["id"]))[0] == 201
    s, e = pedido("POST", "/socios", dados_socio(plano["id"], nome="Outra Pessoa"))
    assert s == 409 and "NIF" in e["message"]
    s, lista = pedido("GET", "/socios")
    assert len(lista) == 1  # a transacao falhada nao deixou nada para tras


def test_listar_ordenado_por_nome_sem_acentos():
    plano = criar_plano()
    pedido("POST", "/socios", dados_socio(plano["id"], nome="Bruno", nif=NIF_A))
    pedido("POST", "/socios", dados_socio(plano["id"], nome="Álvaro", nif=NIF_B))
    _, lista = pedido("GET", "/socios")
    assert [s["nome"] for s in lista] == ["Álvaro", "Bruno"]


def test_editar_socio_e_trocar_nif():
    plano = criar_plano()
    _, a = pedido("POST", "/socios", dados_socio(plano["id"]))
    _, b = pedido("POST", "/socios", dados_socio(plano["id"], nif=NIF_B, nome="B"))

    # NIF de outro socio -> 409
    s, _ = pedido("PUT", f"/socios/{a['id']}", dados_socio(plano["id"], nif=NIF_B))
    assert s == 409

    # trocar NIF de B para um livre liberta o antigo
    s, b2 = pedido("PUT", f"/socios/{b['id']}", dados_socio(plano["id"], nif="999999990", nome="B"))
    assert s == 200 and b2["nif"] == "999999990"
    s, _ = pedido("PUT", f"/socios/{a['id']}", dados_socio(plano["id"], nif=NIF_B, notas="ok"))
    assert s == 200


def test_corrigir_data_entrada_move_inicio_do_plano():
    plano = criar_plano()
    _, s0 = pedido("POST", "/socios", dados_socio(plano["id"]))
    s, s1 = pedido("PUT", f"/socios/{s0['id']}", dados_socio(plano["id"], dataEntrada="2025-12-01"))
    assert s == 200
    assert s1["historico"][0]["dataInicio"] == "2025-12-01" and s1["planoDesde"] == "2025-12-01"


def test_mudar_plano_guarda_historico():
    p3, p5 = criar_plano(3, 2500), criar_plano(5, 2900)
    _, socio = pedido("POST", "/socios", dados_socio(p3["id"]))

    s, e = pedido("POST", f"/socios/{socio['id']}/plano", {"planoId": p3["id"]})
    assert s == 400  # ja esta neste plano
    s, e = pedido("POST", f"/socios/{socio['id']}/plano", {"planoId": p5["id"], "data": "2025-01-01"})
    assert s == 400  # antes do inicio do plano atual

    s, depois = pedido("POST", f"/socios/{socio['id']}/plano", {"planoId": p5["id"], "data": "2026-03-01"})
    assert s == 200, depois
    h = depois["historico"]
    assert [p["planoId"] for p in h] == [p3["id"], p5["id"]]
    assert h[0]["dataFim"] == "2026-03-01" and "dataFim" not in h[1]
    assert depois["planoId"] == p5["id"] and depois["planoDesde"] == "2026-03-01"

    # mudar o preco do plano nao reescreve o historico
    pedido("PUT", f"/planos/{p3['id']}", {**p3, "precoMensal": 9999})
    _, lido = pedido("GET", f"/socios/{socio['id']}")
    assert lido["historico"][0]["precoMensal"] == 2500


def test_inativar_e_reativar():
    p3, p6 = criar_plano(3, 2500), criar_plano(6, 3000)
    _, socio = pedido("POST", "/socios", dados_socio(p3["id"]))
    sid = socio["id"]

    s, ina = pedido("POST", f"/socios/{sid}/inativar", {"data": "2026-06-30"})
    assert s == 200 and ina["estado"] == "INATIVO" and ina["dataSaida"] == "2026-06-30"
    assert ina["historico"][0]["dataFim"] == "2026-06-30"
    assert pedido("POST", f"/socios/{sid}/inativar")[0] == 409
    assert pedido("POST", f"/socios/{sid}/plano", {"planoId": p6["id"]})[0] == 409

    _, ativos = pedido("GET", "/socios", query={"estado": "ATIVO"})
    _, inativos = pedido("GET", "/socios", query={"estado": "INATIVO"})
    assert ativos == [] and len(inativos) == 1

    assert pedido("POST", f"/socios/{sid}/reativar", {"planoId": p6["id"], "data": "2026-06-01"})[0] == 400
    s, rea = pedido("POST", f"/socios/{sid}/reativar", {"planoId": p6["id"], "data": "2026-09-01"})
    assert s == 200 and rea["estado"] == "ATIVO" and "dataSaida" not in rea
    assert [p["planoId"] for p in rea["historico"]] == [p3["id"], p6["id"]]
    assert "dataFim" not in rea["historico"][1]


def test_plano_desativado_nao_aceita_socios():
    p = criar_plano()
    pedido("PUT", f"/planos/{p['id']}", {**p, "ativo": False})
    s, e = pedido("POST", "/socios", dados_socio(p["id"]))
    assert s == 400 and "desativado" in e["message"]


def test_json_invalido():
    s, e = pedido("POST", "/planos", raw="{nao e json")
    assert s == 400 and "JSON" in e["message"]
    s, e = pedido("POST", "/planos", raw="[1, 2]")
    assert s == 400 and "objeto" in e["message"]
