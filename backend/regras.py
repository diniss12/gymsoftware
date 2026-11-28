"""Regras de negocio de pagamentos e receita: a UNICA definicao.

Portado de frontend/src/util.js (mesesDevidos, situacao) e das paginas
Inicio/Estatisticas. Usado pela API (endpoints de resumo) e pelo chat, para o
ecra e o chatbot darem sempre os mesmos numeros. Funcoes puras: recebem listas
ja lidas do DynamoDB e a data de hoje; nao fazem pedidos.

Regras:
- A mensalidade do mes M vence no dia DIA_LIMITE do mes M+1; depois fica em atraso.
- Um socio deve um mes se teve um plano em vigor em pelo menos um dia desse mes
  (quem entra a meio do mes paga o mes inteiro). Inativos continuam a dever os
  meses em que tiveram plano.
- O valor do mes e o preco do ULTIMO plano em vigor nesse mes (se mudou a meio,
  conta o ultimo; nunca conta duas vezes).
- So se cobra a partir de INICIO_COBRANCA (meses anteriores nunca sao divida).
- Periodos: dataFim e exclusiva (= inicio do periodo seguinte / data de saida).
- Valores em centimos (int).
"""

from validacao import METODOS, mes_seguinte

INICIO_COBRANCA = "2026-11"
DIA_LIMITE = 8


def mes_anterior(mes: str, n: int = 1) -> str:
    y, m = int(mes[:4]), int(mes[5:7]) - n
    while m < 1:
        y, m = y - 1, m + 12
    return f"{y}-{m:02d}"


def prazo(mes: str) -> str:
    """Data limite de pagamento da mensalidade: '2026-07' -> '2026-08-08'."""
    return f"{mes_seguinte(mes)}-{DIA_LIMITE:02d}"


def plano_do_mes(periodos: list[dict], mes: str) -> dict | None:
    """Ultimo periodo em vigor em algum dia do mes, ou None se nao teve plano."""
    inicio, seguinte = f"{mes}-01", f"{mes_seguinte(mes)}-01"
    no_mes = [p for p in periodos if p["dataInicio"] < seguinte and (not p.get("dataFim") or p["dataFim"] > inicio)]
    # max() devolve o primeiro em caso de empate, como o reduce do frontend
    return max(no_mes, key=lambda p: p["dataInicio"]) if no_mes else None


def meses_devidos(periodos: list[dict], ate: str) -> list[dict]:
    """Meses a pagar desde INICIO_COBRANCA (ou da entrada) ate `ate` (AAAA-MM, inclusive)."""
    if not periodos:
        return []
    primeiro = min(p["dataInicio"] for p in periodos)[:7]
    mes = max(primeiro, INICIO_COBRANCA)
    devidos = []
    while mes <= ate:
        p = plano_do_mes(periodos, mes)
        if p:
            devidos.append({"mes": mes, "valor": p["precoMensal"], "planoNome": p["planoNome"]})
        mes = mes_seguinte(mes)
    return devidos


def situacao(periodos: list[dict], pagamentos: list[dict], hoje: str) -> dict:
    """Meses por pagar de um socio, separados pelo prazo. `hoje` em AAAA-MM-DD.
    Cada mes leva o seu `prazo` (data limite), para o ecra nao ter de o calcular."""
    pagos = {p["mes"] for p in pagamentos}
    por_pagar = [{**d, "prazo": prazo(d["mes"])} for d in meses_devidos(periodos, hoje[:7]) if d["mes"] not in pagos]
    return {
        "emAtraso": [d for d in por_pagar if prazo(d["mes"]) < hoje],
        "dentroDoPrazo": [d for d in por_pagar if prazo(d["mes"]) >= hoje],
    }


def _agrupar(lista: list[dict], chave: str) -> dict[str, list[dict]]:
    g: dict[str, list[dict]] = {}
    for x in lista:
        g.setdefault(x[chave], []).append(x)
    return g


