// Login feito a mao com as funcoes do Amplify (em vez do <Authenticator>):
// controlo total do aspeto e bundle mais pequeno. O protocolo SRP continua a
// ser tratado pelo Amplify: a password nunca e enviada em claro ao Cognito.

import { useEffect, useRef, useState } from 'react'
import {
  confirmResetPassword,
  confirmSignIn,
  resetPassword,
  setUpTOTP,
  signIn,
  updateMFAPreference,
  verifyTOTPSetup,
} from 'aws-amplify/auth'
import QRCode from 'qrcode'
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
    case 'EnableSoftwareTokenMFAException':
      return 'Código incorreto. Confirma que a hora do telemóvel está certa.'
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
  // passo: 'entrar' | 'nova' (1.o login) | 'mfa' (codigo da app) | 'esqueci' | 'codigo'
  const [passo, setPasso] = useState('entrar')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [nova, setNova] = useState('')
  const [confirma, setConfirma] = useState('')
  const [codigo, setCodigo] = useState('')
  const [mfa, setMfa] = useState('')
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

  // O Cognito responde a cada passo com o que falta: nova password, codigo MFA...
  function seguir({ isSignedIn, nextStep }) {
    if (isSignedIn) return onEntrar()
    switch (nextStep.signInStep) {
      case 'CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED':
        setInfo('Primeiro acesso: define a tua password definitiva.')
        return setPasso('nova')
      case 'CONFIRM_SIGN_IN_WITH_TOTP_CODE':
        setInfo('')
        setMfa('')
        return setPasso('mfa')
      case 'RESET_PASSWORD':
        return setPasso('esqueci')
      default:
        throw new Error(`Passo de login não suportado: ${nextStep.signInStep}`)
    }
  }

  const entrar = (ev) => {
    ev.preventDefault()
    executar(async () => seguir(await signIn({ username: email.trim(), password })))
  }

  const definirNova = (ev) => {
    ev.preventDefault()
    if (!passwordsIguais()) return
    executar(async () => seguir(await confirmSignIn({ challengeResponse: nova })))
  }

  const confirmarMfa = (ev) => {
    ev.preventDefault()
    executar(async () => seguir(await confirmSignIn({ challengeResponse: mfa.trim() })))
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

        {passo === 'mfa' && (
          <form onSubmit={confirmarMfa}>
            <label>
              Código da app autenticadora
              <input
                inputMode="numeric"
                autoComplete="one-time-code"
                value={mfa}
                onChange={(e) => setMfa(e.target.value.replace(/\D/g, '').slice(0, 6))}
                required
                minLength={6}
                autoFocus
              />
            </label>
            <button className="btn btn-red" disabled={aEnviar}>{aEnviar ? 'A verificar…' : 'Confirmar'}</button>
            <button type="button" className="login-link" onClick={voltar}>Voltar</button>
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

/**
 * Configuracao obrigatoria do MFA (app autenticadora), mostrada depois do login
 * enquanto a conta nao tiver MFA. Gera um segredo no Cognito, mostra-o em QR
 * code, e so ativa depois de o utilizador provar que a app gera codigos certos.
 */
export function ConfigurarMFA({ email, onFeito, onSair }) {
  const [qr, setQr] = useState('')
  const [segredo, setSegredo] = useState('')
  const [codigo, setCodigo] = useState('')
  const [erro, setErro] = useState('')
  const [aEnviar, setAEnviar] = useState(false)
  const pedido = useRef(false) // cada setUpTOTP gera um segredo novo: pedir so uma vez

  useEffect(() => {
    if (pedido.current) return
    pedido.current = true
    setUpTOTP()
      .then(async (detalhes) => {
        const uri = detalhes.getSetupUri('Ativo Fitness', email).toString()
        setSegredo(detalhes.sharedSecret)
        setQr(await QRCode.toDataURL(uri, { margin: 1, width: 220 }))
      })
      .catch((e) => setErro(mensagem(e)))
  }, [email])

  const confirmar = async (ev) => {
    ev.preventDefault()
    setErro('')
    setAEnviar(true)
    try {
      await verifyTOTPSetup({ code: codigo.trim() })
      await updateMFAPreference({ totp: 'PREFERRED' })
      onFeito()
    } catch (e) {
      setErro(mensagem(e))
      setAEnviar(false)
    }
  }

  return (
    <main className="login">
      <div className="login-caixa">
        <img src={logo} alt="Ativo Fitness" className="login-logo" />
        <p className="login-eyebrow">Proteger a conta</p>

        <p className="login-info">
          Para proteger os dados dos sócios, o acesso passa a pedir também um código de uma app autenticadora
          (Google Authenticator, Microsoft Authenticator, 1Password…).
        </p>
        {erro && <p className="login-erro" role="alert">{erro}</p>}

        <form onSubmit={confirmar}>
          <p className="login-dica">1. Na app autenticadora, adiciona uma conta e lê este código QR:</p>
          {qr ? <img src={qr} alt="Código QR para a app autenticadora" className="login-qr" /> : <p className="login-dica">A gerar…</p>}
          {segredo && (
            <p className="login-dica">
              Sem câmara? Escreve esta chave na app: <span className="login-segredo">{segredo}</span>
            </p>
          )}
          <label>
            2. Código de 6 dígitos que a app mostra
            <input
              inputMode="numeric"
              autoComplete="one-time-code"
              value={codigo}
              onChange={(e) => setCodigo(e.target.value.replace(/\D/g, '').slice(0, 6))}
              required
              minLength={6}
            />
          </label>
          <button className="btn btn-red" disabled={aEnviar || !qr}>{aEnviar ? 'A ativar…' : 'Ativar e entrar'}</button>
          <button type="button" className="login-link" onClick={onSair}>Sair</button>
        </form>
      </div>
    </main>
  )
}
