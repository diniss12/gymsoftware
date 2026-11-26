"""Validacao dos dados que chegam a API.

Feita a mao (sem pydantic) de proposito: pydantic traz uma extensao nativa
(pydantic-core) que aumenta o pacote e o cold start. Para meia duzia de
campos, umas funcoes simples chegam.
"""

import os
import time
import unicodedata
from datetime import date, datetime
from zoneinfo import ZoneInfo

LISBOA = ZoneInfo("Europe/Lisbon")


class ErroApi(Exception):
    """Erro com status HTTP; convertido em resposta JSON pelo app.py."""

    def __init__(self, status: int, mensagem: str):
        super().__init__(mensagem)
        self.status = status
        self.mensagem = mensagem


def hoje() -> date:
    # A Lambda corre em UTC; entre a meia-noite e a 1h (hora de verao) o "hoje"
    # UTC ainda seria ontem em Portugal.
    return datetime.now(LISBOA).date()


def agora_iso() -> str:
    return datetime.now(LISBOA).isoformat(timespec="milliseconds")


# ---------------------------------------------------------------- ids
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def novo_id() -> str:
    """ULID: 48 bits de timestamp (ms) + 80 bits aleatorios, em base32 Crockford.

    Ordena-se pela data de criacao (util para o historico de planos) e nao
    revela quantos socios existem, ao contrario de um numero sequencial.
    """
    n = (int(time.time() * 1000) << 80) | int.from_bytes(os.urandom(10))
    return "".join(_CROCKFORD[(n >> s) & 31] for s in range(125, -1, -5))


# ---------------------------------------------------------------- texto
def normalizar(texto: str) -> str:
    """Minusculas e sem acentos: 'Álvaro' ordena junto de 'alvaro'."""
    sem_acentos = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in sem_acentos if not unicodedata.combining(c)).lower()


def texto(body: dict, campo: str, *, max_len: int, obrigatorio: bool = True) -> str:
    valor = body.get(campo)
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        if obrigatorio:
            raise ErroApi(400, f"'{campo}' é obrigatório")
        return ""
    if not isinstance(valor, str):
        raise ErroApi(400, f"'{campo}' tem de ser texto")
    valor = " ".join(valor.split()) if "\n" not in valor else valor.strip()
    if len(valor) > max_len:
        raise ErroApi(400, f"'{campo}' tem no máximo {max_len} caracteres")
    return valor


def inteiro(body: dict, campo: str, *, minimo: int, maximo: int) -> int:
    valor = body.get(campo)
    # bool e subclasse de int em Python: True passaria como 1
    if not isinstance(valor, int) or isinstance(valor, bool):
        raise ErroApi(400, f"'{campo}' tem de ser um número inteiro")
    if not minimo <= valor <= maximo:
        raise ErroApi(400, f"'{campo}' tem de estar entre {minimo} e {maximo}")
    return valor


def data(body: dict, campo: str, *, obrigatorio: bool = True, padrao: date | None = None) -> date:
    valor = body.get(campo)
    if valor in (None, ""):
        if padrao is not None:
            return padrao
        if obrigatorio:
            raise ErroApi(400, f"'{campo}' é obrigatório")
        return None
    try:
        return date.fromisoformat(valor)
    except (TypeError, ValueError):
        raise ErroApi(400, f"'{campo}' tem de ser uma data AAAA-MM-DD") from None


def nao_futura(d: date, campo: str) -> date:
    if d > hoje():
        raise ErroApi(400, f"'{campo}' não pode ser uma data futura")
    return d


def mes(body: dict, campo: str) -> str:
    """Mes de referencia 'AAAA-MM' (ex.: '2026-07' = mensalidade de julho)."""
    valor = body.get(campo)
    try:
        date.fromisoformat(f"{valor}-01")
        if len(valor) != 7:
            raise ValueError
    except (TypeError, ValueError):
        raise ErroApi(400, f"'{campo}' tem de ser um mês AAAA-MM") from None
    return valor


def mes_seguinte(m: str) -> str:
    y, mm = int(m[:4]), int(m[5:7])
    return f"{y + 1}-01" if mm == 12 else f"{y}-{mm + 1:02d}"


METODOS = ("MBWAY", "DINHEIRO")


def metodo(body: dict) -> str:
    valor = body.get("metodo")
    if valor not in METODOS:
        raise ErroApi(400, "'metodo' tem de ser 'MBWAY' ou 'DINHEIRO'")
    return valor


SEXOS = ("M", "F")


def sexo(body: dict) -> str:
    valor = body.get("sexo")
    if valor not in SEXOS:
        raise ErroApi(400, "'sexo' é obrigatório: 'M' (masculino) ou 'F' (feminino)")
    return valor


# ---------------------------------------------------------------- NIF
def nif_valido(nif: str) -> bool:
    """Digito de controlo do NIF portugues (modulo 11).

    Os 8 primeiros digitos sao multiplicados por 9, 8, ..., 2; o resto da soma
    por 11 da o 9.o digito: 0 se resto < 2, senao 11 - resto.
    """
    if len(nif) != 9 or not nif.isdigit():
        return False
    soma = sum(int(d) * (9 - i) for i, d in enumerate(nif[:8]))
    resto = soma % 11
    controlo = 0 if resto < 2 else 11 - resto
    return int(nif[8]) == controlo


def nif(body: dict) -> str:
    valor = body.get("nif")
    if isinstance(valor, int) and not isinstance(valor, bool):
        valor = str(valor)
    if not isinstance(valor, str) or not valor.strip():
        raise ErroApi(400, "'nif' é obrigatório")
    valor = valor.replace(" ", "")
    if not nif_valido(valor):
        raise ErroApi(400, "NIF inválido")
    return valor
