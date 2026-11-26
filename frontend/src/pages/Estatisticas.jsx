// Todas as estatisticas sao calculadas no browser a partir da lista de socios
// ja carregada: nao ha endpoint nem custo extra, e acrescentar uma estatistica
// nova e so codigo aqui.

import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { useDados } from '../dados.jsx'
import { FAIXAS, euros, faixaEtaria, hojeISO, idade, normalizar } from '../util.js'
import { Aguardar, Cabecalho } from './comum.jsx'

const MESES = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']

export default function Estatisticas() {
  return (
    <Aguardar>
      <Painel />
    </Aguardar>
  )
}

function contar(lista, chave) {
  const m = new Map()
  for (const x of lista) {
    const k = chave(x)
    m.set(k, (m.get(k) ?? 0) + 1)
  }
  return m
}

function Painel() {
  const { socios, planos, planoPorId } = useDados()

  const e = useMemo(() => {
    const hoje = hojeISO()
    const mesAtual = hoje.slice(0, 7)
    const ativos = socios.filter((s) => s.estado === 'ATIVO')
    const idades = ativos.map((s) => idade(s.dataNascimento, hoje))

    const porPlano = contar(ativos, (s) => s.planoId)
    const linhasPlano = planos
      .filter((p) => p.ativo || porPlano.has(p.id)) // planos desativados so aparecem se ainda tiverem socios
      .map((p) => ({ rotulo: p.nome, valor: porPlano.get(p.id) ?? 0, extra: euros((porPlano.get(p.id) ?? 0) * p.precoMensal) }))

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

    const mes = Number(hoje.slice(5, 7))
    const aniversariantes = ativos
      .filter((s) => Number(s.dataNascimento.slice(5, 7)) === mes)
      .map((s) => ({ ...s, dia: Number(s.dataNascimento.slice(8, 10)), faz: Number(hoje.slice(0, 4)) - Number(s.dataNascimento.slice(0, 4)) }))
      .sort((a, b) => a.dia - b.dia)

    return {
      ativos: ativos.length,
      inativos: socios.length - ativos.length,
      receita: ativos.reduce((s, x) => s + (planoPorId[x.planoId]?.precoMensal ?? 0), 0),
      idadeMedia: idades.length ? Math.round(idades.reduce((a, b) => a + b, 0) / idades.length) : null,
      novos: ativos.filter((s) => s.dataEntrada.startsWith(mesAtual)).length,
      linhasPlano,
      linhasLoc,
      linhasFaixa,
      aniversariantes,
      mesNome: MESES[mes - 1],
    }
  }, [socios, planos, planoPorId])

  return (
    <>
      <Cabecalho eyebrow="Sócios ativos" titulo="Estatísticas" />

      <div className="tiles">
        <Tile rotulo="Sócios ativos" valor={e.ativos} />
        <Tile rotulo="Receita mensal prevista" valor={euros(e.receita)} nota="soma dos planos atuais" />
        <Tile rotulo={`Novos em ${e.mesNome.toLowerCase()}`} valor={e.novos} />
        <Tile rotulo="Idade média" valor={e.idadeMedia ?? '—'} nota={e.idadeMedia ? 'anos' : ''} />
        <Tile rotulo="Inativos" valor={e.inativos} />
      </div>

      {e.ativos === 0 ? (
        <p className="vazio">Ainda não há sócios ativos para mostrar estatísticas.</p>
      ) : (
        <div className="graficos">
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
function Barras({ titulo, linhas }) {
  const max = Math.max(1, ...linhas.map((l) => l.valor))
  const total = linhas.reduce((s, l) => s + l.valor, 0)
  return (
    <section className="cartao">
      <h2 className="cartao-titulo">{titulo}</h2>
      <ul className="barras">
        {linhas.map((l) => {
          const pct = total ? Math.round((l.valor / total) * 100) : 0
          return (
            <li key={l.rotulo} title={`${l.rotulo}: ${l.valor} sócio(s) · ${pct}%${l.extra ? ` · ${l.extra}/mês` : ''}`}>
              <span className="barra-rotulo">{l.rotulo}</span>
              <span className="barra-pista">
                <span className="barra" style={{ width: `${(l.valor / max) * 100}%` }} />
              </span>
              <span className="barra-valor">{l.valor}</span>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
