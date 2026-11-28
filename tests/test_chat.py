"""Testes do assistente (backend/chat.py), sem chamar o Bedrock.

As ferramentas correm contra o DynamoDB simulado (moto, fixture do test_api).
O modelo e substituido por um falso que devolve respostas pre-definidas, para
testar o loop: pedidos de ferramentas, resultados, propostas e limites.
"""

import json
from datetime import date

import pytest

# Reaproveita o ambiente (variaveis, tabela simulada) e os ajudantes da API.
from test_api import Ctx, NIF_B, criar_plano, dados_socio, dynamo, pagamento, pedido  # noqa: F401

import chat  # noqa: E402
import validacao  # noqa: E402


@pytest.fixture(autouse=True)
def hoje_fixo(monkeypatch):
    monkeypatch.setattr(validacao, "hoje", lambda: date(2027, 1, 5))


class ModeloFalso:
    """Devolve as respostas da lista, por ordem, e guarda os pedidos recebidos."""

    def __init__(self, *respostas):
        self.respostas = list(respostas)
        self.pedidos = []

    def converse(self, **kwargs):
        self.pedidos.append(json.loads(json.dumps(kwargs)))  # copia: o loop altera msgs
        return self.respostas.pop(0)


def usa(nome, entrada, uid="t1"):
    return {"stopReason": "tool_use", "output": {"message": {"role": "assistant", "content": [{"toolUse": {"toolUseId": uid, "name": nome, "input": entrada}}]}}}


def diz(texto):
    return {"stopReason": "end_turn", "output": {"message": {"role": "assistant", "content": [{"text": texto}]}}}


def pergunta(texto, historico=()):
    evento = {
        "version": "2.0",
        "routeKey": "POST /chat",
        "rawPath": "/chat",
        "rawQueryString": "",
        "headers": {"content-type": "application/json"},
        "requestContext": {
            "http": {"method": "POST", "path": "/chat", "sourceIp": "1.1.1.1"},
            "requestId": "r",
            "stage": "$default",
            "authorizer": {"jwt": {"claims": {"sub": "u-1"}, "scopes": None}},
        },
        "body": json.dumps({"mensagens": [*historico, {"role": "user", "texto": texto}]}),
        "isBase64Encoded": False,
    }
    r = chat.lambda_handler(evento, Ctx())
    return r["statusCode"], json.loads(r["body"])


@pytest.fixture
def socios():
    plano = criar_plano(3, 2500)
    _, a = pedido("POST", "/socios", dados_socio(plano["id"], nome="Leandro Silva"))
    _, b = pedido("POST", "/socios", dados_socio(plano["id"], nif=NIF_B, nome="Bruno Costa"))
    pedido("POST", f"/socios/{a['id']}/pagamentos", pagamento("2026-11", dataPagamento="2026-12-01"))
    return a, b


# ---------------------------------------------------------------- ferramentas
def test_procurar_socio_sem_acentos_e_sem_dados_pessoais(socios):
    r = chat.procurar_socio(nome="leandro")
    assert r["total"] == 1 and r["socios"][0]["nome"] == "Leandro Silva"
    assert "nif" not in json.dumps(r).lower() and "1990" not in json.dumps(r)


def test_ficha_socio_em_euros_e_sem_dados_pessoais(socios):
    a, _ = socios
    f = chat.ficha_socio(socio_id=a["id"])
    assert f["plano_atual"]["preco_mensal_eur"] == 25.0
    assert f["ultimos_pagamentos"] == [{"mes": "2026-11", "valor_eur": 25.0, "metodo": "MBWAY", "pago_em": "2026-12-01"}]
    assert [m["mes"] for m in f["meses_por_pagar_no_prazo"]] == ["2026-12", "2027-01"]
    texto = json.dumps(f)
    assert "123456789" not in texto and "1990-05-17" not in texto and "Rua X" not in texto


