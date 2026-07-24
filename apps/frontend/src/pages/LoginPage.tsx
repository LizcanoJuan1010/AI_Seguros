/**
 * Pantalla de login (estética Tequendama: paleta Mist/Forest, Card + Button).
 *
 * Flujo:
 *  - Campos email + password, estado de error, botón "Ingresar".
 *  - Al autenticar, redirige por rol: GERENTE/ADMIN → `/gerente`, si no
 *    → `/asistente`.
 *  - Si ya hay sesión activa, redirige sin mostrar el formulario.
 *  - Muestra las credenciales demo como ayuda.
 */
import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { Icon } from '../components/ui/Icon'
import { MistBackground } from '../features/landing/MistBackground'

/** Ruta destino según el rol del usuario autenticado. */
function homeForRole(role: string): string {
  const r = role.toUpperCase()
  return r === 'GERENTE' || r === 'ADMIN' ? '/gerente' : '/asistente'
}

export function LoginPage() {
  const { status, user, signIn } = useAuth()
  const navigate = useNavigate()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  // Si ya hay sesión (o se acaba de crear), redirige por rol.
  useEffect(() => {
    if (status === 'authenticated' && user) {
      navigate(homeForRole(user.role), { replace: true })
    }
  }, [status, user, navigate])

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    if (submitting) return
    setError(null)
    setSubmitting(true)
    const res = await signIn(email.trim(), password)
    setSubmitting(false)
    if (!res.ok) {
      setError(res.error ?? 'No se pudo iniciar sesión')
    }
    // En caso de éxito, el useEffect de arriba redirige por rol.
  }

  const inputClass =
    'w-full rounded-md border border-outline-variant bg-surface-container-lowest px-4 py-3 text-body-md text-on-surface placeholder:text-on-surface-variant/60 outline-none transition-colors focus:border-primary focus:ring-2 focus:ring-primary/20'

  return (
    <div className="relative flex min-h-svh w-full items-center justify-center bg-mist-white px-margin-mobile py-12">
      <MistBackground />

      <Card className="relative z-10 w-full max-w-md p-stack-lg">
        <div className="mb-8 flex flex-col items-center gap-3 text-center">
          <img src="/assets/logo.svg" alt="Tequendama" className="h-14 w-auto" />
          <div>
            <h1 className="text-headline-lg text-primary">Tequendama</h1>
            <p className="mt-1 text-body-md text-on-surface-variant">
              Ingresa para acceder a tu asistente de ventas
            </p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-stack-md">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="email" className="text-label-sm text-on-surface-variant">
              Correo electrónico
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="gerente@colsubsidio.demo"
              className={inputClass}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="password" className="text-label-sm text-on-surface-variant">
              Contraseña
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              className={inputClass}
            />
          </div>

          {error && (
            <div
              role="alert"
              className="flex items-center gap-2 rounded-md bg-error-container px-3 py-2.5 text-label-md text-on-error-container"
            >
              <Icon name="error" className="text-[20px]" />
              <span>{error}</span>
            </div>
          )}

          <Button
            type="submit"
            variant="cta"
            className="w-full"
            disabled={submitting}
          >
            {submitting ? (
              <>
                <span className="size-4 animate-spin rounded-full border-2 border-primary/40 border-t-primary" />
                Ingresando…
              </>
            ) : (
              <>
                <Icon name="login" className="text-[20px]" />
                Ingresar
              </>
            )}
          </Button>
        </form>

        <div className="mt-6 rounded-md border border-outline-variant/60 bg-surface-container-low px-4 py-3 text-label-sm text-on-surface-variant">
          <p className="font-bold text-on-surface">Credenciales demo</p>
          <p className="mt-1">
            <span className="font-mono">gerente@colsubsidio.demo</span> /{' '}
            <span className="font-mono">demo123</span>
          </p>
        </div>
      </Card>
    </div>
  )
}
