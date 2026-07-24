/**
 * Login como pop-up (modal) sobre la vista actual: cuando la sesión no existe
 * o expira, NO se navega a otra página — el modal aparece encima, el usuario
 * ingresa y continúa exactamente donde estaba. Prellena el último email usado
 * (localStorage) para que "se guarde" entre visitas.
 */
import { useState, type FormEvent } from 'react'
import { useAuth } from '../contexts/AuthContext'
import { LS_LAST_EMAIL } from '../contexts/AuthContext'
import { Button } from './ui/Button'
import { Icon } from './ui/Icon'

function lastEmail(): string {
  try {
    return localStorage.getItem(LS_LAST_EMAIL) ?? ''
  } catch {
    return ''
  }
}

const inputClass =
  'w-full rounded-md border border-outline-variant bg-surface-container-lowest px-4 py-3 text-body-md text-on-surface placeholder:text-on-surface-variant/60 outline-none transition-colors focus:border-primary focus:ring-2 focus:ring-primary/20'

export function LoginModal() {
  const { signIn } = useAuth()
  const [email, setEmail] = useState(lastEmail)
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    if (submitting) return
    setError(null)
    setSubmitting(true)
    const res = await signIn(email.trim(), password)
    setSubmitting(false)
    if (!res.ok) {
      setError(res.error ?? 'No se pudo iniciar sesión')
      return
    }
    try {
      localStorage.setItem(LS_LAST_EMAIL, email.trim())
    } catch {
      /* almacenamiento no disponible */
    }
    // Con la sesión creada, RequireAuth renderiza la vista en la que estabas.
  }

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-forest-deep/30 px-4 backdrop-blur-md">
      <div className="glass-card w-full max-w-md rounded-2xl bg-white/85 p-8 shadow-2xl">
        <div className="mb-6 flex flex-col items-center gap-3 text-center">
          <img src="/assets/logo.svg" alt="Tequendama" className="h-12 w-auto" />
          <div>
            <h2 className="text-headline-md text-primary">Tu sesión expiró</h2>
            <p className="mt-1 text-body-md text-on-surface-variant">
              Ingresa de nuevo y continúa justo donde estabas.
            </p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <label className="flex flex-col gap-1.5">
            <span className="text-label-md text-on-surface">Correo</span>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="tu@correo.com"
              autoComplete="email"
              required
              className={inputClass}
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-label-md text-on-surface">Contraseña</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              autoComplete="current-password"
              required
              className={inputClass}
            />
          </label>

          {error && (
            <p className="flex items-center gap-2 rounded-md bg-error-container/50 px-3 py-2 text-label-md text-on-error-container">
              <Icon name="error" className="text-[18px]" />
              {error}
            </p>
          )}

          <Button
            type="submit"
            variant="primary"
            className="mt-1 w-full justify-center rounded-md py-3"
            disabled={submitting}
          >
            {submitting ? 'Ingresando…' : 'Ingresar'}
          </Button>
        </form>
      </div>
    </div>
  )
}
