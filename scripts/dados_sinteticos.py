"""Dados sinteticos para testar a app (estatisticas, pagamentos, assistente).

Corre no AWS CloudShell (ja tem Python, boto3 e as credenciais da consola):

    python3 dados_sinteticos.py              # so mostra o resumo do que geraria (nao escreve)
    python3 dados_sinteticos.py --carregar   # escreve na tabela (pede confirmacao)
    python3 dados_sinteticos.py --apagar     # apaga TODOS os socios sinteticos (pede confirmacao)

Pre-visualizacao sem AWS (le os planos do ficheiro em vez da tabela):

    python3 dados_sinteticos.py --planos planos.json

Cada socio sintetico leva `sintetico: true` na ficha. O --apagar encontra-os por
esse campo e apaga a particao inteira (ficha, historico de planos, pagamentos,
incluindo pagamentos registados depois pela app) e o item do NIF. Os socios
reais nunca sao tocados.

Formato dos itens igual ao backend/repo.py (single-table). Gerador
deterministico (seed fixa): correr duas vezes gera os mesmos socios.
"""

import argparse
import json
import os
import random
import sys
import time
import unicodedata
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

STACK = "gymsoftware"
REGIAO = "eu-west-1"
N_SOCIOS = 80
SEED = 42
INICIO_COBRANCA = "2026-11"

HOMENS = ["João", "Pedro", "Tiago", "Rui", "Miguel", "André", "Bruno", "Ricardo", "Diogo", "Nuno", "Hugo", "Carlos",
          "Filipe", "Gonçalo", "Rafael", "Luís", "Fábio", "Vítor", "José", "Paulo", "Daniel", "Marco", "Tomás", "Leandro"]
MULHERES = ["Ana", "Maria", "Joana", "Inês", "Sofia", "Catarina", "Mariana", "Rita", "Beatriz", "Carla", "Sara",
            "Patrícia", "Marta", "Diana", "Cláudia", "Filipa", "Helena", "Raquel", "Daniela", "Vânia", "Andreia"]
APELIDOS = ["Silva", "Santos", "Ferreira", "Pereira", "Oliveira", "Costa", "Rodrigues", "Martins", "Sousa", "Fernandes",
            "Gonçalves", "Gomes", "Lopes", "Marques", "Alves", "Almeida", "Ribeiro", "Pinto", "Carvalho", "Teixeira",
            "Moreira", "Correia", "Mendes", "Nunes", "Soares", "Vieira", "Monteiro", "Cardoso", "Rocha", "Neves",
            "Coelho", "Cunha", "Pires", "Magalhães", "Leite"]
LOCALIDADES = [("Felgueiras", 45), ("Lousada", 15), ("Amarante", 10), ("Paços de Ferreira", 8), ("Fafe", 7),
               ("Guimarães", 5), ("Vizela", 5), ("Penafiel", 5)]
RUAS = ["Rua da Liberdade", "Rua de Santa Quitéria", "Avenida Dr. Leonardo Coimbra", "Rua do Comércio", "Rua da Igreja",
        "Rua 25 de Abril", "Travessa da Fonte", "Rua das Flores", "Avenida da República", "Rua do Souto"]
NOTAS = ["Lesão no joelho direito: evitar agachamentos com carga.", "Prefere treinar de manhã.",
         "Veio por recomendação de outro sócio.", "Objetivo: perder peso para o casamento em junho."]
# (idade minima, maxima, peso)
IDADES = [(14, 17, 5), (18, 24, 20), (25, 34, 30), (35, 44, 20), (45, 54, 13), (55, 64, 8), (65, 75, 4)]
PESO_PLANO = {1: 8, 2: 22, 3: 32, 4: 18, 5: 12, 6: 8}  # por vezes/semana

LISBOA = ZoneInfo("Europe/Lisbon")
CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


# ---------------------------------------------------------------- ajudantes (iguais ao backend)
def normalizar(texto: str) -> str:
    sem = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in sem if not unicodedata.combining(c)).lower()


def ulid(ms: int, rnd: random.Random) -> str:
    """ULID com timestamp escolhido: os periodos ficam ordenados pela data de inicio."""
    n = (ms << 80) | rnd.getrandbits(80)
    return "".join(CROCKFORD[(n >> s) & 31] for s in range(125, -1, -5))


def ms(d: date, extra: int = 0) -> int:
    return int(datetime(d.year, d.month, d.day, 10, tzinfo=LISBOA).timestamp() * 1000) + extra


def nif(rnd: random.Random) -> str:
    base = str(rnd.choice([1, 2])) + "".join(str(rnd.randint(0, 9)) for _ in range(7))
    resto = sum(int(d) * (9 - i) for i, d in enumerate(base)) % 11
    return base + str(0 if resto < 2 else 11 - resto)


