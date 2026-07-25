/**
 * Índice de conversaciones del cliente (estilo ChatGPT/Gemini) por dispositivo.
 *
 * El cliente anónimo no tiene cuenta en servidor: la LISTA de sus chats vive en
 * su propio navegador (localStorage), coherente con su identidad de dispositivo
 * (ver lib/clientIdentity.ts). Los MENSAJES sí viven en el servidor, guardados
 * por sesión bajo la clave `<tenant>:<session_id>`; este índice solo recuerda
 * qué sesiones son suyas, su título y cuándo se usaron por última vez.
 *
 * Un chat entra al índice cuando tiene su primer mensaje (título = ese mensaje);
 * una conversación "nueva" aún vacía es solo el `session_id` activo, todavía sin
 * fila en el índice, para no ensuciar la lista con chats en blanco.
 *
 * Todo se particiona por tenant: cambiar de equipo (staff) abre otra lista.
 */

export type ChatMeta = {
  /** session_id crudo (sin el prefijo de tenant). */
  id: string
  /** Título visible; por defecto, el primer mensaje del usuario. */
  title: string
  /** Epoch ms de la última actividad (para ordenar por reciente). */
  updatedAt: number
}

const indexKey = (tenant: string) => `teq_chat_index_${tenant}`
const activeKey = (tenant: string) => `teq_assistant_active_session_${tenant}`
/** Clave del modelo antiguo (una sola sesión por tenant) — se migra al índice. */
const legacyKey = (tenant: string) => `teq_assistant_session_id_${tenant}`

const TITLE_MAX = 60

function readIndex(tenant: string): ChatMeta[] {
  try {
    const raw = window.localStorage.getItem(indexKey(tenant))
    const parsed = raw ? (JSON.parse(raw) as unknown) : []
    if (!Array.isArray(parsed)) return []
    return parsed.filter(
      (c): c is ChatMeta =>
        !!c &&
        typeof (c as ChatMeta).id === 'string' &&
        typeof (c as ChatMeta).title === 'string' &&
        typeof (c as ChatMeta).updatedAt === 'number',
    )
  } catch {
    return []
  }
}

function writeIndex(tenant: string, list: ChatMeta[]): void {
  try {
    window.localStorage.setItem(indexKey(tenant), JSON.stringify(list))
  } catch {
    /* almacenamiento no disponible: la lista degrada a solo-memoria de la vista */
  }
}

function cleanTitle(raw: string | undefined): string {
  const t = (raw ?? '').replace(/\s+/g, ' ').trim()
  if (!t) return ''
  return t.length > TITLE_MAX ? `${t.slice(0, TITLE_MAX - 1)}…` : t
}

/** Genera un id de sesión nuevo (`sess_<uuid>`). */
export function makeSessionId(): string {
  const rnd =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`
  return `sess_${rnd}`
}

/** Conversaciones del dispositivo, de la más reciente a la más antigua. */
export function listChats(tenant: string): ChatMeta[] {
  return readIndex(tenant).sort((a, b) => b.updatedAt - a.updatedAt)
}

/** true si la sesión ya está en el índice (es decir, ya tuvo mensajes). */
export function hasChat(tenant: string, id: string): boolean {
  return readIndex(tenant).some((c) => c.id === id)
}

/**
 * Id de la conversación activa. La crea en la primera visita o migra la sesión
 * única del modelo anterior para no perder esa conversación.
 */
export function getActiveChatId(tenant: string): string {
  try {
    const active = window.localStorage.getItem(activeKey(tenant))
    if (active) return active
    const legacy = window.localStorage.getItem(legacyKey(tenant))
    if (legacy) {
      window.localStorage.setItem(activeKey(tenant), legacy)
      return legacy
    }
    const fresh = makeSessionId()
    window.localStorage.setItem(activeKey(tenant), fresh)
    return fresh
  } catch {
    return makeSessionId()
  }
}

/** Fija la conversación activa (persistente entre recargas). */
export function setActiveChatId(tenant: string, id: string): void {
  try {
    window.localStorage.setItem(activeKey(tenant), id)
  } catch {
    /* ignore */
  }
}

/** Crea una conversación nueva y la deja activa (aún sin fila en el índice). */
export function newChatId(tenant: string): string {
  const id = makeSessionId()
  setActiveChatId(tenant, id)
  return id
}

/**
 * Registra/actualiza una conversación en el índice. La inserta si no existía
 * (con `title` si se da) y siempre refresca `updatedAt`. Un `title` vacío no
 * pisa el existente.
 */
export function touchChat(
  tenant: string,
  id: string,
  patch?: { title?: string },
): void {
  const list = readIndex(tenant)
  const now = Date.now()
  const title = cleanTitle(patch?.title)
  const i = list.findIndex((c) => c.id === id)
  if (i === -1) {
    list.push({ id, title: title || 'Conversación', updatedAt: now })
  } else {
    list[i] = {
      ...list[i],
      updatedAt: now,
      title: title || list[i].title,
    }
  }
  writeIndex(tenant, list)
}

/** Renombra una conversación (título vacío se ignora). */
export function renameChat(tenant: string, id: string, title: string): void {
  const clean = cleanTitle(title)
  if (!clean) return
  const list = readIndex(tenant)
  const i = list.findIndex((c) => c.id === id)
  if (i === -1) return
  list[i] = { ...list[i], title: clean }
  writeIndex(tenant, list)
}

/** Quita una conversación del índice (el servidor conserva los mensajes). */
export function deleteChat(tenant: string, id: string): void {
  writeIndex(
    tenant,
    readIndex(tenant).filter((c) => c.id !== id),
  )
}