def test_atrasos_usam_as_mesmas_regras_que_o_ecra(socios):
    r = chat.pagamentos_em_atraso()
    _, ecra = pedido("GET", "/resumo/pagamentos")
    assert r["total_socios_em_atraso"] == len(ecra["atrasos"]) == 1
    assert r["socios"][0]["nome"] == "Bruno Costa" and r["total_em_atraso_eur"] == 25.0


def test_propor_pagamento_calcula_valor_e_nao_grava(socios):
    a, _ = socios
    propostas = []
    r = chat.propor_pagamento(socio_id=a["id"], mes="2026-12", metodo="DINHEIRO", _propostas=propostas)
    assert r["estado"] == "PROPOSTA_CRIADA_AGUARDA_CONFIRMACAO"
    assert propostas == [{
        "tipo": "pagamento", "socioId": a["id"], "nome": "Leandro Silva", "mes": "2026-12",
        "valor": 2500, "metodo": "DINHEIRO", "dataPagamento": "2027-01-05", "notas": "",
    }]
    _, ficha = pedido("GET", f"/socios/{a['id']}")
    assert [p["mes"] for p in ficha["pagamentos"]] == ["2026-11"]  # nada gravado


@pytest.mark.parametrize(
    "extra,mensagem",
    [
        ({"mes": "2026-11"}, "já está pago"),
        ({"mes": "2099-01"}, "adiantado"),
        ({"mes": "2025-12"}, "só entrou"),
        ({"metodo": "CARTAO"}, "metodo"),
        ({"data_pagamento": "2099-01-01"}, "futura"),
    ],
)
def test_propor_pagamento_invalido(socios, extra, mensagem):
    a, _ = socios
    res, ok = chat.executar("propor_pagamento", {"socio_id": a["id"], "mes": "2026-12", "metodo": "MBWAY", **extra}, [])
    assert not ok and mensagem in res["erro"]


def test_ferramenta_desconhecida_ou_socio_errado():
    assert chat.executar("apagar_tudo", {}, []) == ({"erro": "Ferramenta desconhecida: apagar_tudo"}, False)
    res, ok = chat.executar("ficha_socio", {"socio_id": "naoexiste"}, [])
    assert not ok and "procurar_socio" in res["erro"]


# ---------------------------------------------------------------- loop do agente
def test_fluxo_registar_pagamento(socios, monkeypatch):
    a, _ = socios
    modelo = ModeloFalso(
        usa("procurar_socio", {"nome": "leandro"}),
        usa("propor_pagamento", {"socio_id": a["id"], "mes": "2026-12", "metodo": "DINHEIRO"}, "t2"),
        diz("Preparei o registo. Confirma no cartão abaixo."),
    )
    monkeypatch.setattr(chat, "bedrock", lambda: modelo)

    s, r = pergunta("o leandro pagou dezembro em dinheiro")
    assert s == 200, r
    assert r["resposta"] == "Preparei o registo. Confirma no cartão abaixo."
    assert [(p["nome"], p["mes"], p["valor"], p["metodo"]) for p in r["propostas"]] == [("Leandro Silva", "2026-12", 2500, "DINHEIRO")]

    # o modelo recebeu a data de hoje e o resultado da 1.a ferramenta antes de decidir a 2.a
    assert "2027-01-05" in modelo.pedidos[0]["system"][0]["text"]
    resultado = modelo.pedidos[1]["messages"][-1]["content"][0]["toolResult"]
    assert resultado["status"] == "success" and resultado["content"][0]["json"]["socios"][0]["socio_id"] == a["id"]


def test_erro_de_ferramenta_volta_ao_modelo(socios, monkeypatch):
    modelo = ModeloFalso(usa("ficha_socio", {"socio_id": "naoexiste"}), diz("Não encontrei esse sócio."))
    monkeypatch.setattr(chat, "bedrock", lambda: modelo)
    s, r = pergunta("ficha do zé")
    assert s == 200 and r["propostas"] == []
    assert modelo.pedidos[1]["messages"][-1]["content"][0]["toolResult"]["status"] == "error"


