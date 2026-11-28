"""Testes das regras de pagamentos/receita (backend/regras.py).

Funcoes puras: nao precisam de DynamoDB nem de moto. Cada caso-limite aqui
corresponde a uma decisao de negocio documentada no topo de regras.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import regras  # noqa: E402


def per(inicio, fim=None, preco=2500, nome="Mensal 3× semana", socio="s1"):
    p = {"socioId": socio, "dataInicio": inicio, "precoMensal": preco, "planoNome": nome}
    if fim:
        p["dataFim"] = fim
    return p


def pag(mes, valor=2500, data=None, socio="s1"):
    return {"socioId": socio, "mes": mes, "valor": valor, "metodo": "DINHEIRO", "dataPagamento": data or f"{mes}-05"}


def meses(lista):
    return [d["mes"] for d in lista]


# ---------------------------------------------------------------- datas
def test_prazo_e_dia_8_do_mes_seguinte():
    assert regras.prazo("2026-11") == "2026-12-08"
    assert regras.prazo("2026-12") == "2027-01-08"


def test_mes_anterior_atravessa_anos():
    assert regras.mes_anterior("2026-01") == "2025-12"
    assert regras.mes_anterior("2026-11", 11) == "2025-12"
    assert regras.mes_anterior("2026-03", 15) == "2024-12"


# ---------------------------------------------------------------- meses devidos
def test_so_cobra_a_partir_do_inicio_da_cobranca():
    assert meses(regras.meses_devidos([per("2026-05-10")], "2027-01")) == ["2026-11", "2026-12", "2027-01"]


def test_sem_periodos_nao_deve_nada():
    assert regras.meses_devidos([], "2027-01") == []


def test_entrada_a_meio_do_mes_deve_o_mes_inteiro():
    d = regras.meses_devidos([per("2026-12-20", preco=2300)], "2027-01")
    assert d == [
        {"mes": "2026-12", "valor": 2300, "planoNome": "Mensal 3× semana"},
        {"mes": "2027-01", "valor": 2300, "planoNome": "Mensal 3× semana"},
    ]


def test_mudanca_a_meio_do_mes_conta_so_o_ultimo_plano():
    periodos = [
        per("2026-11-01", "2026-11-15", preco=2100, nome="Mensal 1× semana"),
        per("2026-11-15", preco=2900, nome="Mensal 5× semana"),
    ]
    assert regras.meses_devidos(periodos, "2026-11") == [
        {"mes": "2026-11", "valor": 2900, "planoNome": "Mensal 5× semana"}
    ]


def test_inativo_deve_os_meses_em_que_teve_plano():
    # saiu a 3 de dezembro: deve novembro e dezembro, nao janeiro
    assert meses(regras.meses_devidos([per("2026-10-01", "2026-12-03")], "2027-01")) == ["2026-11", "2026-12"]


def test_data_fim_e_exclusiva():
    # saiu a 1 de dezembro: ultimo dia com plano foi 30 de novembro
    assert meses(regras.meses_devidos([per("2026-10-01", "2026-12-01")], "2027-01")) == ["2026-11"]


def test_reativado_nao_deve_meses_em_que_esteve_fora():
    periodos = [per("2026-11-01", "2026-12-01"), per("2027-02-10")]
    assert meses(regras.meses_devidos(periodos, "2027-02")) == ["2026-11", "2027-02"]


# ---------------------------------------------------------------- situacao
def test_no_dia_8_ainda_esta_no_prazo_e_no_dia_9_em_atraso():
    periodos = [per("2026-11-01")]
    s8 = regras.situacao(periodos, [], "2026-12-08")
    assert meses(s8["emAtraso"]) == []
    assert meses(s8["dentroDoPrazo"]) == ["2026-11", "2026-12"]
    s9 = regras.situacao(periodos, [], "2026-12-09")
    assert meses(s9["emAtraso"]) == ["2026-11"]
    assert meses(s9["dentroDoPrazo"]) == ["2026-12"]


def test_meses_pagos_nao_contam():
    s = regras.situacao([per("2026-11-01")], [pag("2026-11")], "2027-01-20")
    assert meses(s["emAtraso"]) == ["2026-12"]
    assert meses(s["dentroDoPrazo"]) == ["2027-01"]


def test_pagamento_adiantado_tira_o_mes_seguinte():
    s = regras.situacao([per("2026-11-01")], [pag("2026-11"), pag("2026-12")], "2026-11-28")
    assert s == {"emAtraso": [], "dentroDoPrazo": []}


# ---------------------------------------------------------------- resumo do inicio
def test_resumo_pagamentos():
    socios = [
        {"id": "a", "nome": "Ana", "estado": "ATIVO"},
        {"id": "b", "nome": "Bruno", "estado": "INATIVO"},
        {"id": "c", "nome": "Carla", "estado": "ATIVO"},
        {"id": "d", "nome": "Duarte", "estado": "ATIVO"},
    ]
    periodos = [
        per("2026-11-01", socio="a", preco=2100),  # deve nov (atraso) + dez (no prazo) + jan (mes atual)
        per("2026-11-01", "2026-12-01", socio="b", preco=3000),  # inativo: deve nov, em atraso
        per("2026-11-01", socio="c", preco=2500),  # pagou tudo
        per("2026-12-05", socio="d", preco=2300),  # deve dez, ainda no prazo
    ]
    pagamentos = [
        pag("2026-11", 2500, "2026-11-30", socio="c"),
        pag("2026-12", 2500, "2027-01-02", socio="c"),  # pago em janeiro: conta no recebido do mes
        pag("2027-01", 2500, "2027-01-03", socio="c"),
    ]
    r = regras.resumo_pagamentos(socios, periodos, pagamentos, "2027-01-05")

    # Bruno deve mais (3000) que Ana (2100) no mesmo mes mais antigo -> primeiro
    assert [a["nome"] for a in r["atrasos"]] == ["Bruno", "Ana"]
    assert r["atrasos"][0]["estado"] == "INATIVO"
    assert r["totalAtraso"] == 5100
    assert r["recebidoMes"] == 5000 and r["nRecebidoMes"] == 2
    assert r["mesAnterior"] == "2026-12"
    # dezembro dentro do prazo: Ana (2100) + Duarte (2300); janeiro (mes atual) nao conta
    assert r["dentroDoPrazo"] == 2 and r["valorDentroDoPrazo"] == 4400


def test_resumo_sem_socios():
    r = regras.resumo_pagamentos([], [], [], "2026-11-28")
    assert r["atrasos"] == [] and r["totalAtraso"] == 0 and r["recebidoMes"] == 0


# ---------------------------------------------------------------- receita prevista
def test_receita_prevista_mostra_pelo_menos_6_meses():
    periodos = [per("2026-11-10", socio="a", preco=2100), per("2026-11-20", socio="b", preco=3000)]
    linhas = regras.receita_prevista_por_mes(periodos, "2026-11-28")
    assert [l["mes"] for l in linhas] == ["2026-06", "2026-07", "2026-08", "2026-09", "2026-10", "2026-11"]
    assert linhas[-1] == {"mes": "2026-11", "receita": 5100, "socios": 2}
    assert all(l["receita"] == 0 for l in linhas[:-1])


def test_receita_prevista_corta_meses_vazios_e_conta_ultimo_plano():
    periodos = [
        per("2025-12-01", "2026-03-15", socio="a", preco=2100),
        per("2026-03-15", socio="a", preco=2900),
        per("2026-02-01", "2026-04-01", socio="b", preco=2500),
    ]
    linhas = regras.receita_prevista_por_mes(periodos, "2026-11-28")
    assert linhas[0]["mes"] == "2025-12"  # primeiro mes com socios (12 meses atras)
    por_mes = {l["mes"]: l for l in linhas}
    assert por_mes["2026-03"] == {"mes": "2026-03", "receita": 2900 + 2500, "socios": 2}
    assert por_mes["2026-04"] == {"mes": "2026-04", "receita": 2900, "socios": 1}  # b saiu a 1 de abril


def test_situacao_inclui_prazo_de_cada_mes():
    s = regras.situacao([per("2026-11-01")], [], "2026-12-20")
    assert s["emAtraso"][0]["prazo"] == "2026-12-08"
    assert s["dentroDoPrazo"][0] == {"mes": "2026-12", "valor": 2500, "planoNome": "Mensal 3× semana", "prazo": "2027-01-08"}


# ---------------------------------------------------------------- recebido por metodo
def test_recebido_por_metodo_ultimos_12_meses_pela_data_de_pagamento():
    pagamentos = [
        {**pag("2025-11", 2100, "2025-11-30"), "metodo": "MBWAY"},  # 12 meses + 1: fica de fora
        {**pag("2025-11", 2200, "2025-12-01"), "metodo": "MBWAY"},  # mes antigo pago dentro da janela: conta
        {**pag("2026-11", 2500, "2026-11-03"), "metodo": "DINHEIRO"},
        {**pag("2026-12", 2500, "2026-11-20"), "metodo": "DINHEIRO"},  # adiantado
    ]
    r = regras.recebido_por_metodo(pagamentos, "2026-11-28")
    assert r["desde"] == "2025-12-01"
    assert r["metodos"] == [
        {"metodo": "MBWAY", "valor": 2200, "n": 1},
        {"metodo": "DINHEIRO", "valor": 5000, "n": 2},
    ]


def test_recebido_por_mes_pela_data_de_pagamento():
    pagamentos = [
        pag("2026-10", 2100, "2026-11-02"),  # outubro pago em novembro: conta em novembro
        pag("2026-11", 2500, "2026-11-20"),
        pag("2026-09", 2500, "2026-09-05"),
        pag("2025-10", 9999, "2025-10-05"),  # fora da janela de 3 meses
    ]
    assert regras.recebido_por_mes(pagamentos, "2026-11-28", meses=3) == [
        {"mes": "2026-09", "valor": 2500, "n": 1},
        {"mes": "2026-10", "valor": 0, "n": 0},
        {"mes": "2026-11", "valor": 4600, "n": 2},
    ]
