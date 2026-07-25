/**
 * Crear / editar un cliente y adjuntarle documentos. Modal sobre la Cartera.
 * En modo edición carga los datos completos (customerFull) para prellenar
 * todos los campos y listar/gestionar los archivos ya subidos. La subida de
 * documentos requiere un cliente ya guardado (necesita su id).
 */
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Button } from '../../components/ui/Button'
import { Icon } from '../../components/ui/Icon'
import {
  api,
  type CustomerAttachment,
  type CustomerInput,
} from '../../lib/api'

const inputClass =
  'w-full rounded-md border border-outline-variant bg-surface-container-lowest px-3 py-2.5 text-body-md text-on-surface placeholder:text-on-surface-variant/60 outline-none transition-colors focus:border-primary focus:ring-2 focus:ring-primary/20'

const DOC_TYPES = ['CC', 'CE', 'TI', 'NIT', 'PP', 'PA']
/** Redes / canales de origen (controlado para que el KPI agrupe limpio). */
const REFERRAL_SOURCES = [
  'Instagram',
  'Facebook',
  'TikTok',
  'WhatsApp',
  'Google',
  'YouTube',
  'LinkedIn',
  'Referido',
  'Otro',
]
const UPLOAD_ACCEPT =
  '.pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg,.webp,.txt'

function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

type Props = {
  mode: 'create' | 'edit'
  customerId?: string
  onClose: () => void
  /** Se llama tras crear/editar para que la cartera refresque. */
  onSaved: () => void
}

const EMPTY: CustomerInput = { documentType: 'CC', consentData: false }

