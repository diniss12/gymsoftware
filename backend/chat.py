"""Assistente de chat do gymsoftware: uma Lambda propria (POST /chat).

Corre com um role SO DE LEITURA na tabela (mais um contador diario): o modelo
nunca grava nada. Para registar um pagamento, a ferramenta `propor_pagamento`
devolve uma PROPOSTA; o frontend mostra-a num cartao e so ao carregar em
"Confirmar" chama a API normal (POST /socios/{id}/pagamentos), com o token do
dono e as validacoes de sempre.

Modelo via Bedrock Converse API (igual para qualquer modelo: trocar de modelo
e mudar o parametro ChatModelId no template). Os numeros vem SEMPRE das
ferramentas (regras.py / repo.py), ja em euros: o modelo nao faz contas.

Dados pessoais: as ferramentas nao devolvem NIF, data de nascimento nem
morada. O perfil de inferencia "eu." mantem o processamento na UE.
"""

import json
import os
import re
from datetime import date
from functools import cache

import boto3
from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver, Response
from aws_lambda_powertools.logging import correlation_paths
from aws_lambda_powertools.utilities.typing import LambdaContext
from botocore.exceptions import ClientError

import regras
import repo
import validacao as v
from validacao import ErroApi, normalizar

logger = Logger()
app = APIGatewayHttpResolver()

MODELO = os.environ.get("MODEL_ID", "eu.amazon.nova-lite-v1:0")
LIMITE_DIA = int(os.environ.get("CHAT_LIMITE_DIA", "50"))  # travao de custos
MAX_VOLTAS = 5  # chamadas ao modelo por pergunta (cada ferramenta usada = +1)
MAX_MENSAGENS = 20  # historico enviado ao modelo
MAX_TEXTO = 2000  # caracteres por mensagem
MAX_LISTA = 30  # linhas por resultado de ferramenta: o modelo nunca recebe os 300 socios

DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
METODOS_TXT = {"MBWAY": "MB WAY", "DINHEIRO": "dinheiro"}


@cache
def bedrock():
    return boto3.client("bedrock-runtime")


@app.exception_handler(ErroApi)
def _erro_api(e: ErroApi):
    return Response(
        status_code=e.status,
        content_type="application/json",
        body=json.dumps({"message": e.mensagem}, ensure_ascii=False),
    )


def eur(centimos) -> float:
    """Centimos -> euros, arredondado aqui (e nao pelo modelo)."""
    return round(int(centimos) / 100, 2)


# ================================================================ ferramentas
def _planos_por_id() -> dict:
    return {p["id"]: p for p in repo.listar_planos()}


def _carregar_socio(socio_id) -> tuple[dict, list[dict], list[dict]]:
    if not isinstance(socio_id, str) or not socio_id:
        raise ErroApi(400, "Falta o socio_id (usa procurar_socio primeiro).")
    r = repo.obter_socio_completo(socio_id)
    if not r:
        raise ErroApi(404, "Sócio não encontrado. Usa procurar_socio para obter o id certo.")
    return r


def procurar_socio(nome: str = "", **_) -> dict:
    termo = normalizar((nome or "").strip())
    if len(termo) < 2:
        raise ErroApi(400, "Indica pelo menos 2 letras do nome.")
    planos = _planos_por_id()
    encontrados = [s for s in repo.listar_socios() if termo in normalizar(s["nome"])]
    return {
        "total": len(encontrados),
        "socios": [
            {
                "socio_id": s["id"],
                "nome": s["nome"],
                "estado": s["estado"],
                "plano": planos.get(s.get("planoId"), {}).get("nome"),
                "socio_desde": s["dataEntrada"],
            }
            for s in encontrados[:10]
        ],
        "truncado": len(encontrados) > 10,
    }


def listar_socios(estado: str = "ATIVO", **_) -> dict:
    estado = (estado or "ATIVO").upper()
    if estado not in ("ATIVO", "INATIVO", "TODOS"):
        raise ErroApi(400, "estado tem de ser ATIVO, INATIVO ou TODOS.")
    planos = _planos_por_id()
    lista = [s for s in repo.listar_socios() if estado == "TODOS" or s["estado"] == estado]
    return {
        "estado": estado,
        "total": len(lista),
        "socios": [
            {"socio_id": s["id"], "nome": s["nome"], "estado": s["estado"], "plano": planos.get(s.get("planoId"), {}).get("nome")}
            for s in lista[:MAX_LISTA]
        ],
        "truncado": len(lista) > MAX_LISTA,
    }


