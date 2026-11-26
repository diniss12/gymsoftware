// Login feito a mao com as funcoes do Amplify (em vez do <Authenticator>):
// controlo total do aspeto e bundle mais pequeno. O protocolo SRP continua a
// ser tratado pelo Amplify: a password nunca e enviada em claro ao Cognito.

import { useState } from 'react'
import { confirmResetPassword, confirmSignIn, resetPassword, signIn } from 'aws-amplify/auth'
import logo from './assets/logo.png'

const REGRA_PASSWORD = 'Mínimo 12 caracteres, com maiúsculas, minúsculas e números.'

function mensagem(e) {
  switch (e?.name) {
    case 'NotAuthorizedException':
      return e.message?.includes('expired')
        ? 'A password temporária expirou. Pede uma nova ao administrador.'
        : 'Email ou password incorretos.'
    case 'InvalidPasswordException':
      return `Password não cumpre as regras. ${REGRA_PASSWORD}`
    case 'CodeMismatchException':
      return 'Código incorreto.'
    case 'ExpiredCodeException':
      return 'Código expirado. Pede um novo.'
    case 'LimitExceededException':
    case 'TooManyRequestsException':
      return 'Demasiadas tentativas. Espera uns minutos.'
    default:
      return e?.message || 'Ocorreu um erro.'
  }
}

export default function Login({ onEntrar }) {
  // passo: 'entrar' | 'nova' (1.o login) | 'esqueci' | 'codigo'
  const [passo, setPasso] = useState('entrar')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [nova, setNova] = useState('')
  const [confirma, setConfirma] = useState('')
  const [codigo, setCodigo] = useState('')
  const [erro, setErro] = useState('')
  const [info, setInfo] = useState('')
  const [aEnviar, setAEnviar] = useState(false)

  async function executar(fn) {
    setErro('')
    setAEnviar(true)
    try {
      await fn()
    } catch (e) {
      setErro(mensagem(e))
    } finally {
      setAEnviar(false)
    }
  }

  function passwordsIguais() {
    if (nova !== confirma) {
      setErro('As passwords não coincidem.')
      return false
    }
    return true
  }

  const entrar = (ev) => {
    ev.preventDefault()
    executar(async () => {
      const { isSignedIn, nextStep } = await signIn({ username: email.trim(), password })
      if (isSignedIn) return onEntrar()
      if (nextStep.signInStep === 'CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED') {
        setInfo('Primeiro acesso: define a tua password definitiva.')
        return setPasso('nova')
      }
      if (nextStep.signInStep === 'RESET_PASSWORD') return setPasso('esqueci')
      throw new Error(`Passo de login não suportado: ${nextStep.signInStep}`)
    })
  }

  const definirNova = (ev) => {
    ev.preventDefault()
    if (!passwordsIguais()) return
    executar(async () => {
      const { isSignedIn } = await confirmSignIn({ challengeResponse: nova })
      if (isSignedIn) onEntrar()
    })
  }

  const pedirCodigo = (ev) => {
    ev.preventDefault()
    executar(async () => {
      await resetPassword({ username: email.trim() })
      setInfo('Se o email existir, vais receber um código.')
      setPasso('codigo')
    })
  }

  const repor = (ev) => {
    ev.preventDefault()
    if (!passwordsIguais()) return
    executar(async () => {
      await confirmResetPassword({ username: email.trim(), confirmationCode: codigo.trim(), newPassword: nova })
      setInfo('Password alterada. Já podes entrar.')
      setPassword('')
      setNova('')
      setConfirma('')
      setPasso('entrar')
    })
  }

  const voltar = () => {
    setErro('')
    setInfo('')
    setPasso('entrar')
  }

  const camposNova = (
    <>
      <label>
        Nova password
        <input type="password" autoComplete="new-password" value={nova} onChange={(e) => setNova(e.target.value)} required minLength={12} />
      </label>
      <label>
        Confirmar password
        <input type="password" autoComplete="new-password" value={confirma} onChange={(e) => setConfirma(e.target.value)} required minLength={12} />
      </label>
      <p className="login-dica">{REGRA_PASSWORD}</p>
    </>
  )

  return (
    <main className="login">
      <div className="login-caixa">
        <img src={logo} alt="Ativo Fitness" className="login-logo" />
        <p className="login-eyebrow">Área de gestão</p>

        {info && <p className="login-info">{info}</p>}
        {erro && <p className="login-erro" role="alert">{erro}</p>}

        {passo === 'entrar' && (
          <form onSubmit={entrar}>
            <label>
              Email
              <input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
            </label>
            <label>
              Password
              <input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
            </label>
            <button className="btn btn-red" disabled={aEnviar}>{aEnviar ? 'A entrar…' : 'Entrar'}</button>
            <button type="button" className="login-link" onClick={() => { setErro(''); setInfo(''); setPasso('esqueci') }}>
              Esqueci-me da password
            </button>
          </form>
        )}

        {passo === 'nova' && (
          <form onSubmit={definirNova}>
            {camposNova}
            <button className="btn btn-red" disabled={aEnviar}>{aEnviar ? 'A guardar…' : 'Guardar e entrar'}</button>
          </form>
        )}

        {passo === 'esqueci' && (
          <form onSubmit={pedirCodigo}>
            <label>
              Email
              <input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
            </label>
            <button className="btn btn-red" disabled={aEnviar}>{aEnviar ? 'A enviar…' : 'Enviar código'}</button>
            <button type="button" className="login-link" onClick={voltar}>Voltar</button>
          </form>
        )}

        {passo === 'codigo' && (
          <form onSubmit={repor}>
            <label>
              Código recebido por email
              <input inputMode="numeric" autoComplete="one-time-code" value={codigo} onChange={(e) => setCodigo(e.target.value)} required autoFocus />
            </label>
            {camposNova}
            <button className="btn btn-red" disabled={aEnviar}>{aEnviar ? 'A guardar…' : 'Alterar password'}</button>
            <button type="button" className="login-link" onClick={voltar}>Voltar</button>
          </form>
        )}
      </div>
    </main>
  )
}
