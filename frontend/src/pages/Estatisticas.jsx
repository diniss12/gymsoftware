// Todas as estatisticas sao calculadas no browser: a lista de socios ja esta
// carregada e o historico de planos (GET /periodos) vem num so pedido.
// Acrescentar uma estatistica nova e so codigo aqui, sem mexer no backend.

import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api.js'
import { useDados } from '../dados.jsx'
import { FAIXAS, MESES, METODOS, SEXOS, euros, faixaEtaria, hojeISO, idade, mesAnterior, normalizar } from '../util.js'
import { Aguardar, Cabecalho, Erro } from './comum.jsx'

const pad = (n) => String(n).padStart(2, '0')

export default function Estatisticas() {
  return (
    <Aguardar>
      <Painel />
    </Aguardar>
  )
}

function contar(lista, chave, peso = () => 1) {
  const m = new Map()
  for (const x of lista) {
    const k = chave(x)
    m.set(k, (m.get(k) ?? 0) + peso(x))
  }
  return m
}

/**
 * Receita prevista de cada um dos ultimos `n` meses, a partir do historico de planos.
 * Regra: um socio conta num mes se teve um plano em vigor em algum dia desse mes;
 * se mudou de plano a meio, conta o ultimo plano do mes (nunca conta duas vezes).
 * dataFim e exclusiva (= dia em que comecou o plano seguinte / data de saida).
 */
function receitaPorMes(periodos, n = 12) {
  const hoje = hojeISO()
  let y = Number(hoje.slice(0, 4))
  let m = Number(hoje.slice(5, 7))
  const meses = []
  for (let i = 0; i < n; i++) {
    meses.unshift({ y, m })
    if (--m === 0) [m, y] = [12, y - 1]
  }

  const porSocio = new Map()
  for (const p of periodos) porSocio.set(p.socioId, [...(porSocio.get(p.socioId) ?? []), p])
  const linhas = meses.map(({ y, m }) => {
    const inicio = `${y}-${pad(m)}-01`
    const seguinte = m === 12 ? `${y + 1}-01-01` : `${y}-${pad(m + 1)}-01`
    let receita = 0
    let socios = 0
    for (const lista of porSocio.values()) {
      const noMes = lista.filter((p) => p.dataInicio < seguinte && (!p.dataFim || p.dataFim > inicio))
      if (!noMes.length) continue
      const ultimo = noMes.reduce((a, b) => (b.dataInicio > a.dataInicio ? b : a))
      receita += ultimo.precoMensal
      socios += 1
    }
    return { y, m, receita, socios }
  })

  // Sem historico antigo (app nova): corta os meses iniciais vazios, mas mostra pelo menos 6.
  const primeiro = linhas.findIndex((l) => l.socios > 0)
  return linhas.slice(Math.min(primeiro === -1 ? n : primeiro, n - 6))
}