def ficha_socio(socio_id: str = "", **_) -> dict:
    socio, periodos, pagamentos = _carregar_socio(socio_id)
    sit = regras.situacao(periodos, pagamentos, v.hoje().isoformat())
    atual = next((p for p in periodos if p["id"] == socio.get("periodoAtual")), None)

    def mes_eur(d):
        return {"mes": d["mes"], "valor_eur": eur(d["valor"]), "prazo": d["prazo"]}

    return {
        "socio_id": socio["id"],
        "nome": socio["nome"],
        "estado": socio["estado"],
        "socio_desde": socio["dataEntrada"],
        "data_saida": socio.get("dataSaida"),
        "plano_atual": atual
        and {"nome": atual["planoNome"], "preco_mensal_eur": eur(atual["precoMensal"]), "desde": atual["dataInicio"]},
        "historico_planos": [
            {"plano": p["planoNome"], "preco_eur": eur(p["precoMensal"]), "inicio": p["dataInicio"], "fim": p.get("dataFim")}
            for p in periodos
        ],
        "ultimos_pagamentos": [
            {"mes": p["mes"], "valor_eur": eur(p["valor"]), "metodo": p["metodo"], "pago_em": p["dataPagamento"]}
            for p in pagamentos[-12:]
        ],
        "meses_em_atraso": [mes_eur(d) for d in sit["emAtraso"]],
        "meses_por_pagar_no_prazo": [mes_eur(d) for d in sit["dentroDoPrazo"]],
    }


def pagamentos_em_atraso(**_) -> dict:
    r = regras.resumo_pagamentos(
        repo.listar_socios(), repo.listar_periodos(), repo.listar_pagamentos("0000-00"), v.hoje().isoformat()
    )
    return {
        "regra": f"A mensalidade de cada mês pode ser paga até ao dia {r['diaLimite']} do mês seguinte; depois fica em atraso.",
        "total_socios_em_atraso": len(r["atrasos"]),
        "total_em_atraso_eur": eur(r["totalAtraso"]),
        "socios": [
            {
                "socio_id": a["socioId"],
                "nome": a["nome"],
                "estado": a["estado"],
                "meses": [{"mes": d["mes"], "valor_eur": eur(d["valor"])} for d in a["meses"]],
                "total_eur": eur(a["total"]),
            }
            for a in r["atrasos"][:MAX_LISTA]
        ],
        "truncado": len(r["atrasos"]) > MAX_LISTA,
        "recebido_este_mes_eur": eur(r["recebidoMes"]),
        "pagamentos_este_mes": r["nRecebidoMes"],
        "mes_anterior": r["mesAnterior"],
        "mes_anterior_por_pagar_ainda_no_prazo": {
            "socios": r["dentroDoPrazo"],
            "valor_eur": eur(r["valorDentroDoPrazo"]),
            "prazo": r["prazoMesAnterior"],
        },
    }


def _comparar(serie: dict, inicio: str, fim: str) -> dict:
    """Diferenca e variacao entre dois meses, calculadas aqui (o modelo nao faz contas)."""
    a, b = serie.get(inicio), serie.get(fim)
    if a is None or b is None:
        return {"erro": "mês fora dos últimos 12 meses"}
    return {
        "inicio_eur": eur(a),
        "fim_eur": eur(b),
        "diferenca_eur": eur(b - a),
        "variacao_percentual": round((b - a) / a * 100, 1) if a else None,
    }


