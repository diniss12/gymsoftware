// Contagens simples sobre os socios (por plano, idade, localidade...) sao
// calculadas no browser a partir da lista ja carregada. O que envolve regras de
// dinheiro (receita prevista, recebido por metodo) vem do backend (regras.py),
// a mesma definicao que o chat usa: GET /resumo/receita.

import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api.js'
import { useDados } from '../dados.jsx'
import { FAIXAS, MESES, METODOS, SEXOS, euros, faixaEtaria, hojeISO, idade, normalizar } from '../util.js'
import { Aguardar, Cabecalho, Erro } from './comum.jsx'

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

function Painel() {
  const { socios, planos, planoPorId } = useDados()
  const [receita, setReceita] = useState(null)
  const [erroReceita, setErroReceita] = useState('')

  useEffect(() => {
    api('/resumo/receita').then(setReceita).catch((e) => setErroReceita(e.message))
  }, [socios]) // recarrega se a lista de socios mudar (ex.: mudanca de plano)

  const linhasMetodo = receita?.porMetodo.metodos.map((m) => ({
    rotulo: `${METODOS[m.metodo] ?? m.metodo} · ${m.n}`,
    valor: m.valor,
    dica: `${m.n} pagamento(s)`,
  }))

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

  const meses = receita?.prevista

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

      {e.ativos === 0 && !meses?.some((l) => l.socios > 0) ? (
        <p className="vazio">Ainda não há sócios ativos para mostrar estatísticas.</p>
      ) : (
        <div className="graficos">
          <section className="cartao col-total">
            <h2 className="cartao-titulo">Receita por mês</h2>
            <p className="cartao-sub">
              Prevista pelos planos em vigor em cada mês, não pelos pagamentos recebidos. Quem mudou de plano a meio do mês conta com o último plano.
            </p>
            <Erro>{erroReceita}</Erro>
            {!meses && !erroReceita && <p className="muted">A carregar…</p>}
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
        const y = l.mes.slice(0, 4)
        const m = Number(l.mes.slice(5, 7))
        const atual = i === meses.length - 1
        const mostrar = atual || i === iMax
        return (
          <div
            key={l.mes}
            className={`coluna${atual ? ' coluna-atual' : ''}`}
            role="listitem"
            title={`${MESES[m - 1]} ${y}: ${euros(l.receita)} · ${l.socios} sócio(s)`}
          >
            <span className="coluna-valor">{mostrar && l.receita > 0 ? euros(l.receita) : ''}</span>
            <span className="coluna-pista">
              <span className="coluna-barra" style={{ height: `${(l.receita / max) * 100}%` }} />
            </span>
            <span className="coluna-mes">
              {MESES[m - 1].slice(0, 3)}
              {(m === 1 || i === 0) && <small>{y}</small>}
            </span>
          </div>
        )
      })}
    </div>
  )
}
