// Assistente (POST /chat) numa barra lateral, aberta pelo botao flutuante no
// canto inferior direito. Fica montado em todas as paginas: a conversa
// mantem-se ao navegar e ao fechar/abrir. O historico vive so no browser e e
// enviado inteiro em cada pergunta (o backend nao guarda conversas).
// Pagamentos propostos aparecem como cartoes: so ao carregar em "Confirmar" e
// que a API normal os grava.

import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from './api.js'
import { useDados } from './dados.jsx'
import { METODOS, dataPt, euros, mesNome } from './util.js'

const SUGESTOES = [
  'Quem tem mensalidades em atraso?',
  'Quanto recebi este mês?',
  'Quantos sócios ativos há por plano?',
]

function IconeIA() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" aria-hidden="true">
      <path d="M11 3l1.9 5.1L18 10l-5.1 1.9L11 17l-1.9-5.1L4 10l5.1-1.9z" />
      <path d="M18.5 14.5l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8z" />
    </svg>
  )
}

export default function Assistente() {
  const [aberto, setAberto] = useState(false)
  // mensagens: { role: 'user' | 'assistant', texto, propostas? }
  const [mensagens, setMensagens] = useState([])
  const [texto, setTexto] = useState('')
  const [aPensar, setAPensar] = useState(false)
  const [erro, setErro] = useState('')
  const fim = useRef(null)
  const campo = useRef(null)

  // Esc fecha; ao abrir, o cursor vai para o campo de texto.
  useEffect(() => {
    if (!aberto) return
    campo.current?.focus()
    const tecla = (e) => e.key === 'Escape' && setAberto(false)
    window.addEventListener('keydown', tecla)
    return () => window.removeEventListener('keydown', tecla)
  }, [aberto])

  useEffect(() => {
    fim.current?.scrollIntoView({ block: 'end' })
  }, [mensagens, aPensar, aberto])

  async function enviar(pergunta) {
    const t = pergunta.trim()
    if (!t || aPensar) return
    const novas = [...mensagens, { role: 'user', texto: t }]
    setMensagens(novas)
    setTexto('')
    setErro('')
    setAPensar(true)
    try {
      const r = await api('/chat', {
        method: 'POST',
        body: { mensagens: novas.map(({ role, texto }) => ({ role, texto })) },
      })
      setMensagens([...novas, { role: 'assistant', texto: r.resposta, propostas: r.propostas }])
    } catch (e) {
      setErro(e.message)
      setMensagens(mensagens) // devolve a pergunta ao campo para tentar de novo
      setTexto(t)
    } finally {
      setAPensar(false)
      campo.current?.focus()
    }
  }

  if (!aberto) {
    return (
      <button className="ia-botao" onClick={() => setAberto(true)} aria-label="Abrir assistente" title="Assistente">
        <IconeIA />
      </button>
    )
  }

  return (
    <aside className="ia-painel" role="dialog" aria-label="Assistente">
      <header className="ia-cabecalho">
        <span className="ia-titulo"><IconeIA /> Assistente</span>
        <div className="ia-acoes">
          {mensagens.length > 0 && (
            <button className="btn btn-pequeno" onClick={() => { setMensagens([]); setErro('') }} disabled={aPensar}>
              Nova conversa
            </button>
          )}
          <button className="ia-fechar" onClick={() => setAberto(false)} aria-label="Fechar assistente">×</button>
        </div>
      </header>

      <div className="ia-corpo">
        {mensagens.length === 0 && (
          <div className="chat-vazio">
            <p className="muted">Pergunta sobre sócios, pagamentos e receita, ou regista um pagamento ("o João pagou novembro em dinheiro").</p>
            <div className="chat-sugestoes">
              {SUGESTOES.map((s) => (
                <button key={s} className="btn btn-pequeno" onClick={() => enviar(s)}>{s}</button>
              ))}
            </div>
          </div>
        )}
        {mensagens.map((m, i) => (
          <div key={i} className={`chat-msg chat-${m.role}`}>
            <div className="chat-bolha">{m.texto}</div>
            {m.propostas?.map((p, j) => <PropostaPagamento key={j} proposta={p} />)}
          </div>
        ))}
        {aPensar && <div className="chat-msg chat-assistant"><div className="chat-bolha muted">A pensar…</div></div>}
        <div ref={fim} />
      </div>

      <footer className="ia-rodape">
        {erro && <p className="aviso aviso-erro" role="alert">{erro}</p>}
        <form className="chat-form" onSubmit={(e) => { e.preventDefault(); enviar(texto) }}>
          <input
            ref={campo}
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            placeholder="Escreve uma pergunta…"
            maxLength={2000}
            disabled={aPensar}
            aria-label="Pergunta"
          />
          <button className="btn btn-primario" disabled={aPensar || !texto.trim()}>Enviar</button>
        </form>
        <p className="ia-aviso">O assistente pode enganar-se. Confirma os dados antes de registar um pagamento.</p>
      </footer>
    </aside>
  )
}

/** Cartao de confirmacao: so aqui o pagamento e gravado (POST normal da API). */
function PropostaPagamento({ proposta: p }) {
  const { recarregar } = useDados()
  const [estado, setEstado] = useState('pendente') // pendente | a-gravar | registado | cancelado
  const [erro, setErro] = useState('')

  async function confirmar() {
    setEstado('a-gravar')
    setErro('')
    try {
      await api(`/socios/${p.socioId}/pagamentos`, {
        method: 'POST',
        body: { mes: p.mes, valor: p.valor, metodo: p.metodo, dataPagamento: p.dataPagamento, notas: p.notas },
      })
      setEstado('registado')
      recarregar() // o Inicio e as Estatisticas por tras do painel atualizam-se
    } catch (e) {
      setErro(e.message)
      setEstado('pendente')
    }
  }

  return (
    <div className={`proposta proposta-${estado}`}>
      <p className="proposta-titulo">Registar pagamento</p>
      <dl className="dados">
        <dt>Sócio</dt><dd><Link to={`/socios/${p.socioId}`}>{p.nome}</Link></dd>
        <dt>Mensalidade</dt><dd>{mesNome(p.mes)}</dd>
        <dt>Valor</dt><dd>{euros(p.valor)}</dd>
        <dt>Método</dt><dd>{METODOS[p.metodo] ?? p.metodo}</dd>
        <dt>Pago em</dt><dd>{dataPt(p.dataPagamento)}</dd>
        {p.notas && (<><dt>Notas</dt><dd>{p.notas}</dd></>)}
      </dl>
      {erro && <p className="campo-erro">{erro}</p>}
      {estado === 'registado' && <p className="proposta-estado">Pagamento registado.</p>}
      {estado === 'cancelado' && <p className="proposta-estado muted">Cancelado. Nada foi registado.</p>}
      {(estado === 'pendente' || estado === 'a-gravar') && (
        <div className="formulario-acoes">
          <button className="btn btn-primario btn-pequeno" onClick={confirmar} disabled={estado === 'a-gravar'}>
            {estado === 'a-gravar' ? 'A registar…' : 'Confirmar'}
          </button>
          <button className="btn btn-pequeno" onClick={() => setEstado('cancelado')} disabled={estado === 'a-gravar'}>
            Cancelar
          </button>
        </div>
      )}
    </div>
  )
}