def receita(mes_inicio: str = "", mes_fim: str = "", **_) -> dict:
    hoje = v.hoje().isoformat()
    pagamentos = repo.listar_pagamentos("0000-00")
    metodos = regras.recebido_por_metodo(pagamentos, hoje)
    recebido = regras.recebido_por_mes(pagamentos, hoje)
    prevista = regras.receita_prevista_por_mes(repo.listar_periodos(), hoje)
    comparacao = None
    if mes_inicio or mes_fim:
        inicio = v.mes({"mes_inicio": mes_inicio}, "mes_inicio")
        fim = v.mes({"mes_fim": mes_fim or hoje[:7]}, "mes_fim")
        comparacao = {
            "de": inicio,
            "ate": fim,
            "prevista": _comparar({l["mes"]: l["receita"] for l in prevista}, inicio, fim),
            "recebida": _comparar({l["mes"]: l["valor"] for l in recebido}, inicio, fim),
        }
    return {
        "comparacao": comparacao,
        "nota": "prevista = soma dos planos em vigor em cada mês (é a 'Receita por mês' do ecrã Estatísticas); "
        "recebida = dinheiro que entrou em cada mês (pagamentos, pela data de pagamento).",
        "prevista_por_mes": [
            {"mes": l["mes"], "valor_eur": eur(l["receita"]), "socios": l["socios"]} for l in prevista
        ],
        "recebida_por_mes": [
            {"mes": l["mes"], "valor_eur": eur(l["valor"]), "pagamentos": l["n"]} for l in recebido
        ],
        "recebido_ultimos_12_meses_por_metodo": {
            "desde": metodos["desde"],
            "metodos": [{"metodo": m["metodo"], "valor_eur": eur(m["valor"]), "pagamentos": m["n"]} for m in metodos["metodos"]],
        },
    }


def resumo_socios(**_) -> dict:
    socios = repo.listar_socios()
    planos = _planos_por_id()
    ativos = [s for s in socios if s["estado"] == "ATIVO"]
    por_plano: dict[str, int] = {}
    for s in ativos:
        nome = planos.get(s.get("planoId"), {}).get("nome", "?")
        por_plano[nome] = por_plano.get(nome, 0) + 1
    hoje = v.hoje().isoformat()
    meses = [regras.mes_anterior(hoje[:7], i) for i in range(11, -1, -1)]
    return {
        "ativos": len(ativos),
        "inativos": len(socios) - len(ativos),
        "ativos_por_plano": por_plano,
        "por_mes": [
            {
                "mes": m,
                "entradas": sum(1 for s in socios if s["dataEntrada"].startswith(m)),
                "saidas": sum(1 for s in socios if (s.get("dataSaida") or "").startswith(m)),
            }
            for m in meses
        ],
    }


def socios_por_localidade(localidade: str = "", **_) -> dict:
    """Socios ATIVOS por localidade, agrupados como nas Estatisticas
    (sem maiusculas/acentos: 'felgueiras' = 'Felgueiras')."""
    grupos: dict[str, dict] = {}
    for s in repo.listar_socios():
        if s["estado"] != "ATIVO":
            continue
        nome_loc = (s.get("localidade") or "").strip() or "Sem localidade"
        g = grupos.setdefault(normalizar(nome_loc), {"localidade": nome_loc, "socios": []})
        g["socios"].append(s)
    termo = normalizar((localidade or "").strip())
    if not termo:
        lista = sorted(grupos.values(), key=lambda g: -len(g["socios"]))
        return {"total_ativos": sum(len(g["socios"]) for g in lista),
                "por_localidade": [{"localidade": g["localidade"], "ativos": len(g["socios"])} for g in lista]}
    escolhidos = [g for k, g in grupos.items() if termo == k] or [g for k, g in grupos.items() if termo in k]
    socios = [s for g in escolhidos for s in g["socios"]]
    return {
        "procurado": localidade,
        "localidades_encontradas": [g["localidade"] for g in escolhidos],
        "total_ativos": len(socios),
        "socios": [{"socio_id": s["id"], "nome": s["nome"]} for s in socios[:MAX_LISTA]],
        "truncado": len(socios) > MAX_LISTA,
    }


def aniversariantes(mes=None, **_) -> dict:
    """Socios ATIVOS que fazem anos no mes (como nas Estatisticas). Devolve o
    dia e a idade que fazem, nao a data de nascimento completa."""
    hoje = v.hoje()
    try:
        mes = int(mes) if mes not in (None, "") else hoje.month
    except (TypeError, ValueError):
        raise ErroApi(400, "mes tem de ser um número de 1 a 12.") from None
    if not 1 <= mes <= 12:
        raise ErroApi(400, "mes tem de ser um número de 1 a 12.")
    lista = sorted(
        (
            {"nome": s["nome"], "socio_id": s["id"], "dia": int(s["dataNascimento"][8:10]),
             "faz_anos": hoje.year - int(s["dataNascimento"][:4])}
            for s in repo.listar_socios()
            if s["estado"] == "ATIVO" and int(s["dataNascimento"][5:7]) == mes
        ),
        key=lambda x: x["dia"],
    )
    return {"mes": mes, "total": len(lista), "socios": lista[:MAX_LISTA], "truncado": len(lista) > MAX_LISTA}