def mes_seguinte(m: str) -> str:
    y, mm = int(m[:4]), int(m[5:7])
    return f"{y + 1}-01" if mm == 12 else f"{y}-{mm + 1:02d}"


def plano_do_mes(periodos: list[dict], mes: str) -> dict | None:
    """Mesma regra que backend/regras.py: ultimo plano em vigor no mes."""
    inicio, seguinte = f"{mes}-01", f"{mes_seguinte(mes)}-01"
    no_mes = [p for p in periodos if p["dataInicio"] < seguinte and (not p.get("dataFim") or p["dataFim"] > inicio)]
    return max(no_mes, key=lambda p: p["dataInicio"]) if no_mes else None


def entre(rnd: random.Random, a: date, b: date) -> date:
    return a + timedelta(days=rnd.randint(0, max(0, (b - a).days)))


def escolher(rnd: random.Random, pares):
    return rnd.choices([x for x, _ in pares], weights=[p for _, p in pares])[0]


# ---------------------------------------------------------------- geracao
def gerar(planos: list[dict], hoje: date, nifs_ocupados=lambda n: False) -> list[dict]:
    """Devolve uma lista de socios, cada um com perfil, periodos e pagamentos."""
    rnd = random.Random(SEED)
    ativos = [p for p in planos if p["ativo"] and p.get("vezesPorSemana")]
    pesos = [(p, PESO_PLANO.get(p["vezesPorSemana"], 5)) for p in ativos]
    inicio_dados = date(hoje.year - 1, hoje.month, 15)
    nomes, nifs, socios = set(), set(), []

    while len(socios) < N_SOCIOS:
        sexo = "M" if rnd.random() < 0.55 else "F"
        nome = f"{rnd.choice(HOMENS if sexo == 'M' else MULHERES)} {rnd.choice(APELIDOS)} {rnd.choice(APELIDOS)}"
        if nome in nomes:
            continue
        n = nif(rnd)
        while n in nifs or nifs_ocupados(n):
            n = nif(rnd)
        nomes.add(nome)
        nifs.add(n)

        lo, hi, _ = escolher(rnd, [((a, b, p), p) for a, b, p in IDADES])
        idade = rnd.randint(lo, hi)
        nascimento = entre(rnd, date(hoje.year - idade - 1, hoje.month, 1) + timedelta(days=1), date(hoje.year - idade, hoje.month, 1))
        # Mais inscricoes em janeiro e setembro (como num ginasio a serio)
        while True:
            entrada = entre(rnd, inicio_dados, hoje - timedelta(days=3))
            if entrada.month in (1, 9) or rnd.random() < 0.6:
                break

        plano = escolher(rnd, pesos)
        periodos = [{"plano": plano, "inicio": entrada}]
        if rnd.random() < 0.2 and (hoje - entrada).days > 60:  # mudou de plano uma vez
            outro = escolher(rnd, [(p, w) for p, w in pesos if p["id"] != plano["id"]])
            periodos.append({"plano": outro, "inicio": entre(rnd, entrada + timedelta(days=30), hoje - timedelta(days=10))})
        saida = None
        if rnd.random() < 0.12 and (hoje - periodos[-1]["inicio"]).days > 50:  # saiu do ginasio
            saida = entre(rnd, periodos[-1]["inicio"] + timedelta(days=45), hoje - timedelta(days=5))

        sid = ulid(ms(entrada), rnd)
        pers = []
        for i, p in enumerate(periodos):
            fim = periodos[i + 1]["inicio"] if i + 1 < len(periodos) else saida
            per = {
                "tipo": "PERIODO",
                "id": ulid(ms(p["inicio"], i), rnd),
                "planoId": p["plano"]["id"],
                "planoNome": p["plano"]["nome"],
                "precoMensal": p["plano"]["precoMensal"],
                "vezesPorSemana": p["plano"].get("vezesPorSemana"),
                "dataInicio": p["inicio"].isoformat(),
            }
            if fim:
                per["dataFim"] = fim.isoformat()
            pers.append(per)

        criado = datetime(entrada.year, entrada.month, entrada.day, 18, rnd.randint(0, 59), tzinfo=LISBOA).isoformat(timespec="milliseconds")
        perfil = {
            "tipo": "SOCIO",
            "id": sid,
            "nome": nome,
            "nif": n,
            "sexo": sexo,
            "dataNascimento": nascimento.isoformat(),
            "dataEntrada": entrada.isoformat(),
            "morada": f"{rnd.choice(RUAS)}, {rnd.randint(1, 250)}",
            "localidade": escolher(rnd, LOCALIDADES),
            "notas": rnd.choice(NOTAS) if rnd.random() < 0.1 else "",
            "estado": "INATIVO" if saida else "ATIVO",
            "planoId": pers[-1]["planoId"],
            "planoDesde": pers[-1]["dataInicio"],
            "criadoEm": criado,
            "atualizadoEm": criado,
            "sintetico": True,
        }
        if saida:
            perfil["dataSaida"] = saida.isoformat()
        else:
            perfil["periodoAtual"] = pers[-1]["id"]

        # Pagamentos: historico quase todo pago; o mes atual (ainda no prazo) so por parte;
        # ~10% sao maus pagadores; alguns pagam o mes seguinte adiantado.
        mau_pagador = rnd.random() < 0.1
        pagamentos = []
        mes, mes_atual = entrada.isoformat()[:7], hoje.isoformat()[:7]
        while mes <= mes_atual:
            plano_mes = plano_do_mes(pers, mes)
            prob = 0.35 if mau_pagador else (0.65 if mes == mes_atual else 0.95)
            if plano_mes and rnd.random() < prob:
                ini = max(date.fromisoformat(f"{mes}-01"), entrada)
                pago = ini + timedelta(days=rnd.randint(0, 10)) if rnd.random() < 0.85 else date.fromisoformat(f"{mes_seguinte(mes)}-01") + timedelta(days=rnd.randint(0, 7))
                if pago <= hoje:
                    pagamentos.append(pagamento(sid, mes, plano_mes["precoMensal"], pago, rnd))
            mes = mes_seguinte(mes)
        if not saida and not mau_pagador and rnd.random() < 0.06:
            prox = mes_seguinte(mes_atual)
            pagamentos.append(pagamento(sid, prox, pers[-1]["precoMensal"], entre(rnd, hoje - timedelta(days=5), hoje), rnd))

        socios.append({"perfil": perfil, "periodos": pers, "pagamentos": pagamentos})
    return socios