def test_para_ao_fim_de_max_voltas(monkeypatch):
    modelo = ModeloFalso(*[usa("listar_planos", {}, f"t{i}") for i in range(chat.MAX_VOLTAS)])
    monkeypatch.setattr(chat, "bedrock", lambda: modelo)
    s, r = pergunta("planos?")
    assert s == 200 and "demasiados passos" in r["resposta"]
    assert len(modelo.pedidos) == chat.MAX_VOLTAS


def test_historico_alternado_e_validado(monkeypatch):
    modelo = ModeloFalso(diz("ok"))
    monkeypatch.setattr(chat, "bedrock", lambda: modelo)
    historico = [{"role": "assistant", "texto": "olá"}, {"role": "user", "texto": "a"}, {"role": "user", "texto": "b"}]
    s, _ = pergunta("c", historico)
    assert s == 200
    msgs = modelo.pedidos[0]["messages"]
    assert [m["role"] for m in msgs] == ["user"] and msgs[0]["content"][0]["text"] == "a\nb\nc"

    assert pergunta("x" * (chat.MAX_TEXTO + 1))[0] == 400


def test_limite_diario(monkeypatch):
    monkeypatch.setattr(chat, "LIMITE_DIA", 2)
    monkeypatch.setattr(chat, "bedrock", lambda: ModeloFalso(diz("ok")))
    assert pergunta("1")[0] == 200
    assert pergunta("2")[0] == 200
    s, r = pergunta("3")
    assert s == 429 and "Limite diário" in r["message"]


# ---------------------------------------------------------------- correcoes apos o 1.o uso real (Nova Lite)
@pytest.mark.parametrize(
    "bruto,limpo",
    [
        ("<thinking>The tool returned an error.</thinking>\n\nO teu cliente chama-se Leandro.", "O teu cliente chama-se Leandro."),
        ("Olá<thinking>a\nb</thinking> mundo", "Olá mundo"),
        ("Resposta.<thinking>raciocínio cortado sem fecho", "Resposta."),
        ("Sem tags.", "Sem tags."),
    ],
)
def test_limpar_raciocinio(bruto, limpo):
    assert chat.limpar(bruto) == limpo


def test_raciocinio_nao_chega_ao_ecra(monkeypatch):
    monkeypatch.setattr(chat, "bedrock", lambda: ModeloFalso(diz("<thinking>pensar em inglês</thinking>Tens 1 sócio.")))
    s, r = pergunta("quantos sócios?")
    assert s == 200 and r["resposta"] == "Tens 1 sócio."


def test_listar_socios(socios):
    r = chat.listar_socios()
    assert r["total"] == 2 and [x["nome"] for x in r["socios"]] == ["Bruno Costa", "Leandro Silva"]
    assert "123456789" not in json.dumps(r)
    assert chat.listar_socios(estado="INATIVO")["total"] == 0
    assert chat.executar("listar_socios", {"estado": "X"}, [])[1] is False


def test_aniversariantes(socios, monkeypatch):
    # dados_socio: nascimento 1990-05-17; hoje fixo e 2027-01-05
    assert chat.aniversariantes()["total"] == 0  # janeiro
    r = chat.aniversariantes(mes=5)
    assert [(x["nome"], x["dia"], x["faz_anos"]) for x in r["socios"]] == [("Bruno Costa", 17, 37), ("Leandro Silva", 17, 37)]
    assert "1990-05-17" not in json.dumps(r)  # so dia e idade, nao a data completa
    assert chat.executar("aniversariantes", {"mes": 13}, [])[1] is False


def test_system_prompt_obriga_a_usar_ferramentas():
    p = chat.system_prompt(date(2027, 1, 5))
    assert "usa primeiro uma ferramenta" in p and "Não tenho acesso a essa informação" in p