def listar_planos(**_) -> dict:
    return {
        "planos": [
            {
                "nome": p["nome"],
                "preco_mensal_eur": eur(p["precoMensal"]),
                "vezes_por_semana": p.get("vezesPorSemana"),
                "disponivel": p["ativo"],
            }
            for p in repo.listar_planos()
        ]
    }


def propor_pagamento(socio_id: str = "", mes: str = "", metodo: str = "", data_pagamento: str = "", valor_eur=None, notas: str = "", _propostas=None, **_) -> dict:
    """Valida tudo o que a API vai validar e devolve uma proposta; NAO grava."""
    socio, periodos, pagamentos = _carregar_socio(socio_id)
    mes = v.mes({"mes": mes}, "mes")
    if metodo not in v.METODOS:
        raise ErroApi(400, "metodo tem de ser MBWAY ou DINHEIRO; pergunta ao utilizador se não o disse.")
    data = v.nao_futura(v.data({"d": data_pagamento}, "d", padrao=v.hoje()), "data_pagamento").isoformat()
    if mes < socio["dataEntrada"][:7]:
        raise ErroApi(400, f"O sócio só entrou em {socio['dataEntrada']}: não pode pagar {mes}.")
    if mes > v.mes_seguinte(v.hoje().isoformat()[:7]):
        raise ErroApi(400, "Só se pode pagar adiantado até ao mês seguinte.")
    if any(p["mes"] == mes for p in pagamentos):
        raise ErroApi(409, f"{mes} já está pago por este sócio.")

    if valor_eur is None:
        plano = regras.plano_do_mes(periodos, mes)
        if not plano:
            raise ErroApi(400, f"O sócio não tinha plano em {mes}: pergunta ao utilizador o valor.")
        valor = plano["precoMensal"]
    else:
        try:
            valor = round(float(valor_eur) * 100)
        except (TypeError, ValueError):
            raise ErroApi(400, "valor_eur inválido.") from None
        if not 0 <= valor <= 100_000:
            raise ErroApi(400, "valor_eur fora do intervalo permitido.")

    proposta = {
        "tipo": "pagamento",
        "socioId": socio["id"],
        "nome": socio["nome"],
        "mes": mes,
        "valor": valor,  # centimos: o que o frontend envia a API
        "metodo": metodo,
        "dataPagamento": data,
        "notas": (notas or "")[:500],
    }
    if _propostas is not None:
        _propostas.append(proposta)
    return {
        "estado": "PROPOSTA_CRIADA_AGUARDA_CONFIRMACAO",
        "importante": "NADA foi registado. O utilizador tem de carregar em Confirmar no cartão que aparece no ecrã.",
        "resumo": f"{socio['nome']} · {mes} · {eur(valor):.2f} € · {METODOS_TXT[metodo]} · pago em {data}",
    }


def _S(props: dict, req=()) -> dict:
    """JSON Schema dos parametros de uma ferramenta ("required" so se houver)."""
    schema = {"type": "object", "properties": props}
    if req:
        schema["required"] = list(req)
    return schema