export function CustomerFormModal({ mode, customerId, onClose, onSaved }: Props) {
  const [form, setForm] = useState<CustomerInput>(EMPTY)
  const [docs, setDocs] = useState<CustomerAttachment[]>([])
  const [loading, setLoading] = useState(mode === 'edit')
  const [submitting, setSubmitting] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  // Modo edición: trae los datos completos + documentos para prellenar.
  useEffect(() => {
    if (mode !== 'edit' || !customerId) return
    let alive = true
    api
      .customerFull(customerId)
      .then((full) => {
        if (!alive) return
        const c = full.customer
        setForm({
          fullName: c.fullName ?? '',
          documentType: c.documentType ?? 'CC',
          documentId: c.documentId ?? '',
          email: c.email ?? '',
          phone: c.phone ?? '',
          birthDate: c.birthDate ? c.birthDate.slice(0, 10) : '',
          city: c.city ?? '',
          department: c.department ?? '',
          consentData: c.consentData,
          notes: c.notes ?? '',
          referralSource: c.referralSource ?? '',
          referralLink: c.referralLink ?? '',
        })
        setDocs(full.documents ?? [])
      })
      .catch(() => alive && setError('No se pudo cargar el cliente.'))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [mode, customerId])

  const set = <K extends keyof CustomerInput>(key: K, value: CustomerInput[K]) =>
    setForm((f) => ({ ...f, [key]: value }))

  // Limpia strings vacíos para no mandar "" al backend.
  const clean = (input: CustomerInput): CustomerInput => {
    const out: CustomerInput = {}
    for (const [k, v] of Object.entries(input)) {
      if (typeof v === 'string') {
        if (v.trim()) (out as Record<string, unknown>)[k] = v.trim()
      } else if (v !== undefined) {
        (out as Record<string, unknown>)[k] = v
      }
    }
    return out
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (submitting) return
    setError(null)
    setSubmitting(true)
    try {
      if (mode === 'create') {
        await api.createCustomer(clean(form))
      } else if (customerId) {
        await api.updateCustomer(customerId, clean(form))
      }
      onSaved()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo guardar.')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleFiles(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? [])
    e.target.value = ''
    if (!files.length || !customerId) return
    setError(null)
    setUploading(true)
    try {
      const created = await api.uploadCustomerDocuments(customerId, files)
      setDocs((prev) => [...created, ...prev])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo subir el archivo.')
    } finally {
      setUploading(false)
    }
  }

  async function removeDoc(docId: string) {
    try {
      await api.deleteCustomerDocument(docId)
      setDocs((prev) => prev.filter((d) => d.id !== docId))
    } catch {
      setError('No se pudo eliminar el documento.')
    }
  }

  return (
    <div
      className="fixed inset-0 z-[90] flex items-center justify-center overflow-y-auto bg-forest-deep/30 px-4 py-8 backdrop-blur-md"
      onClick={onClose}
    >
      <div
        className="glass-card my-auto max-h-[calc(100svh-4rem)] w-full max-w-2xl overflow-y-auto rounded-2xl bg-white/90 p-6 shadow-2xl sm:p-8"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <div className="mb-6 flex items-start justify-between gap-4">
          <div>
            <h2 className="text-headline-md text-primary">
              {mode === 'create' ? 'Nuevo cliente' : 'Editar cliente'}
            </h2>
            <p className="mt-1 text-body-md text-on-surface-variant">
              {mode === 'create'
                ? 'Registra un cliente en la cartera del equipo.'
                : 'Actualiza los datos y adjunta documentos.'}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar"
            className="flex size-9 shrink-0 items-center justify-center rounded-full border border-outline-variant/60 text-on-surface-variant transition-colors hover:bg-surface-variant"
          >
            <Icon name="close" className="text-[20px]" />
          </button>
        </div>

        {loading ? (
          <p className="py-10 text-center text-body-md text-on-surface-variant">
            Cargando…
          </p>
        ) : (
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <label className="flex flex-col gap-1.5">
              <span className="text-label-md text-on-surface">Nombre completo</span>
              <input
                className={inputClass}
                value={form.fullName ?? ''}
                onChange={(e) => set('fullName', e.target.value)}
                placeholder="Nombre y apellidos"
              />
            </label>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-[110px_1fr]">
              <label className="flex flex-col gap-1.5">
                <span className="text-label-md text-on-surface">Tipo doc.</span>
                <select
                  className={inputClass}
                  value={form.documentType ?? 'CC'}
                  onChange={(e) => set('documentType', e.target.value)}
                >
                  {DOC_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="text-label-md text-on-surface">Número de documento</span>
                <input
                  className={inputClass}
                  value={form.documentId ?? ''}
                  onChange={(e) => set('documentId', e.target.value)}
                  placeholder="Ej: 1020304050"
                />
              </label>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <label className="flex flex-col gap-1.5">
                <span className="text-label-md text-on-surface">Correo</span>
                <input
                  type="email"
                  className={inputClass}
                  value={form.email ?? ''}
                  onChange={(e) => set('email', e.target.value)}
                  placeholder="cliente@correo.com"
                />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="text-label-md text-on-surface">Teléfono</span>
                <input
                  className={inputClass}
                  value={form.phone ?? ''}
                  onChange={(e) => set('phone', e.target.value)}
                  placeholder="+57 300 000 0000"
                />
              </label>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <label className="flex flex-col gap-1.5">
                <span className="text-label-md text-on-surface">Nacimiento</span>
                <input
                  type="date"
                  className={inputClass}
                  value={form.birthDate ?? ''}
                  onChange={(e) => set('birthDate', e.target.value)}
                />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="text-label-md text-on-surface">Ciudad</span>
                <input
                  className={inputClass}
                  value={form.city ?? ''}
                  onChange={(e) => set('city', e.target.value)}
                  placeholder="Bogotá"
                />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="text-label-md text-on-surface">Departamento</span>
                <input
                  className={inputClass}
                  value={form.department ?? ''}
                  onChange={(e) => set('department', e.target.value)}
                  placeholder="Cundinamarca"
                />
              </label>
            </div>

            {/* Adquisición: por dónde llegó el cliente (alimenta el KPI). */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-[180px_1fr]">
              <label className="flex flex-col gap-1.5">
                <span className="text-label-md text-on-surface">
                  Red social / origen
                </span>
                <select
                  className={inputClass}
                  value={form.referralSource ?? ''}
                  onChange={(e) => set('referralSource', e.target.value)}
                >
                  <option value="">Sin registrar</option>
                  {REFERRAL_SOURCES.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="text-label-md text-on-surface">
                  Link por el que llegó
                </span>
                <input
                  className={inputClass}
                  value={form.referralLink ?? ''}
                  onChange={(e) => set('referralLink', e.target.value)}
                  placeholder="https://instagram.com/p/…"
                />
              </label>
            </div>

            <label className="flex flex-col gap-1.5">
              <span className="text-label-md text-on-surface">Notas / observaciones</span>
              <textarea
                className={`${inputClass} min-h-20 resize-y`}
                value={form.notes ?? ''}
                onChange={(e) => set('notes', e.target.value)}
                placeholder="Información adicional del cliente…"
              />
            </label>

            <label className="flex items-center gap-2.5">
              <input
                type="checkbox"
                className="size-4 accent-primary"
                checked={form.consentData ?? false}
                onChange={(e) => set('consentData', e.target.checked)}
              />
              <span className="text-label-md text-on-surface">
                Autoriza tratamiento de datos (Habeas Data, Ley 1581/2012)
              </span>
            </label>

            {/* Documentos: solo en edición (necesita el id del cliente). */}
            {mode === 'edit' && customerId && (
              <div className="rounded-lg border border-outline-variant/50 bg-surface-container-lowest/60 p-4">
                <div className="mb-3 flex items-center justify-between">
                  <span className="flex items-center gap-2 text-label-md font-bold text-on-surface">
                    <Icon name="attach_file" className="text-[18px] text-primary" />
                    Documentos ({docs.length})
                  </span>
                  <input
                    ref={fileRef}
                    type="file"
                    multiple
                    accept={UPLOAD_ACCEPT}
                    className="hidden"
                    onChange={handleFiles}
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    className="rounded-md px-3 py-1.5 text-label-sm"
                    disabled={uploading}
                    onClick={() => fileRef.current?.click()}
                  >
                    <Icon name="upload" className="text-[16px]" />
                    {uploading ? 'Subiendo…' : 'Subir'}
                  </Button>
                </div>
                {docs.length === 0 ? (
                  <p className="text-label-sm text-on-surface-variant">
                    Aún no hay archivos adjuntos.
                  </p>
                ) : (
                  <ul className="flex flex-col divide-y divide-outline-variant/40">
                    {docs.map((d) => (
                      <li
                        key={d.id}
                        className="flex items-center gap-3 py-2 text-label-sm"
                      >
                        <Icon
                          name="description"
                          className="shrink-0 text-[18px] text-primary"
                        />
                        <span className="min-w-0 flex-1 truncate text-on-surface">
                          {d.filename}
                        </span>
                        <span className="shrink-0 text-on-surface-variant">
                          {fmtSize(d.sizeBytes)}
                        </span>
                        <button
                          type="button"
                          aria-label="Descargar"
                          onClick={() =>
                            api.downloadCustomerDocument(d.id, d.filename)
                          }
                          className="shrink-0 text-on-surface-variant transition-colors hover:text-primary"
                        >
                          <Icon name="download" className="text-[18px]" />
                        </button>
                        <button
                          type="button"
                          aria-label="Eliminar"
                          onClick={() => removeDoc(d.id)}
                          className="shrink-0 text-on-surface-variant transition-colors hover:text-error"
                        >
                          <Icon name="delete" className="text-[18px]" />
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            {error && (
              <p className="flex items-center gap-2 rounded-md bg-error-container/50 px-3 py-2 text-label-md text-on-error-container">
                <Icon name="error" className="text-[18px]" />
                {error}
              </p>
            )}

            <div className="mt-1 flex justify-end gap-3">
              <Button
                type="button"
                variant="ghost"
                className="rounded-md px-5 py-2.5"
                onClick={onClose}
              >
                Cancelar
              </Button>
              <Button
                type="submit"
                variant="primary"
                className="rounded-md px-6 py-2.5"
                disabled={submitting}
              >
                {submitting
                  ? 'Guardando…'
                  : mode === 'create'
                    ? 'Crear cliente'
                    : 'Guardar cambios'}
              </Button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}
