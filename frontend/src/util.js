// Funcoes puras de formatacao e calculo, partilhadas pelas paginas.

const EUR = new Intl.NumberFormat('pt-PT', { style: 'currency', currency: 'EUR' })

/** 2100 (centimos) -> "21,00 €" */
export const euros = (centimos) => EUR.format((centimos ?? 0) / 100)

/** "21,5" ou "21.50" -> 2150; null se invalido */
export function paraCentimos(texto) {
  const n = Number(String(texto).trim().replace(',', '.'))
  return Number.isFinite(n) && n >= 0 ? Math.round(n * 100) : null
}

/** Minusculas e sem acentos, para pesquisar "alvaro" e encontrar "Álvaro". */
export const normalizar = (s) =>
  (s ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()

/** Data de hoje (hora local do browser) em AAAA-MM-DD. */
export function hojeISO() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/** "2026-01-10" -> "10/01/2026" */
export const dataPt = (iso) => (iso ? iso.split('-').reverse().join('/') : '—')

/** Idade em anos completos a partir de "AAAA-MM-DD". Calculada, nunca guardada. */
export function idade(nascimento, hoje = hojeISO()) {
  if (!nascimento) return null
  const [ay, am, ad] = nascimento.split('-').map(Number)
  const [hy, hm, hd] = hoje.split('-').map(Number)
  return hy - ay - (hm < am || (hm === am && hd < ad) ? 1 : 0)
}

export const FAIXAS = ['< 18', '18–24', '25–34', '35–44', '45–54', '55–64', '65+']

export function faixaEtaria(anos) {
  if (anos < 18) return '< 18'
  if (anos < 25) return '18–24'
  if (anos < 35) return '25–34'
  if (anos < 45) return '35–44'
  if (anos < 55) return '45–54'
  if (anos < 65) return '55–64'
  return '65+'
}

/** Digito de controlo do NIF (mesma regra que o backend). */
export function nifValido(nif) {
  if (!/^\d{9}$/.test(nif)) return false
  const soma = [...nif.slice(0, 8)].reduce((s, d, i) => s + Number(d) * (9 - i), 0)
  const resto = soma % 11
  return Number(nif[8]) === (resto < 2 ? 0 : 11 - resto)
}

export const SEXOS = { M: 'Masculino', F: 'Feminino' }

export const vezes = (p) => (p?.vezesPorSemana ? `${p.vezesPorSemana}× semana` : 'Livre')

// ================================================================ meses e pagamentos
export const MESES = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']

export const METODOS = { MBWAY: 'MB WAY', DINHEIRO: 'Dinheiro' }

/** Primeiro mes cobrado na app: meses anteriores (antes de a app existir) nunca contam como divida. */
export const INICIO_COBRANCA = '2026-11'

/** A mensalidade do mes M pode ser paga ate ao dia 8 do mes M+1; depois fica em atraso. */
export const DIA_LIMITE = 8

const pad2 = (n) => String(n).padStart(2, '0')

export function mesSeguinte(mes) {
  const y = Number(mes.slice(0, 4))
  const m = Number(mes.slice(5, 7))
  return m === 12 ? `${y + 1}-01` : `${y}-${pad2(m + 1)}`
}

export function mesAnterior(mes, n = 1) {
  let y = Number(mes.slice(0, 4))
  let m = Number(mes.slice(5, 7)) - n
  while (m < 1) [m, y] = [m + 12, y - 1]
  return `${y}-${pad2(m)}`
}

/** "2026-07" -> "Julho 2026" */
export const mesNome = (mes) => `${MESES[Number(mes.slice(5, 7)) - 1]} ${mes.slice(0, 4)}`

/** "2026-07" -> "Jul 2026" */
export const mesCurto = (mes) => `${MESES[Number(mes.slice(5, 7)) - 1].slice(0, 3)} ${mes.slice(0, 4)}`

/** Data limite de pagamento do mes: "2026-07" -> "2026-08-08" */
export const prazo = (mes) => `${mesSeguinte(mes)}-${pad2(DIA_LIMITE)}`

/**
 * Meses que um socio deve pagar, de INICIO_COBRANCA (ou da entrada) ate `ate`.
 * Deve um mes se teve um plano em vigor em algum dia desse mes; o valor e o do
 * ultimo plano do mes (mesma regra da receita prevista). dataFim e exclusiva.
 */
export function mesesDevidos(periodos, ate) {
  if (!periodos?.length) return []
  const primeiro = periodos.reduce((a, p) => (p.dataInicio < a ? p.dataInicio : a), '9999').slice(0, 7)
  let mes = primeiro > INICIO_COBRANCA ? primeiro : INICIO_COBRANCA
  const devidos = []
  while (mes <= ate) {
    const inicio = `${mes}-01`
    const seguinte = `${mesSeguinte(mes)}-01`
    const noMes = periodos.filter((p) => p.dataInicio < seguinte && (!p.dataFim || p.dataFim > inicio))
    if (noMes.length) {
      const ultimo = noMes.reduce((a, b) => (b.dataInicio > a.dataInicio ? b : a))
      devidos.push({ mes, valor: ultimo.precoMensal, planoNome: ultimo.planoNome })
    }
    mes = mesSeguinte(mes)
  }
  return devidos
}

/** Meses por pagar de um socio, separados em "em atraso" (prazo passou) e "dentro do prazo". */
export function situacao(periodos, pagamentos, hoje = hojeISO()) {
  const pagos = new Set((pagamentos ?? []).map((p) => p.mes))
  const porPagar = mesesDevidos(periodos, hoje.slice(0, 7)).filter((d) => !pagos.has(d.mes))
  return {
    emAtraso: porPagar.filter((d) => prazo(d.mes) < hoje),
    dentroDoPrazo: porPagar.filter((d) => prazo(d.mes) >= hoje),
  }
}