FERRAMENTAS = {
    "procurar_socio": (procurar_socio, "Procura sócios pelo nome (ou parte do nome, sem acentos). Devolve socio_id, nome, estado e plano. Usa sempre antes de ficha_socio ou propor_pagamento.",
                       _S({"nome": {"type": "string", "description": "Nome ou parte do nome"}}, ["nome"])),
    "listar_socios": (listar_socios, "Lista os sócios (clientes) por ordem alfabética: nomes, estado e plano (máx. 30). Usa para perguntas como 'quem são os meus clientes' ou 'como se chama o meu cliente'.",
                      _S({"estado": {"type": "string", "enum": ["ATIVO", "INATIVO", "TODOS"], "description": "Por omissão ATIVO"}})),
    "ficha_socio": (ficha_socio, "Ficha de um sócio: plano atual, histórico de planos, últimos pagamentos e meses em atraso / por pagar.",
                    _S({"socio_id": {"type": "string"}}, ["socio_id"])),
    "pagamentos_em_atraso": (pagamentos_em_atraso, "Todos os sócios com mensalidades em atraso (com valores), quanto entrou este mês e o que do mês anterior ainda está no prazo.", _S({})),
    "receita": (receita, "Receita prevista (planos) e recebida (pagamentos) por mês nos últimos 12 meses, e recebida por método. "
                "Para comparar dois meses (crescimento, diferença), passa mes_inicio e mes_fim: a diferença e a percentagem vêm já calculadas em 'comparacao'.",
                _S({"mes_inicio": {"type": "string", "description": "AAAA-MM"}, "mes_fim": {"type": "string", "description": "AAAA-MM; omite para o mês atual"}})),
    "resumo_socios": (resumo_socios, "Número de sócios ativos e inativos, ativos por plano, e entradas/saídas por mês (12 meses).", _S({})),
    "socios_por_localidade": (socios_por_localidade, "Sócios ativos por localidade. Sem parâmetro: contagem de cada localidade. Com localidade: quantos e quais os sócios dessa localidade.",
                              _S({"localidade": {"type": "string", "description": "Ex.: Lousada; omite para ver todas"}})),
    "aniversariantes": (aniversariantes, "Sócios ativos que fazem anos num mês (por omissão o mês atual): nome, dia e idade que fazem.",
                        _S({"mes": {"type": "integer", "description": "1 a 12; omite para o mês atual"}})),
    "listar_planos": (listar_planos, "Planos do ginásio com preço mensal e vezes por semana.", _S({})),
    "propor_pagamento": (propor_pagamento,
                         "Prepara o registo do pagamento de uma mensalidade para o utilizador CONFIRMAR no ecrã. Não grava nada. "
                         "O valor é calculado automaticamente pelo plano do mês; só indica valor_eur se o utilizador disser um valor diferente.",
                         _S({
                             "socio_id": {"type": "string"},
                             "mes": {"type": "string", "description": "Mês da mensalidade, AAAA-MM"},
                             "metodo": {"type": "string", "enum": list(v.METODOS)},
                             "data_pagamento": {"type": "string", "description": "AAAA-MM-DD; omite se foi hoje"},
                             "valor_eur": {"type": "number", "description": "Só se o utilizador indicar um valor diferente do plano"},
                             "notas": {"type": "string"},
                         }, ["socio_id", "mes", "metodo"])),
}

TOOL_CONFIG = {
    "tools": [
        {"toolSpec": {"name": nome, "description": desc, "inputSchema": {"json": schema}}}
        for nome, (_, desc, schema) in FERRAMENTAS.items()
    ]
}


def executar(nome: str, entrada: dict, propostas: list) -> tuple[dict, bool]:
    """Corre uma ferramenta; devolve (resultado, ok). Erros voltam ao modelo como texto."""
    if nome not in FERRAMENTAS:
        return {"erro": f"Ferramenta desconhecida: {nome}"}, False
    fn = FERRAMENTAS[nome][0]
    try:
        extra = {"_propostas": propostas} if nome == "propor_pagamento" else {}
        return fn(**(entrada or {}), **extra), True
    except ErroApi as e:
        return {"erro": e.mensagem}, False
    except TypeError:
        return {"erro": "Parâmetros inválidos para esta ferramenta."}, False