def pagamento(sid: str, mes: str, valor: int, pago: date, rnd: random.Random) -> dict:
    return {
        "tipo": "PAGAMENTO",
        "socioId": sid,
        "mes": mes,
        "valor": valor,
        "metodo": "MBWAY" if rnd.random() < 0.6 else "DINHEIRO",
        "dataPagamento": pago.isoformat(),
        "notas": "",
        "criadoEm": datetime(pago.year, pago.month, pago.day, 19, rnd.randint(0, 59), tzinfo=LISBOA).isoformat(timespec="milliseconds"),
    }


def itens(s: dict) -> list[dict]:
    """Itens DynamoDB no formato do backend/repo.py."""
    p, sid = s["perfil"], s["perfil"]["id"]
    out = [
        {"PK": f"SOCIO#{sid}", "SK": "PERFIL", "GSI1PK": "SOCIOS", "GSI1SK": f"{normalizar(p['nome'])}#{sid}", **p},
        {"PK": f"NIF#{p['nif']}", "SK": "NIF", "tipo": "NIF", "socioId": sid, "sintetico": True},
    ]
    for per in s["periodos"]:
        out.append({"PK": f"SOCIO#{sid}", "SK": f"PERIODO#{per['id']}", "GSI1PK": "PERIODOS",
                    "GSI1SK": f"{per['dataInicio']}#{per['id']}", **per})
    for pg in s["pagamentos"]:
        out.append({"PK": f"SOCIO#{sid}", "SK": f"PAGAMENTO#{pg['mes']}", "GSI1PK": "PAGAMENTOS",
                    "GSI1SK": f"{pg['mes']}#{sid}", **pg})
    # None nao e valido no DynamoDB (vezesPorSemana de um plano "livre")
    return [{k: v for k, v in it.items() if v is not None} for it in out]


def resumo(socios: list[dict], hoje: date):
    ativos = [s for s in socios if s["perfil"]["estado"] == "ATIVO"]
    por_plano = {}
    for s in ativos:
        nome = s["periodos"][-1]["planoNome"]
        por_plano[nome] = por_plano.get(nome, 0) + 1
    pags = [p for s in socios for p in s["pagamentos"]]
    mes_atual = hoje.isoformat()[:7]
    sem_mes_atual = sum(1 for s in ativos if not any(p["mes"] == mes_atual for p in s["pagamentos"]))
    print(f"Sócios: {len(socios)} ({len(ativos)} ativos, {len(socios) - len(ativos)} inativos)")
    print(f"Mudaram de plano: {sum(1 for s in socios if len(s['periodos']) > 1)}")
    print("Ativos por plano: " + ", ".join(f"{k}: {v}" for k, v in sorted(por_plano.items())))
    print(f"Pagamentos: {len(pags)}, total {sum(p['valor'] for p in pags) / 100:.2f} € "
          f"(MB WAY {sum(1 for p in pags if p['metodo'] == 'MBWAY')}, dinheiro {sum(1 for p in pags if p['metodo'] == 'DINHEIRO')})")
    print(f"Ativos sem pagamento de {mes_atual}: {sem_mes_atual}")
    print(f"Itens a escrever: {sum(len(itens(s)) for s in socios)}")
    print("Exemplos: " + "; ".join(s["perfil"]["nome"] for s in socios[:5]))


