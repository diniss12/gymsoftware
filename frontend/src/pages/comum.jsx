import { useDados } from '../dados.jsx'

/** Mostra "a carregar" / erro enquanto a lista de socios e planos nao chega. */
export function Aguardar({ children }) {
  const { socios, planos, erro, recarregar } = useDados()
  if (erro)
    return (
      <div className="aviso aviso-erro">
        <p>Não foi possível carregar os dados: {erro}</p>
        <button className="btn btn-ghost" onClick={recarregar}>Tentar de novo</button>
      </div>
    )
  if (!socios || !planos) return <p className="muted">A carregar…</p>
  return children
}

export function Cabecalho({ eyebrow, titulo, children }) {
  return (
    <div className="cabecalho">
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1 className="titulo">{titulo}</h1>
      </div>
      {children && <div className="cabecalho-acoes">{children}</div>}
    </div>
  )
}

export function Erro({ children }) {
  return children ? <p className="aviso aviso-erro" role="alert">{children}</p> : null
}