# ================================================================ modelo
def system_prompt(hoje: date) -> str:
    return f"""És o assistente da área de gestão do ginásio Ativo Fitness. Falas com o dono do ginásio.

Responde SEMPRE em português de Portugal, mesmo que os resultados das ferramentas, os erros ou o teu raciocínio estejam noutra língua.

Hoje é {DIAS[hoje.weekday()]}, {hoje.isoformat()}.

Regras:
- Para QUALQUER pergunta sobre sócios, pagamentos, planos, receita ou aniversários, usa primeiro uma ferramenta. Nunca respondas de memória nem por suposição.
- Responde só com base nos resultados das ferramentas. Nunca inventes nomes, números, valores ou datas. Se nenhuma ferramenta tiver a informação, responde "Não tenho acesso a essa informação." em vez de adivinhar.
- Nunca digas que há zero, nenhum ou "não tenho clientes" sem uma ferramenta o ter devolvido.
- Os valores já vêm em euros (campos *_eur): usa-os tal como vêm. Nunca faças contas (somas, diferenças, percentagens): se precisares de uma, usa os parâmetros da ferramenta que a calcula (ex.: receita com mes_inicio e mes_fim). Escreve euros como 23,00 €.
- "Receita" tem duas medidas: a PREVISTA (soma dos planos; é a que aparece no gráfico "Receita por mês" das Estatísticas) e a RECEBIDA (pagamentos registados). Se o utilizador disser só "receita", usa a prevista e diz que é a prevista; podes acrescentar a recebida numa segunda frase. Diz sempre qual das duas estás a usar.
- Respostas curtas e diretas, só com a resposta final, sem etiquetas XML (nada de <response> ou <thinking>). Listas só quando há várias linhas.
- "Sócios" e "clientes" são a mesma coisa. Para saber nomes sem pista nenhuma, usa listar_socios; com parte do nome, usa procurar_socio.
- Se uma ferramenta devolver um erro, tenta resolver com outra ferramenta antes de pedir mais informação ao utilizador. Meses no formato AAAA-MM; quando o utilizador diz só o mês (ex.: "junho"), é a ocorrência mais recente desse mês até ao mês seguinte ao atual.
- Para registar um pagamento: procura o sócio com procurar_socio; se houver mais do que um com esse nome, pergunta qual. Se não souberes o método (MB WAY ou dinheiro), pergunta. Depois usa propor_pagamento. Nunca digas que o pagamento ficou registado: diz que preparaste o registo e que falta confirmar no cartão abaixo.
- Não consegues inscrever sócios, editar fichas, mudar planos nem apagar dados: indica o ecrã da aplicação onde se faz isso (ex.: "Sócios → Novo sócio").
- Não há registo de entradas (check-ins) nem presenças.
- Não tens acesso a NIF, datas de nascimento completas, moradas, telefones, emails, entradas/presenças nem notas das fichas. Se perguntarem por isso, diz que não tens acesso e que está na ficha do sócio na aplicação."""


def _validar_historico(body: dict) -> list[dict]:
    mensagens = body.get("mensagens")
    if not isinstance(mensagens, list) or not mensagens:
        raise ErroApi(400, "'mensagens' tem de ser uma lista não vazia")
    msgs = []
    for m in mensagens[-MAX_MENSAGENS:]:
        if not isinstance(m, dict) or m.get("role") not in ("user", "assistant"):
            raise ErroApi(400, "Cada mensagem precisa de role 'user' ou 'assistant'")
        texto = m.get("texto")
        if not isinstance(texto, str) or not texto.strip():
            raise ErroApi(400, "Mensagem vazia")
        if len(texto) > MAX_TEXTO:
            raise ErroApi(400, f"Mensagem demasiado longa (máximo {MAX_TEXTO} caracteres)")
        # A Converse API exige alternancia user/assistant: junta seguidas do mesmo papel.
        if msgs and msgs[-1]["role"] == m["role"]:
            msgs[-1]["content"][0]["text"] += "\n" + texto.strip()
        else:
            msgs.append({"role": m["role"], "content": [{"text": texto.strip()}]})
    while msgs and msgs[0]["role"] != "user":  # tem de comecar pelo utilizador
        msgs.pop(0)
    if not msgs or msgs[-1]["role"] != "user":
        raise ErroApi(400, "A última mensagem tem de ser do utilizador")
    return msgs


_PENSAMENTO = re.compile(r"<thinking>.*?(</thinking>|$)", re.S | re.I)


_RESPOSTA = re.compile(r"<response>(.*?)(</response>|$)", re.S | re.I)


def limpar(texto: str) -> str:
    """Tira as marcas internas que alguns modelos (ex.: Nova) escrevem:
    o raciocinio <thinking>...</thinking> desaparece; se houver um bloco
    <response>...</response>, essa e a resposta final e fica so ela."""
    texto = _PENSAMENTO.sub("", texto).replace("</thinking>", "")
    final = _RESPOSTA.search(texto)
    if final and final.group(1).strip():
        texto = final.group(1)
    return texto.replace("<response>", "").replace("</response>", "").strip()


_SUPORTA_ANY = True  # muda para False se o modelo recusar toolChoice "any"


