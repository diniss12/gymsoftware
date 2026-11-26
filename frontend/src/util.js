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

export const vezes = (p) => (p?.vezesPorSemana ? `${p.vezesPorSemana}× semana` : 'Livre')
