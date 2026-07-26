/**
 * Pestaña "Agente IA" del gerente: administrar lo que el agente sabe.
 *
 * 1) Catálogo y precios: edita la tabla `products` del cotizador del servicio
 *    IA (PATCH /api/products/:id). El nuevo precio rige de inmediato en las
 *    cotizaciones del agente y sobrevive reinicios (editado_manual).
 * 2) Conocimiento del negocio: notas (promos, políticas, aclaraciones) que se
 *    inyectan al prompt del agente en TODAS las conversaciones del equipo
 *    (CRUD /api/knowledge). Activar/desactivar tiene efecto inmediato.
 *
 * Ambas requieren sesión de gerente (JWT del login).
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { Button } from '../../components/ui/Button'
import { Card } from '../../components/ui/Card'
import { Chip } from '../../components/ui/Chip'
import { Icon } from '../../components/ui/Icon'
import { authHeaders } from '../../lib/authFetch'
import { useTenant } from '../../tenant/TenantContext'

type CatalogProduct = {
  id: string
  tipo: string
  nombre: string
  aseguradora: string
  suma_base_usd: number
  prima_base_usd: number
  coberturas: string[]
}

type KnowledgeEntry = {
  id: number
  title: string
  content: string
  active: boolean
  updated_at: string
}

const jsonHeaders = () => ({
  'Content-Type': 'application/json',
  ...authHeaders(),
})

/* ---------------- Catálogo y precios ---------------- */

type ProductEditorProps = {
  product: CatalogProduct
  onSaved: (p: CatalogProduct) => void
  onDelete: (p: CatalogProduct) => void
}

