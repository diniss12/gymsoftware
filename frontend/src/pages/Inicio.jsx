// Painel inicial: quem tem mensalidades em atraso (prazo: dia 8 do mes seguinte)
// e o resumo de pagamentos do mes. Calculado no backend (regras.py), a mesma
// definicao que o chat usa: GET /resumo/pagamentos.

import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api.js'
import { useDados } from '../dados.jsx'
import { MESES, dataPt, euros, hojeISO, mesCurto, mesNome } from '../util.js'
import { Aguardar, Cabecalho, Erro } from './comum.jsx'

export default function Inicio() {
  return (
    <Aguardar>
      <Painel />
    </Aguardar>
  )
}

function Painel() {
  const { socios } = useDados()
  const navigate = useNavigate()
  const [r, setR] = useState(null)
  const [erro, setErro] = useState('')

  // Recarrega quando a lista de socios muda (ex.: depois de gravar uma ficha).
  useEffect(() => {
    api('/resumo/pagamentos').then(setR).catch((e) => setErro(e.message))
  }, [socios])

  const nomeMes = r ? MESES[Number(r.hoje.slice(5, 7)) - 1].toLowerCase() : ''

  return (
    <>
      <Cabecalho titulo="Início" descricao={`Situação dos pagamentos a ${dataPt(hojeISO())}`}>
        <Link to="/socios/novo" className="btn btn-primario">Novo sócio</Link>
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
              <p className="tile-lbl">Recebido em {nomeMes}</p>
              <p className="tile-valor">{euros(r.recebidoMes)}</p>
              <p className="tile-nota">{r.nRecebidoMes} pagamento(s)</p>
            </div>
            <div className="tile">
              <p className="tile-lbl">{mesNome(r.mesAnterior)} por pagar</p>
              <p className="tile-valor">{euros(r.valorDentroDoPrazo)}</p>
              <p className="tile-nota">{r.dentroDoPrazo} sócio(s) · ainda no prazo (até {dataPt(r.prazoMesAnterior)})</p>
            </div>
          </div>

          <h2 className="subtitulo">Mensalidades em atraso</h2>
          <p className="texto-ajuda">
            A mensalidade de cada mês pode ser paga até ao dia {r.diaLimite} do mês seguinte. Depois disso aparece aqui.
          </p>
          {r.atrasos.length === 0 ? (
            <p className="vazio">Tudo em dia. Não há mensalidades em atraso.</p>
          ) : (
            <div className="tabela-scroll">
              <table className="tabela tabela-clicavel">
                <thead>
                  <tr>
                    <th>Sócio</th>
                    <th>Meses em atraso</th>
                    <th className="num">Valor</th>
                  </tr>
                </thead>
                <tbody>
                  {r.atrasos.map(({ socioId, nome, estado, meses, total }) => (
                    <tr key={socioId} onClick={() => navigate(`/socios/${socioId}`)}>
                      <td>
                        <Link to={`/socios/${socioId}`} onClick={(e) => e.stopPropagation()}>{nome}</Link>
                        {estado === 'INATIVO' && <span className="etiqueta">Inativo</span>}
                      </td>
                      <td className="celula-chips">
                        {meses.map((d) => (
                          <span key={d.mes} className="chip chip-atraso" title={`${euros(d.valor)} · prazo ${dataPt(d.prazo)}`}>
                            {mesCurto(d.mes)}
                          </span>
                        ))}
                      </td>
                      <td className="num">{euros(total)}</td>
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