function Painel() {
  const { socios, planos, planoPorId } = useDados()
  const [periodos, setPeriodos] = useState(null)
  const [erroPeriodos, setErroPeriodos] = useState('')

  const [pagamentos, setPagamentos] = useState(null)

  useEffect(() => {
    api('/periodos').then(setPeriodos).catch((e) => setErroPeriodos(e.message))
  }, [socios]) // recarrega se a lista de socios mudar (ex.: mudanca de plano)

  // Pagamentos dos ultimos 12 meses (pela data em que foram pagos). Pede-se a
  // partir de 13 meses de referencia atras para apanhar quem pagou com atraso.
  const desde12 = mesAnterior(hojeISO().slice(0, 7), 11)
  useEffect(() => {
    api(`/pagamentos?desde=${mesAnterior(desde12, 1)}`)
      .then((lista) => setPagamentos(lista.filter((p) => p.dataPagamento >= `${desde12}-01`)))
      .catch((e) => setErroPeriodos(e.message))
  }, [desde12])

  const linhasMetodo = useMemo(() => {
    if (!pagamentos) return null
    const valor = contar(pagamentos, (p) => p.metodo, (p) => p.valor)
    const n = contar(pagamentos, (p) => p.metodo)
    return Object.entries(METODOS).map(([k, nome]) => ({
      rotulo: `${nome} · ${n.get(k) ?? 0}`,
      valor: valor.get(k) ?? 0,
      dica: `${n.get(k) ?? 0} pagamento(s)`,
    }))
  }, [pagamentos])

  const e = useMemo(() => {
    const hoje = hojeISO()
    const mesAtual = hoje.slice(0, 7)
    const ativos = socios.filter((s) => s.estado === 'ATIVO')
    const idades = ativos.map((s) => idade(s.dataNascimento, hoje))
    const preco = (s) => planoPorId[s.planoId]?.precoMensal ?? 0

    const porPlano = contar(ativos, (s) => s.planoId)
    const linhasPlano = planos
      .filter((p) => p.ativo || porPlano.has(p.id)) // planos desativados so aparecem se ainda tiverem socios
      .map((p) => {
        const n = porPlano.get(p.id) ?? 0
        return { rotulo: p.nome, valor: n, dica: `${euros(n * p.precoMensal)}/mês` }
      })

    // Localidades: agrupa ignorando maiusculas/acentos ("Felgueiras" = "felgueiras").
    const nomesLoc = new Map()
    const porLoc = contar(ativos, (s) => {
      const k = normalizar(s.localidade?.trim()) || '—'
      if (!nomesLoc.has(k)) nomesLoc.set(k, s.localidade?.trim() || 'Sem localidade')
      return k
    })
    let linhasLoc = [...porLoc].map(([k, v]) => ({ rotulo: nomesLoc.get(k), valor: v })).sort((a, b) => b.valor - a.valor)
    if (linhasLoc.length > 10) {
      const resto = linhasLoc.slice(9).reduce((s, l) => s + l.valor, 0)
      linhasLoc = [...linhasLoc.slice(0, 9), { rotulo: 'Outras', valor: resto }]
    }

    const porFaixa = contar(idades, faixaEtaria)
    const linhasFaixa = FAIXAS.map((f) => ({ rotulo: f, valor: porFaixa.get(f) ?? 0 }))

    const comSexo = ativos.filter((s) => s.sexo)
    const receitaSexo = contar(comSexo, (s) => s.sexo, preco)
    const nSexo = contar(comSexo, (s) => s.sexo)
    const linhasSexo = Object.entries(SEXOS).map(([k, nome]) => ({
      rotulo: `${nome} · ${nSexo.get(k) ?? 0}`,
      valor: receitaSexo.get(k) ?? 0,
      dica: `${nSexo.get(k) ?? 0} sócio(s)`,
    }))

    const mes = Number(hoje.slice(5, 7))
    const aniversariantes = ativos
      .filter((s) => Number(s.dataNascimento.slice(5, 7)) === mes)
      .map((s) => ({ ...s, dia: Number(s.dataNascimento.slice(8, 10)), faz: Number(hoje.slice(0, 4)) - Number(s.dataNascimento.slice(0, 4)) }))
      .sort((a, b) => a.dia - b.dia)

    return {
      ativos: ativos.length,
      inativos: socios.length - ativos.length,
      receita: ativos.reduce((s, x) => s + preco(x), 0),
      idadeMedia: idades.length ? Math.round(idades.reduce((a, b) => a + b, 0) / idades.length) : null,
      novos: ativos.filter((s) => s.dataEntrada.startsWith(mesAtual)).length,
      semSexo: ativos.length - comSexo.length,
      linhasPlano,
      linhasLoc,
      linhasFaixa,
      linhasSexo,
      aniversariantes,
      mesNome: MESES[mes - 1],
    }
  }, [socios, planos, planoPorId])

  const meses = useMemo(() => (periodos ? receitaPorMes(periodos) : null), [periodos])

  return (
    <>
      <Cabecalho titulo="Estatísticas" descricao="Calculadas a partir dos sócios ativos, salvo indicação em contrário." />

      <div className="tiles">
        <Tile rotulo="Sócios ativos" valor={e.ativos} />
        <Tile rotulo="Receita mensal prevista" valor={euros(e.receita)} nota="soma dos planos atuais" />
        <Tile rotulo={`Novos em ${e.mesNome.toLowerCase()}`} valor={e.novos} />
        <Tile rotulo="Idade média" valor={e.idadeMedia ?? '—'} nota={e.idadeMedia ? 'anos' : ''} />
        <Tile rotulo="Inativos" valor={e.inativos} />
      </div>

      {e.ativos === 0 && !periodos?.length ? (
        <p className="vazio">Ainda não há sócios ativos para mostrar estatísticas.</p>
      ) : (
        <div className="graficos">
          <section className="cartao col-total">
            <h2 className="cartao-titulo">Receita por mês</h2>
            <p className="cartao-sub">
              Prevista pelos planos em vigor em cada mês, não pelos pagamentos recebidos. Quem mudou de plano a meio do mês conta com o último plano.
            </p>
            <Erro>{erroPeriodos}</Erro>
            {!meses && !erroPeriodos && <p className="muted">A carregar…</p>}
            {meses && <Colunas meses={meses} />}
          </section>

          {linhasMetodo && (
            <Barras titulo="Pagamentos por método" linhas={linhasMetodo} formato={euros} largura="9ch"
              nota="Valor recebido nos últimos 12 meses · número de pagamentos ao lado do método." />
          )}
          <Barras titulo="Receita mensal por sexo" linhas={e.linhasSexo} formato={euros} largura="9ch"
            nota={e.semSexo ? `${e.semSexo} sócio(s) sem sexo indicado não entram aqui.` : null} />
          <Barras titulo="Por plano" linhas={e.linhasPlano} />
          <Barras titulo="Por faixa etária" linhas={e.linhasFaixa} />
          <Barras titulo="Por localidade" linhas={e.linhasLoc} />
          <section className="cartao">
            <h2 className="cartao-titulo">Aniversariantes de {e.mesNome.toLowerCase()}</h2>
            {e.aniversariantes.length === 0 ? (
              <p className="muted">Ninguém faz anos este mês.</p>
            ) : (
              <ul className="aniversarios">
                {e.aniversariantes.map((s) => (
                  <li key={s.id}>
                    <span className="aniv-dia">{s.dia}</span>
                    <Link to={`/socios/${s.id}`}>{s.nome}</Link>
                    <span className="muted">faz {s.faz}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      )}
    </>
  )
}

function Tile({ rotulo, valor, nota }) {
  return (
    <div className="tile">
      <p className="tile-lbl">{rotulo}</p>
      <p className="tile-valor">{valor}</p>
      {nota && <p className="tile-nota">{nota}</p>}
    </div>
  )
}

/** Barras horizontais de uma so serie: sem legenda (o titulo nomeia a serie),
 *  valor escrito no fim de cada barra e tooltip nativo ao passar o rato. */
function Barras({ titulo, linhas, formato = String, largura = '3ch', nota }) {
  const max = Math.max(1, ...linhas.map((l) => l.valor))
  const total = linhas.reduce((s, l) => s + l.valor, 0)
  return (
    <section className="cartao">
      <h2 className="cartao-titulo">{titulo}</h2>
      <ul className="barras" style={{ '--largura-valor': largura }}>
        {linhas.map((l) => {
          const pct = total ? Math.round((l.valor / total) * 100) : 0
          return (
            <li key={l.rotulo} title={`${l.rotulo}: ${formato(l.valor)} · ${pct}%${l.dica ? ` · ${l.dica}` : ''}`}>
              <span className="barra-rotulo">{l.rotulo}</span>
              <span className="barra-pista">
                <span className="barra" style={{ width: `${(l.valor / max) * 100}%` }} />
              </span>
              <span className="barra-valor">{formato(l.valor)}</span>
            </li>
          )
        })}
      </ul>
      {nota && <p className="cartao-sub cartao-nota">{nota}</p>}
    </section>
  )
}

/** Colunas verticais (uma por mes). So o mes atual e o maximo levam o valor
 *  escrito; os restantes mostram-no no tooltip, para nao encher o grafico. */
function Colunas({ meses }) {
  const max = Math.max(1, ...meses.map((l) => l.receita))
  const iMax = meses.findIndex((l) => l.receita === max)
  return (
    <div className="colunas" role="list">
      {meses.map((l, i) => {
        const atual = i === meses.length - 1
        const mostrar = atual || i === iMax
        return (
          <div
            key={`${l.y}-${l.m}`}
            className={`coluna${atual ? ' coluna-atual' : ''}`}
            role="listitem"
            title={`${MESES[l.m - 1]} ${l.y}: ${euros(l.receita)} · ${l.socios} sócio(s)`}
          >
            <span className="coluna-valor">{mostrar && l.receita > 0 ? euros(l.receita) : ''}</span>
            <span className="coluna-pista">
              <span className="coluna-barra" style={{ height: `${(l.receita / max) * 100}%` }} />
            </span>
            <span className="coluna-mes">
              {MESES[l.m - 1].slice(0, 3)}
              {(l.m === 1 || i === 0) && <small>{l.y}</small>}
            </span>
          </div>
        )
      })}
    </div>
  )
}