def resumo_pagamentos(socios: list[dict], periodos: list[dict], pagamentos: list[dict], hoje: str) -> dict:
    """Painel do Inicio: quem esta em atraso, o que entrou este mes e o que do
    mes anterior ainda esta dentro do prazo.

    `periodos` e `pagamentos` de todos os socios (com socioId). `pagamentos`
    deve incluir todos os pagamentos com dataPagamento no mes atual, seja qual
    for o mes a que se referem.
    """
    mes_atual = hoje[:7]
    periodos_de = _agrupar(periodos, "socioId")
    pagamentos_de = _agrupar(pagamentos, "socioId")

    atrasos = []
    n_dentro, valor_dentro = 0, 0
    for s in socios:
        sit = situacao(periodos_de.get(s["id"], []), pagamentos_de.get(s["id"], []), hoje)
        if sit["emAtraso"]:
            atrasos.append({
                "socioId": s["id"],
                "nome": s["nome"],
                "estado": s["estado"],
                "meses": sit["emAtraso"],
                "total": sum(d["valor"] for d in sit["emAtraso"]),
            })
        # So o mes anterior ainda no prazo (o mes atual ainda esta a decorrer).
        for d in sit["dentroDoPrazo"]:
            if d["mes"] < mes_atual:
                n_dentro += 1
                valor_dentro += d["valor"]
    # Mais antigo primeiro; no mesmo mes, maior divida primeiro.
    atrasos.sort(key=lambda a: (a["meses"][0]["mes"], -a["total"]))

    do_mes = [p for p in pagamentos if p["dataPagamento"].startswith(mes_atual)]
    return {
        "hoje": hoje,
        "atrasos": atrasos,
        "totalAtraso": sum(a["total"] for a in atrasos),
        "recebidoMes": sum(p["valor"] for p in do_mes),
        "nRecebidoMes": len(do_mes),
        "mesAnterior": mes_anterior(mes_atual),
        "prazoMesAnterior": prazo(mes_anterior(mes_atual)),
        "dentroDoPrazo": n_dentro,
        "valorDentroDoPrazo": valor_dentro,
        "diaLimite": DIA_LIMITE,
    }


def recebido_por_mes(pagamentos: list[dict], hoje: str, meses: int = 12) -> list[dict]:
    """Valor RECEBIDO em cada um dos ultimos `meses` meses, pela dataPagamento
    (o dinheiro que entrou nesse mes, seja de que mensalidade for)."""
    lista = [mes_anterior(hoje[:7], i) for i in range(meses - 1, -1, -1)]
    linhas = {m: {"mes": m, "valor": 0, "n": 0} for m in lista}
    for p in pagamentos:
        linha = linhas.get(p["dataPagamento"][:7])
        if linha and p["dataPagamento"] <= hoje:
            linha["valor"] += p["valor"]
            linha["n"] += 1
    return [linhas[m] for m in lista]


def recebido_por_metodo(pagamentos: list[dict], hoje: str, meses: int = 12) -> dict:
    """Valor RECEBIDO (pela dataPagamento) nos ultimos `meses` meses, incluindo
    o atual, por metodo de pagamento."""
    desde = f"{mes_anterior(hoje[:7], meses - 1)}-01"
    recentes = [p for p in pagamentos if desde <= p["dataPagamento"] <= hoje]
    return {
        "desde": desde,
        "metodos": [
            {
                "metodo": m,
                "valor": sum(p["valor"] for p in recentes if p["metodo"] == m),
                "n": sum(1 for p in recentes if p["metodo"] == m),
            }
            for m in METODOS
        ],
    }


def receita_prevista_por_mes(periodos: list[dict], hoje: str, n: int = 12) -> list[dict]:
    """Receita PREVISTA pelos planos em cada um dos ultimos `n` meses (nao a
    recebida). Corta os meses iniciais sem socios, mas devolve pelo menos 6."""
    meses = [mes_anterior(hoje[:7], i) for i in range(n - 1, -1, -1)]
    periodos_de = _agrupar(periodos, "socioId")
    linhas = []
    for mes in meses:
        receita, socios = 0, 0
        for lista in periodos_de.values():
            p = plano_do_mes(lista, mes)
            if p:
                receita += p["precoMensal"]
                socios += 1
        linhas.append({"mes": mes, "receita": receita, "socios": socios})
    primeiro = next((i for i, l in enumerate(linhas) if l["socios"] > 0), n)
    return linhas[min(primeiro, n - 6):]
