// Painel inicial: quem tem mensalidades em atraso (prazo: dia 8 do mes seguinte)
// e o resumo de pagamentos do mes. Calculado no browser a partir de 3 listas
// (socios ja carregados + GET /periodos + GET /pagamentos), 2 pedidos no total.

import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api.js'
import { useDados } from '../dados.jsx'
import { DIA_LIMITE, INICIO_COBRANCA, MESES, dataPt, euros, hojeISO, mesAnterior, mesCurto, mesNome, prazo, situacao } from '../util.js'
import { Aguardar, Cabecalho, Erro } from './comum.jsx'

export default function Inicio() {
  return (
    <Aguardar>
      <Painel />
    </Aguardar>
  )
}

function agrupar(lista, chave) {
  const m = new Map()
  for (const x of lista) m.set(chave(x), [...(m.get(chave(x)) ?? []), x])
  return m
}

function Painel() {
  const { socios } = useDados()
  const navigate = useNavigate()
  const [dados, setDados] = useState(null)
  const [erro, setErro] = useState('')

  useEffect(() => {
    Promise.all([api('/periodos'), api(`/pagamentos?desde=${INICIO_COBRANCA}`)])
      .then(([periodos, pagamentos]) => setDados({ periodos, pagamentos }))
      .catch((e) => setErro(e.message))
  }, [socios])

  const r = useMemo(() => {
    if (!dados) return null
    const hoje = hojeISO()
    const mesAtual = hoje.slice(0, 7)
    const periodosDe = agrupar(dados.periodos, (p) => p.socioId)
    const pagamentosDe = agrupar(dados.pagamentos, (p) => p.socioId)

    const atrasos = []
    let dentroDoPrazo = 0
    let valorDentroDoPrazo = 0
    for (const s of socios) {
      const sit = situacao(periodosDe.get(s.id) ?? [], pagamentosDe.get(s.id) ?? [], hoje)
      if (sit.emAtraso.length) {
        atrasos.push({ socio: s, meses: sit.emAtraso, total: sit.emAtraso.reduce((t, d) => t + d.valor, 0) })
      }
      // So o mes anterior ainda dentro do prazo (o mes atual ainda esta a decorrer).
      for (const d of sit.dentroDoPrazo) {
        if (d.mes < mesAtual) {
          dentroDoPrazo += 1
          valorDentroDoPrazo += d.valor
        }
      }
    }
    atrasos.sort((a, b) => a.meses[0].mes.localeCompare(b.meses[0].mes) || b.total - a.total)

    const doMes = dados.pagamentos.filter((p) => p.dataPagamento.startsWith(mesAtual))
    return {
      atrasos,
      totalAtraso: atrasos.reduce((t, a) => t + a.total, 0),
      recebidoMes: doMes.reduce((t, p) => t + p.valor, 0),
      nRecebidoMes: doMes.length,
      dentroDoPrazo,
      valorDentroDoPrazo,
      mesAnterior: mesAnterior(mesAtual),
      nomeMes: MESES[Number(mesAtual.slice(5, 7)) - 1].toLowerCase(),
    }
  }, [dados, socios])

  return (
    <>
      <Cabecalho eyebrow={dataPt(hojeISO())} titulo="Início">
        <Link to="/socios/novo" className="btn btn-red">+ Novo sócio</Link>
      </Cabecalho>

      <Erro>{erro}</Erro>
      {!r && !erro && <p className="muted">A carregar…</p>}
      {r && (
        <>
          <div className="tiles">
            <div className={`tile${r.atrasos.length ? ' tile-alerta' : ''}`}>
              <p className="tile-lbl">Em atraso</p>
              <p className="tile-valor">{euros(r.totalAtraso)}</p>
              <p className="tile-nota">{r.atrasos.length} sócio(s)</p>
            </div>
            <div className="tile">
              <p className="tile-lbl">Recebido em {r.nomeMes}</p>
              <p className="tile-valor">{euros(r.recebidoMes)}</p>
              <p className="tile-nota">{r.nRecebidoMes} pagamento(s)</p>
            </div>
            <div className="tile">
              <p className="tile-lbl">{mesNome(r.mesAnterior)} por pagar</p>
              <p className="tile-valor">{euros(r.valorDentroDoPrazo)}</p>
              <p className="tile-nota">{r.dentroDoPrazo} sócio(s) · ainda no prazo (até {dataPt(prazo(r.mesAnterior))})</p>
            </div>
          </div>

          <h2 className="subtitulo">Mensalidades em atraso</h2>
          <p className="cartao-sub">
            A mensalidade de cada mês pode ser paga até ao dia {DIA_LIMITE} do mês seguinte. Depois disso aparece aqui.
          </p>
          {r.atrasos.length === 0 ? (
            <p className="vazio vazio-ok">Tudo em dia. Não há mensalidades em atraso.</p>
          ) : (
            <div className="tabela-scroll">
              <table className="tabela tabela-clicavel">
                <thead>
                  <tr>
                    <th>Sócio</th>
                    <th>Meses em atraso</th>
                    <th className="num">Valor</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {r.atrasos.map(({ socio, meses, total }) => (
                    <tr key={socio.id} onClick={() => navigate(`/socios/${socio.id}`)}>
                      <td>
                        <Link to={`/socios/${socio.id}`} onClick={(e) => e.stopPropagation()}>{socio.nome}</Link>
                        {socio.estado === 'INATIVO' && <span className="etiqueta">Inativo</span>}
                      </td>
                      <td className="celula-chips">
                        {meses.map((d) => (
                          <span key={d.mes} className="chip chip-atraso" title={`${euros(d.valor)} · prazo ${dataPt(prazo(d.mes))}`}>
                            {mesCurto(d.mes)}
                          </span>
                        ))}
                      </td>
                      <td className="num">{euros(total)}</td>
                      <td className="num"><span className="seta">Registar →</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </>
  )
}