/** Estado editable compartido por la fila (desktop) y la tarjeta (móvil). */
function useProductEditor(
  product: CatalogProduct,
  onSaved: (p: CatalogProduct) => void,
) {
  const [prima, setPrima] = useState(String(product.prima_base_usd))
  const [suma, setSuma] = useState(String(product.suma_base_usd))
  const [state, setState] = useState<'idle' | 'saving' | 'ok' | 'error'>('idle')

  const dirty =
    Number(prima) !== product.prima_base_usd ||
    Number(suma) !== product.suma_base_usd

  const save = async () => {
    setState('saving')
    try {
      const res = await fetch(`/api/products/${product.id}`, {
        method: 'PATCH',
        headers: jsonHeaders(),
        body: JSON.stringify({
          prima_base_usd: Number(prima),
          suma_base_usd: Number(suma),
        }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const updated = (await res.json()) as CatalogProduct
      onSaved({ ...product, ...updated })
      setState('ok')
      setTimeout(() => setState('idle'), 2000)
    } catch {
      setState('error')
    }
  }

  return { prima, setPrima, suma, setSuma, state, dirty, save }
}

const rowInputClass =
  'w-24 rounded-lg border border-outline-variant bg-white px-2 py-1.5 text-right text-sm outline-none focus:border-primary'

/** Tarjeta apilada (móvil) para editar un producto del catálogo. */
function ProductCard({ product, onSaved, onDelete }: ProductEditorProps) {
  const { prima, setPrima, suma, setSuma, state, dirty, save } =
    useProductEditor(product, onSaved)
  const cardInput =
    'w-full rounded-lg border border-outline-variant bg-white px-3 py-2 text-right text-sm outline-none focus:border-primary'
  return (
    <div className="rounded-xl border border-outline-variant bg-surface-container-lowest p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-bold text-on-surface">{product.nombre}</p>
          <p className="text-[11px] text-outline">{product.aseguradora}</p>
        </div>
        <Chip tone="neutral" className="shrink-0">
          {product.tipo}
        </Chip>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-3">
        <label className="flex flex-col gap-1">
          <span className="text-[10px] font-semibold tracking-wide text-on-surface-variant uppercase">
            Prima (USD/mes)
          </span>
          <input
            type="number"
            min={0}
            step="0.5"
            value={prima}
            onChange={(e) => setPrima(e.target.value)}
            className={cardInput}
            aria-label={`Prima mensual USD de ${product.nombre}`}
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[10px] font-semibold tracking-wide text-on-surface-variant uppercase">
            Suma asegurada (USD)
          </span>
          <input
            type="number"
            min={0}
            step="1000"
            value={suma}
            onChange={(e) => setSuma(e.target.value)}
            className={cardInput}
            aria-label={`Suma asegurada USD de ${product.nombre}`}
          />
        </label>
      </div>
      <div className="mt-3 flex items-center justify-end gap-2">
        {state === 'error' && (
          <span className="text-[10px] font-bold text-error">
            No se pudo guardar
          </span>
        )}
        <button
          type="button"
          onClick={() => onDelete(product)}
          title="Eliminar producto"
          aria-label={`Eliminar ${product.nombre}`}
          className="flex size-9 items-center justify-center rounded-lg text-on-surface-variant hover:bg-error-container/60 hover:text-error"
        >
          <Icon name="delete" className="text-[18px]" />
        </button>
        {state === 'ok' ? (
          <span className="inline-flex items-center gap-1 text-xs font-bold text-primary">
            <Icon name="check_circle" className="text-[16px]" />
            Guardado
          </span>
        ) : (
          <Button
            className="rounded-lg px-4 py-2 text-xs"
            disabled={!dirty || state === 'saving'}
            onClick={save}
          >
            {state === 'saving' ? 'Guardando…' : 'Guardar'}
          </Button>
        )}
      </div>
    </div>
  )
}

function ProductRow({ product, onSaved, onDelete }: ProductEditorProps) {
  const { prima, setPrima, suma, setSuma, state, dirty, save } =
    useProductEditor(product, onSaved)

  return (
    <tr className="align-middle transition-colors hover:bg-mist-white">
      <td className="px-4 py-3">
        <p className="text-sm font-bold text-on-surface">{product.nombre}</p>
        <p className="text-[11px] text-outline">{product.aseguradora}</p>
      </td>
      <td className="px-4 py-3">
        <Chip tone="neutral">{product.tipo}</Chip>
      </td>
      <td className="px-4 py-3 text-right">
        <input
          type="number"
          min={0}
          step="0.5"
          value={prima}
          onChange={(e) => setPrima(e.target.value)}
          className={rowInputClass}
          aria-label={`Prima mensual USD de ${product.nombre}`}
        />
      </td>
      <td className="px-4 py-3 text-right">
        <input
          type="number"
          min={0}
          step="1000"
          value={suma}
          onChange={(e) => setSuma(e.target.value)}
          className={rowInputClass}
          aria-label={`Suma asegurada USD de ${product.nombre}`}
        />
      </td>
      <td className="px-4 py-3 text-right">
        <div className="flex items-center justify-end gap-1">
          {state === 'ok' ? (
            <span className="inline-flex items-center gap-1 text-xs font-bold text-primary">
              <Icon name="check_circle" className="text-[16px]" />
              Guardado
            </span>
          ) : (
            <Button
              className="rounded-lg px-3 py-1.5 text-xs"
              disabled={!dirty || state === 'saving'}
              onClick={save}
            >
              {state === 'saving' ? 'Guardando…' : 'Guardar'}
            </Button>
          )}
          <button
            type="button"
            onClick={() => onDelete(product)}
            title="Eliminar producto"
            aria-label={`Eliminar ${product.nombre}`}
            className="flex size-8 items-center justify-center rounded-full text-on-surface-variant hover:bg-error-container/60 hover:text-error"
          >
            <Icon name="delete" className="text-[18px]" />
          </button>
        </div>
        {state === 'error' && (
          <p className="mt-1 text-[10px] font-bold text-error">No se pudo guardar</p>
        )}
      </td>
    </tr>
  )
}

/** Formulario para dar de alta un producto nuevo en el catálogo. */
function NewProductForm({ onCreated }: { onCreated: (p: CatalogProduct) => void }) {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({
    nombre: '',
    tipo: 'vida',
    aseguradora: '',
    prima_base_usd: '',
    suma_base_usd: '',
    coberturas: '',
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async () => {
    if (!form.nombre.trim() || !form.aseguradora.trim() || busy) return
    setBusy(true)
    setError(null)
    try {
      const res = await fetch('/api/products', {
        method: 'POST',
        headers: jsonHeaders(),
        body: JSON.stringify({
          nombre: form.nombre.trim(),
          tipo: form.tipo.trim(),
          aseguradora: form.aseguradora.trim(),
          prima_base_usd: Number(form.prima_base_usd) || 0,
          suma_base_usd: Number(form.suma_base_usd) || 0,
          coberturas: form.coberturas
            .split('\n')
            .map((s) => s.trim())
            .filter(Boolean),
        }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      onCreated((await res.json()) as CatalogProduct)
      setForm({
        nombre: '',
        tipo: 'vida',
        aseguradora: '',
        prima_base_usd: '',
        suma_base_usd: '',
        coberturas: '',
      })
      setOpen(false)
    } catch {
      setError('No se pudo crear el producto (¿sesión de gerente activa?).')
    } finally {
      setBusy(false)
    }
  }

  const field =
    'w-full rounded-lg border border-outline-variant bg-white px-3 py-2 text-sm outline-none focus:border-primary'

  if (!open) {
    return (
      <div className="border-t border-outline-variant p-4">
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="flex items-center gap-2 rounded-lg border border-dashed border-primary/40 px-4 py-2.5 text-sm font-bold text-primary hover:bg-primary/5"
        >
          <Icon name="add_circle" className="text-[18px]" />
          Agregar producto nuevo
        </button>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3 border-t border-outline-variant bg-surface-container-low/40 p-4">
      <p className="text-sm font-bold text-on-surface">Nuevo producto</p>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <input
          className={field}
          placeholder="Nombre del producto"
          value={form.nombre}
          onChange={(e) => setForm({ ...form, nombre: e.target.value })}
        />
        <input
          className={field}
          placeholder="Aseguradora"
          value={form.aseguradora}
          onChange={(e) => setForm({ ...form, aseguradora: e.target.value })}
        />
        <select
          className={field}
          value={form.tipo}
          onChange={(e) => setForm({ ...form, tipo: e.target.value })}
        >
          {['vida', 'salud', 'auto', 'hogar', 'mascotas', 'movilidad', 'accidentes', 'viaje', 'pyme', 'desempleo', 'dispositivos'].map(
            (t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ),
          )}
        </select>
        <div className="grid grid-cols-2 gap-3">
          <input
            className={field}
            type="number"
            min={0}
            step="0.5"
            placeholder="Prima USD/mes"
            value={form.prima_base_usd}
            onChange={(e) => setForm({ ...form, prima_base_usd: e.target.value })}
          />
          <input
            className={field}
            type="number"
            min={0}
            step="1000"
            placeholder="Suma USD"
            value={form.suma_base_usd}
            onChange={(e) => setForm({ ...form, suma_base_usd: e.target.value })}
          />
        </div>
      </div>
      <textarea
        className={`${field} resize-y`}
        rows={2}
        placeholder="Coberturas (una por línea)"
        value={form.coberturas}
        onChange={(e) => setForm({ ...form, coberturas: e.target.value })}
      />
      {error && <p className="text-xs font-bold text-error">{error}</p>}
      <div className="flex items-center justify-end gap-2">
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="rounded-lg px-4 py-2 text-sm font-semibold text-on-surface-variant hover:bg-surface-variant"
        >
          Cancelar
        </button>
        <Button
          className="rounded-lg px-4 py-2 text-sm"
          onClick={submit}
          disabled={busy || !form.nombre.trim() || !form.aseguradora.trim()}
        >
          {busy ? 'Creando…' : 'Crear producto'}
        </Button>
      </div>
    </div>
  )
}

function CatalogEditor() {
  const [products, setProducts] = useState<CatalogProduct[]>([])
  const [error, setError] = useState(false)
  const [note, setNote] = useState<string | null>(null)

  const remove = async (p: CatalogProduct) => {
    if (!window.confirm(`¿Eliminar "${p.nombre}" del catálogo?`)) return
    setNote(null)
    try {
      const res = await fetch(`/api/products/${p.id}`, {
        method: 'DELETE',
        headers: authHeaders(),
      })
      if (res.status === 409) {
        setNote(
          `No se puede eliminar "${p.nombre}": tiene cotizaciones asociadas.`,
        )
        return
      }
      if (!res.ok && res.status !== 204) throw new Error(`HTTP ${res.status}`)
      setProducts((prev) => prev.filter((x) => x.id !== p.id))
    } catch {
      setNote('No se pudo eliminar el producto.')
    }
  }

  useEffect(() => {
    let alive = true
    fetch('/api/products')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d: CatalogProduct[]) => alive && setProducts(d))
      .catch(() => alive && setError(true))
    return () => {
      alive = false
    }
  }, [])

  return (
    <Card className="rounded-lg border border-outline-variant">
      <div className="border-b border-outline-variant p-5">
        <h2 className="flex items-center gap-2 text-lg font-bold text-on-surface">
          <Icon name="sell" className="text-primary" />
          Catálogo y precios del cotizador
        </h2>
        <p className="text-xs text-on-surface-variant">
          Estos valores alimentan las cotizaciones del agente IA en vivo. Los
          precios son en USD (moneda base del cotizador; la conversión a COP la
          hace la tasa de cambio del día).
        </p>
      </div>
      {error ? (
        <p className="p-6 text-sm text-on-surface-variant">
          No se pudo cargar el catálogo.
        </p>
      ) : (
        <>
          {note && (
            <p className="border-b border-outline-variant bg-error-container/20 px-5 py-2 text-xs font-semibold text-on-error-container">
              {note}
            </p>
          )}
          {/* Móvil (<md): cada producto como tarjeta editable apilada */}
          <div className="flex flex-col gap-3 p-4 md:hidden">
            {products.map((p) => (
              <ProductCard
                key={p.id}
                product={p}
                onSaved={(updated) =>
                  setProducts((prev) =>
                    prev.map((x) => (x.id === updated.id ? updated : x)),
                  )
                }
                onDelete={remove}
              />
            ))}
          </div>

          {/* Desktop (md+): tabla editable */}
          <div className="hidden overflow-x-auto md:block">
            <table className="w-full text-left">
            <thead>
              <tr className="bg-surface-container-low/50">
                {['Producto', 'Tipo', 'Prima base (USD/mes)', 'Suma asegurada (USD)', ''].map(
                  (h) => (
                    <th
                      key={h}
                      className="px-4 py-3 text-xs font-semibold tracking-wider text-on-surface-variant uppercase last:text-right [&:nth-child(3)]:text-right [&:nth-child(4)]:text-right"
                    >
                      {h}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant">
              {products.map((p) => (
                <ProductRow
                  key={p.id}
                  product={p}
                  onSaved={(updated) =>
                    setProducts((prev) =>
                      prev.map((x) => (x.id === updated.id ? updated : x)),
                    )
                  }
                  onDelete={remove}
                />
              ))}
            </tbody>
          </table>
          </div>

          <NewProductForm
            onCreated={(p) => setProducts((prev) => [...prev, p])}
          />
        </>
      )}
    </Card>
  )
}

/* ---------------- Conocimiento del negocio ---------------- */

function KnowledgeEditor() {
  const { teamId } = useTenant()
  const [entries, setEntries] = useState<KnowledgeEntry[]>([])
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [editId, setEditId] = useState<number | null>(null)
  const [editTitle, setEditTitle] = useState('')
  const [editContent, setEditContent] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  const load = useCallback(() => {
    fetch('/api/knowledge', { headers: authHeaders() })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d: KnowledgeEntry[]) => setEntries(d))
      .catch(() => setEntries([]))
  }, [])

  useEffect(load, [load, teamId])

  const uploadDoc = async (file: File) => {
    setUploading(true)
    setNote(null)
    try {
      const body = new FormData()
      body.append('file', file)
      // Sin Content-Type manual: el navegador fija el boundary del multipart.
      const res = await fetch('/api/knowledge/upload', {
        method: 'POST',
        headers: authHeaders(),
        body,
      })
      if (res.status === 422) {
        setNote('No se pudo leer el documento (¿PDF escaneado o vacío?).')
        return
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setNote(`Documento "${file.name}" añadido al conocimiento del agente.`)
      load()
    } catch {
      setNote('No se pudo subir el documento.')
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const startEdit = (e: KnowledgeEntry) => {
    setEditId(e.id)
    setEditTitle(e.title)
    setEditContent(e.content)
  }

  const saveEdit = async () => {
    if (editId == null) return
    try {
      const res = await fetch(`/api/knowledge/${editId}`, {
        method: 'PATCH',
        headers: jsonHeaders(),
        body: JSON.stringify({ title: editTitle.trim(), content: editContent.trim() }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setEditId(null)
      load()
    } catch {
      setNote('No se pudo guardar la edición.')
    }
  }

  const create = async () => {
    if (!title.trim() || !content.trim() || busy) return
    setBusy(true)
    setNote(null)
    try {
      const res = await fetch('/api/knowledge', {
        method: 'POST',
        headers: jsonHeaders(),
        body: JSON.stringify({ title: title.trim(), content: content.trim() }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setTitle('')
      setContent('')
      setNote('Guardado: el agente ya lo usa en sus conversaciones.')
      load()
    } catch {
      setNote('No se pudo guardar (¿sesión de gerente activa?).')
    } finally {
      setBusy(false)
    }
  }

  const toggle = async (entry: KnowledgeEntry) => {
    await fetch(`/api/knowledge/${entry.id}`, {
      method: 'PATCH',
      headers: jsonHeaders(),
      body: JSON.stringify({ active: !entry.active }),
    }).catch(() => undefined)
    load()
  }

  const remove = async (id: number) => {
    await fetch(`/api/knowledge/${id}`, {
      method: 'DELETE',
      headers: authHeaders(),
    }).catch(() => undefined)
    load()
  }

  return (
    <Card className="rounded-lg border border-outline-variant">
      <div className="border-b border-outline-variant p-5">
        <h2 className="flex items-center gap-2 text-lg font-bold text-on-surface">
          <Icon name="psychology" className="text-primary" />
          Conocimiento del negocio
        </h2>
        <p className="text-xs text-on-surface-variant">
          Promociones, políticas y aclaraciones que el agente IA usará de
          inmediato en <span className="font-bold">todas</span> las
          conversaciones del equipo (chat web y WhatsApp).
        </p>
      </div>
      <div className="flex flex-col gap-3 p-5">
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Título (ej: Promo julio seguro de vida)"
          maxLength={120}
          className="w-full rounded-lg border border-outline-variant bg-white px-3 py-2 text-sm outline-none focus:border-primary"
        />
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="Contenido que el agente debe saber y usar (ej: 'Durante julio, Vida Esencial tiene 20% de descuento el primer año para afiliados Colsubsidio…')"
          rows={3}
          maxLength={4000}
          className="w-full resize-y rounded-lg border border-outline-variant bg-white px-3 py-2 text-sm outline-none focus:border-primary"
        />
        <div className="flex flex-wrap items-center justify-between gap-2">
          {note ? (
            <p className="text-label-sm text-on-surface-variant">{note}</p>
          ) : (
            <span />
          )}
          <div className="flex items-center gap-2">
            <input
              ref={fileRef}
              type="file"
              accept=".pdf,.docx,.doc,.txt"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) void uploadDoc(f)
              }}
            />
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              disabled={uploading}
              className="flex items-center gap-1.5 rounded-lg border border-outline-variant px-4 py-2 text-sm font-semibold text-on-surface hover:bg-surface-variant disabled:opacity-50"
            >
              <Icon name="upload_file" className="text-[16px]" />
              {uploading ? 'Subiendo…' : 'Subir documento'}
            </button>
            <Button
              className="rounded-lg px-4 py-2 text-sm"
              onClick={create}
              disabled={busy || !title.trim() || !content.trim()}
            >
              <Icon name="add" className="text-[16px]" />
              Enseñar al agente
            </Button>
          </div>
        </div>

        {entries.length > 0 && (
          <ul className="flex flex-col gap-2 border-t border-outline-variant/50 pt-3">
            {entries.map((e) => (
              <li
                key={e.id}
                className={`rounded-lg border p-3 ${
                  e.active
                    ? 'border-primary/30 bg-primary-fixed/10'
                    : 'border-outline-variant bg-surface-container-low opacity-70'
                }`}
              >
                {editId === e.id ? (
                  <div className="flex flex-col gap-2">
                    <input
                      value={editTitle}
                      onChange={(ev) => setEditTitle(ev.target.value)}
                      maxLength={120}
                      className="w-full rounded-lg border border-outline-variant bg-white px-3 py-2 text-sm outline-none focus:border-primary"
                    />
                    <textarea
                      value={editContent}
                      onChange={(ev) => setEditContent(ev.target.value)}
                      rows={4}
                      className="w-full resize-y rounded-lg border border-outline-variant bg-white px-3 py-2 text-sm outline-none focus:border-primary"
                    />
                    <div className="flex items-center justify-end gap-2">
                      <button
                        type="button"
                        onClick={() => setEditId(null)}
                        className="rounded-lg px-3 py-1.5 text-xs font-semibold text-on-surface-variant hover:bg-surface-variant"
                      >
                        Cancelar
                      </button>
                      <Button
                        className="rounded-lg px-3 py-1.5 text-xs"
                        onClick={saveEdit}
                        disabled={!editTitle.trim() || !editContent.trim()}
                      >
                        Guardar
                      </Button>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="text-sm font-bold text-on-surface">
                        {e.title}
                        {!e.active && (
                          <span className="ml-2 text-[10px] font-bold text-outline uppercase">
                            pausado
                          </span>
                        )}
                      </p>
                      <p className="mt-0.5 line-clamp-4 text-xs whitespace-pre-wrap text-on-surface-variant">
                        {e.content}
                      </p>
                    </div>
                    <span className="flex shrink-0 items-center gap-1">
                      <button
                        type="button"
                        onClick={() => startEdit(e)}
                        title="Editar"
                        aria-label={`Editar "${e.title}"`}
                        className="flex size-8 items-center justify-center rounded-full text-on-surface-variant hover:bg-surface-variant hover:text-primary"
                      >
                        <Icon name="edit" className="text-[18px]" />
                      </button>
                      <button
                        type="button"
                        onClick={() => toggle(e)}
                        title={e.active ? 'Pausar' : 'Activar'}
                        aria-label={`${e.active ? 'Pausar' : 'Activar'} "${e.title}"`}
                        className="flex size-8 items-center justify-center rounded-full text-on-surface-variant hover:bg-surface-variant hover:text-primary"
                      >
                        <Icon
                          name={e.active ? 'pause_circle' : 'play_circle'}
                          className="text-[18px]"
                        />
                      </button>
                      <button
                        type="button"
                        onClick={() => remove(e.id)}
                        title="Eliminar"
                        aria-label={`Eliminar "${e.title}"`}
                        className="flex size-8 items-center justify-center rounded-full text-on-surface-variant hover:bg-error-container/60 hover:text-error"
                      >
                        <Icon name="delete" className="text-[18px]" />
                      </button>
                    </span>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  )
}

export function AgentKnowledgePanel() {
  return (
    <div className="flex flex-col gap-6">
      <CatalogEditor />
      <KnowledgeEditor />
    </div>
  )
}