# ---------------------------------------------------------------- AWS
def tabela():
    import boto3

    outs = boto3.client("cloudformation", region_name=REGIAO).describe_stacks(StackName=STACK)["Stacks"][0]["Outputs"]
    nome = next(o["OutputValue"] for o in outs if o["OutputKey"] == "TableName")
    return boto3.resource("dynamodb", region_name=REGIAO).Table(nome)


def query_tudo(t, **kw) -> list[dict]:
    itens_, inicio = [], None
    while True:
        if inicio:
            kw["ExclusiveStartKey"] = inicio
        r = t.query(**kw)
        itens_ += r["Items"]
        inicio = r.get("LastEvaluatedKey")
        if not inicio:
            return itens_


def num(x):
    return int(x) if x is not None else None


def planos_da_tabela(t) -> list[dict]:
    from boto3.dynamodb.conditions import Key

    return [
        {"id": p["id"], "nome": p["nome"], "precoMensal": num(p["precoMensal"]),
         "vezesPorSemana": num(p.get("vezesPorSemana")), "ativo": p["ativo"]}
        for p in query_tudo(t, IndexName="GSI1", KeyConditionExpression=Key("GSI1PK").eq("PLANOS"))
    ]


def sinteticos_existentes(t) -> list[dict]:
    from boto3.dynamodb.conditions import Attr, Key

    return query_tudo(t, IndexName="GSI1", KeyConditionExpression=Key("GSI1PK").eq("SOCIOS"),
                      FilterExpression=Attr("sintetico").eq(True))


def confirmar(palavra: str, texto: str):
    print(texto)
    if input(f"Escreve {palavra} para continuar: ").strip() != palavra:
        sys.exit("Cancelado. Nada foi alterado.")


def carregar(t, hoje: date):
    if sinteticos_existentes(t):
        sys.exit("Já existem sócios sintéticos na tabela. Corre primeiro --apagar.")
    ocupado = lambda n: "Item" in t.get_item(Key={"PK": f"NIF#{n}", "SK": "NIF"})  # noqa: E731
    socios = gerar(planos_da_tabela(t), hoje, ocupado)
    resumo(socios, hoje)
    confirmar("CARREGAR", f"\nVai escrever na tabela de PRODUÇÃO {t.name}.")
    with t.batch_writer() as w:
        for s in socios:
            for it in itens(s):
                w.put_item(Item=it)
    print(f"Feito: {len(socios)} sócios sintéticos carregados. Recarrega a app.")


def apagar(t):
    from boto3.dynamodb.conditions import Key

    socios = sinteticos_existentes(t)
    if not socios:
        sys.exit("Não há sócios sintéticos na tabela.")
    confirmar("APAGAR", f"Vai apagar {len(socios)} sócios sintéticos (e tudo o que está associado a eles) da tabela {t.name}.")
    n = 0
    with t.batch_writer() as w:
        for s in socios:
            for it in query_tudo(t, KeyConditionExpression=Key("PK").eq(s["PK"])):
                w.delete_item(Key={"PK": it["PK"], "SK": it["SK"]})
                n += 1
            w.delete_item(Key={"PK": f"NIF#{s['nif']}", "SK": "NIF"})
            n += 1
    print(f"Feito: {n} itens apagados. Os sócios reais não foram tocados.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--carregar", action="store_true")
    g.add_argument("--apagar", action="store_true")
    g.add_argument("--planos", help="pre-visualizar com os planos deste ficheiro (scripts/planos.json), sem AWS")
    a = ap.parse_args()
    hoje = datetime.now(LISBOA).date()

    if a.planos:
        bruto = json.load(open(a.planos))
        lista = next(iter(bruto.values()))
        planos = [{"id": i["PutRequest"]["Item"]["id"]["S"], "nome": i["PutRequest"]["Item"]["nome"]["S"],
                   "precoMensal": int(i["PutRequest"]["Item"]["precoMensal"]["N"]),
                   "vezesPorSemana": int(i["PutRequest"]["Item"]["vezesPorSemana"]["N"]), "ativo": True} for i in lista]
        resumo(gerar(planos, hoje), hoje)
        return
    t = tabela()
    if a.carregar:
        carregar(t, hoje)
    elif a.apagar:
        apagar(t)
    else:
        resumo(gerar(planos_da_tabela(t), hoje), hoje)
        print("\n(Só pré-visualização: nada foi escrito. Usa --carregar para escrever.)")


if __name__ == "__main__":
    main()
