import { useEffect, useState } from 'react'
import { Button } from '../components/ui/Button'
import { Icon } from '../components/ui/Icon'
import { downloadFile } from '../lib/download'

/**
 * Widget embebible de seguro en el punto de compra (iframe de aliados).
 * Sin TopNav ni auth: un aliado (e-commerce, banco) lo integra con
 * `<iframe src=".../embed?tipo=viaje&partner=KEY&nombre=TiendaViajes">`.
 * Flujo: prima al instante → datos mínimos + consentimiento → póliza emitida.
 */

type EmbeddedOption = {
  producto: string
  aseguradora: string
  tipo: string
  moneda: string
  prima_mensual_local: number
  periodicidad: string
  coberturas: string[]
}

type IssuedPolicy = {
  policyNumber?: string
  download_url?: string | null
  referred?: boolean
  mensaje?: string
}

type Phase = 'loading' | 'quote' | 'issuing' | 'done' | 'error'

export function EmbedQuotePage() {
  const params = new URLSearchParams(window.location.search)
  const tipo = params.get('tipo') ?? 'viaje'
  const partnerKey = params.get('partner') ?? 'demo-partner-2026'
  const partnerName = params.get('nombre') ?? 'nuestro aliado'
  const dias = params.get('dias')
  const valor = params.get('valor')

  const [phase, setPhase] = useState<Phase>('loading')
  const [option, setOption] = useState<EmbeddedOption | null>(null)
  const [issued, setIssued] = useState<IssuedPolicy | null>(null)
  const [error, setError] = useState('')
  const [fullName, setFullName] = useState('')
  const [documentId, setDocumentId] = useState('')
  const [email, setEmail] = useState('')
  const [consent, setConsent] = useState(false)

  useEffect(() => {
    let alive = true
    fetch('/api/embedded/quote', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        partner_key: partnerKey,
        tipo,
        country: 'CO',
        ...(dias ? { dias_viaje: Number(dias) } : {}),
        ...(valor ? { valor_bien_usd: Number(valor) } : {}),
      }),
    })
      .then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then((d) => {
        if (!alive) return
        setOption(d.opcion)
        setPhase('quote')
      })
      .catch(() => {
        if (!alive) return
        setError('No pudimos cotizar en este momento.')
        setPhase('error')
      })
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- los params vienen de la URL, fijos por carga
  }, [])

  const buy = async () => {
    if (!option || !fullName.trim() || !documentId.trim() || !consent) return
    setPhase('issuing')
    try {
      const r = await fetch('/api/embedded/checkout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          partner_key: partnerKey,
          tipo: option.tipo,
          monthly_premium_cop: option.prima_mensual_local,
          customer: {
            fullName: fullName.trim(),
            documentId: documentId.trim(),
            ...(email.trim() ? { email: email.trim() } : {}),
          },
          consent_data: true,
          coverage: {
            aseguradora: option.aseguradora,
            coberturas: option.coberturas,
            resumen: `${option.producto} (${option.aseguradora}) — vía ${partnerName}`,
          },
          partner_name: partnerName,
        }),
      })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const d = (await r.json()) as IssuedPolicy
      setIssued(d)
      setPhase('done')
    } catch {
      setError('No pudimos emitir la póliza. Intenta de nuevo.')
      setPhase('error')
    }
  }

  const per = option?.periodicidad === 'por viaje' ? 'por viaje' : '/mes'

  return (
    <div className="flex min-h-svh items-center justify-center bg-background p-4">
      <div className="soft-forest-shadow w-full max-w-sm overflow-hidden rounded-2xl border border-outline-variant bg-surface-container-lowest">
        <div className="flex items-center gap-2 bg-primary px-4 py-3">
          <Icon name="shield" filled className="text-amber-cta" />
          <p className="text-sm font-bold text-on-primary">
            Protege tu compra
            <span className="ml-1 font-normal text-primary-fixed-dim">
              · con {partnerName}
            </span>
          </p>
        </div>

        {phase === 'loading' ? (
          <p className="p-6 text-center text-sm text-on-surface-variant">
            Calculando tu protección…
          </p>
        ) : null}

        {phase === 'error' ? (
          <p className="flex items-center gap-2 p-6 text-sm text-on-error-container">
            <Icon name="error" filled className="text-error" />
            {error}
          </p>
        ) : null}

        {(phase === 'quote' || phase === 'issuing') && option ? (
          <div className="p-5">
            <p className="text-xs uppercase tracking-wide text-on-surface-variant">
              {option.producto} · {option.aseguradora}
            </p>
            <p className="mt-1 text-3xl font-bold text-on-surface">
              {option.prima_mensual_local.toLocaleString('es-CO', {
                maximumFractionDigits: 0,
              })}{' '}
              <span className="text-sm font-semibold text-on-surface-variant">
                {option.moneda} {per}
              </span>
            </p>
            <ul className="mt-3 space-y-1">
              {option.coberturas.slice(0, 3).map((c) => (
                <li
                  key={c}
                  className="flex items-start gap-1.5 text-xs text-on-surface-variant"
                >
                  <Icon name="check_circle" filled className="mt-px text-[14px] text-primary" />
                  {c}
                </li>
              ))}
            </ul>

            <div className="mt-4 flex flex-col gap-2">
              <input
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Nombre completo"
                className="rounded-md border border-outline-variant bg-white px-3 py-2 text-sm text-on-surface outline-none focus:border-primary"
              />
              <input
                value={documentId}
                onChange={(e) => setDocumentId(e.target.value)}
                placeholder="Número de documento (CC)"
                inputMode="numeric"
                className="rounded-md border border-outline-variant bg-white px-3 py-2 text-sm text-on-surface outline-none focus:border-primary"
              />
              <input
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Correo (opcional)"
                type="email"
                className="rounded-md border border-outline-variant bg-white px-3 py-2 text-sm text-on-surface outline-none focus:border-primary"
              />
              <label className="flex items-start gap-2 text-[11px] text-on-surface-variant">
                <input
                  type="checkbox"
                  checked={consent}
                  onChange={(e) => setConsent(e.target.checked)}
                  className="mt-0.5 accent-primary"
                />
                Autorizo el tratamiento de mis datos personales (Ley 1581/2012)
                para emitir la póliza.
              </label>
            </div>

            <Button
              variant="cta"
              className="mt-4 w-full rounded-full"
              disabled={
                phase === 'issuing' ||
                !fullName.trim() ||
                !documentId.trim() ||
                !consent
              }
              onClick={buy}
            >
              <Icon name="lock" filled className="text-[18px]" />
              {phase === 'issuing' ? 'Emitiendo…' : 'Asegurar mi compra'}
            </Button>
          </div>
        ) : null}

        {phase === 'done' && issued ? (
          <div className="p-5 text-center">
            {issued.referred ? (
              <>
                <Icon
                  name="supervisor_account"
                  filled
                  className="text-[40px] text-amber-cta"
                />
                <p className="mt-2 font-bold text-on-surface">
                  Un asesor revisa tu solicitud
                </p>
                <p className="mt-1 text-xs text-on-surface-variant">
                  {issued.mensaje ?? 'Te contactaremos en menos de 24 horas.'}
                </p>
              </>
            ) : (
              <>
                <Icon name="verified" filled className="text-[40px] text-primary" />
                <p className="mt-2 font-bold text-on-surface">
                  ¡Ya quedaste protegido!
                </p>
                <p className="mt-1 font-mono text-sm font-bold text-primary">
                  {issued.policyNumber}
                </p>
                {issued.download_url ? (
                  <Button
                    variant="primary"
                    className="mt-3 w-full rounded-full"
                    onClick={() => downloadFile(issued.download_url as string)}
                  >
                    <Icon name="download" filled className="text-[18px]" />
                    Descargar póliza
                  </Button>
                ) : null}
              </>
            )}
          </div>
        ) : null}

        <p className="border-t border-outline-variant/40 px-4 py-2 text-center text-[10px] text-outline">
          Seguro embebido por Tequendama · Colsubsidio distribuye
        </p>
      </div>
    </div>
  )
}