def _chamar_modelo(sistema, msgs, obrigar_ferramenta: bool):
    """Na 1.a chamada de cada pergunta obriga o modelo a usar uma ferramenta
    (toolChoice "any"): os modelos pequenos tendem a responder "de memoria" e a
    inventar ("nao tenho clientes de Lousada"). Depois, "auto", para poder
    responder em texto. Se o modelo nao aceitar "any", continua sem ele."""
    global _SUPORTA_ANY
    config = TOOL_CONFIG
    if obrigar_ferramenta and _SUPORTA_ANY:
        config = {**TOOL_CONFIG, "toolChoice": {"any": {}}}
    try:
        return bedrock().converse(
            modelId=MODELO,
            system=sistema,
            messages=msgs,
            toolConfig=config,
            inferenceConfig={"maxTokens": 1000, "temperature": 0},  # 0: escolhas de ferramenta deterministas
        )
    except ClientError as e:
        if config is TOOL_CONFIG or e.response["Error"]["Code"] != "ValidationException":
            raise
        logger.warning("Modelo nao aceita toolChoice any; a continuar sem", extra={"erro": str(e)})
        _SUPORTA_ANY = False
        return _chamar_modelo(sistema, msgs, obrigar_ferramenta=False)


def conversar(msgs: list[dict]) -> tuple[str, list[dict]]:
    """Loop do agente: o modelo pede ferramentas, corremo-las, devolvemos os
    resultados, ate ele responder em texto (ou ate MAX_VOLTAS)."""
    propostas: list[dict] = []
    sistema = [{"text": system_prompt(v.hoje())}]
    for volta in range(MAX_VOLTAS):
        r = _chamar_modelo(sistema, msgs, obrigar_ferramenta=volta == 0)
        saida = r["output"]["message"]
        msgs.append(saida)
        usos = [b["toolUse"] for b in saida["content"] if "toolUse" in b]
        if r["stopReason"] != "tool_use" or not usos:
            texto = limpar("\n".join(b["text"] for b in saida["content"] if "text" in b))
            return texto or "Não consegui responder a isso.", propostas
        resultados = []
        for u in usos:
            res, ok = executar(u["name"], u.get("input"), propostas)
            logger.info("ferramenta", extra={"nome": u["name"], "ok": ok})
            resultados.append({"toolResult": {"toolUseId": u["toolUseId"], "content": [{"json": res}], "status": "success" if ok else "error"}})
        msgs.append({"role": "user", "content": resultados})
    return "A pergunta exigiu demasiados passos. Tenta ser mais específico.", propostas


def contar_pedido_do_dia():
    """Contador atomico por dia: acima de LIMITE_DIA recusa (travao de custos).
    Unica escrita deste role, limitada por IAM a chaves LIMITE#*."""
    try:
        repo.tabela().update_item(
            Key={"PK": f"LIMITE#CHAT#{v.hoje().isoformat()}", "SK": "LIMITE"},
            UpdateExpression="ADD n :um",
            ConditionExpression="attribute_not_exists(n) OR n < :max",
            ExpressionAttributeValues={":um": 1, ":max": LIMITE_DIA},
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise ErroApi(429, f"Limite diário de {LIMITE_DIA} perguntas atingido. Volta a tentar amanhã.") from None
        raise


@app.post("/chat")
def chat():
    try:
        body = app.current_event.json_body
    except (json.JSONDecodeError, TypeError):
        raise ErroApi(400, "Corpo do pedido não é JSON válido") from None
    if not isinstance(body, dict):
        raise ErroApi(400, "Corpo do pedido tem de ser um objeto JSON")
    msgs = _validar_historico(body)
    contar_pedido_do_dia()
    try:
        resposta, propostas = conversar(msgs)
    except ClientError as e:
        logger.exception("Erro do Bedrock")
        codigo = e.response["Error"]["Code"]
        if codigo == "ThrottlingException":
            raise ErroApi(503, "O assistente está ocupado. Tenta daqui a pouco.") from None
        raise ErroApi(502, f"O assistente não está disponível ({codigo}).") from None
    return {"resposta": resposta, "propostas": propostas}


@logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_HTTP)
def lambda_handler(event: dict, context: LambdaContext) -> dict:
    return app.resolve(event, context)
