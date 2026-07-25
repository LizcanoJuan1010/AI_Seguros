/**
 * Catálogo de funciones de la plataforma que se muestran en el inicio.
 *
 * Cada card con `prompt` navega a `/asistente?q=<prompt>`: el chat auto-envía
 * la pregunta exacta y la IA ejecuta la herramienta en vivo (demo real, no
 * mockup). Las cards con `to` abren una experiencia completa de la app.
 */
export type FeatureCategory =
  | 'comprar'
  | 'pagos'
  | 'siniestros'
  | 'negocio'
  | 'experiencias'

export type FeatureCard = {
  id: string
  icon: string
  title: string
  desc: string
  category: FeatureCategory
  /** Pregunta exacta que se auto-envía al chat del asistente. */
  prompt?: string
  /** Ruta de la experiencia (cards sin prompt). */
  to?: string
  /** Funciones que responden con datos de negocio (rol gerente). */
  managerMode?: boolean
  /** Card hero: ocupa dos columnas en el bento. */
  featured?: boolean
}

export const FEATURE_CATEGORIES: {
  id: FeatureCategory | 'todos'
  label: string
  icon: string
}[] = [
  { id: 'todos', label: 'Todas', icon: 'apps' },
  { id: 'comprar', label: 'Cotiza y asegúrate', icon: 'verified_user' },
  { id: 'pagos', label: 'Pagos y pólizas', icon: 'credit_card' },
  { id: 'siniestros', label: 'Siniestros', icon: 'car_crash' },
  { id: 'negocio', label: 'Para tu negocio', icon: 'monitoring' },
  { id: 'experiencias', label: 'Experiencias', icon: 'play_circle' },
]

export const featureCards: FeatureCard[] = [
  // ── Cotiza y asegúrate ────────────────────────────────────────────────
  {
    id: 'cotizar',
    icon: 'request_quote',
    title: 'Cotización al instante',
    desc: 'Hasta 3 opciones reales con prima en pesos y dólares, coberturas y aseguradoras de verdad. Sin formularios eternos.',
    category: 'comprar',
    prompt: 'Cotízame un seguro de vida, tengo 29 años',
    featured: true,
  },
  {
    id: 'catalogo',
    icon: 'travel_explore',
    title: 'Catálogo LATAM',
    desc: 'Explora productos por país y tipo entre más de 1.300 aseguradoras reales de la región.',
    category: 'comprar',
    prompt: '¿Qué seguros de auto tienen disponibles en Colombia?',
  },
  {
    id: 'pdf',
    icon: 'picture_as_pdf',
    title: 'Cotización en PDF',
    desc: 'La IA genera un documento formal de tu cotización, listo para descargar o compartir.',
    category: 'comprar',
    prompt: 'Cotízame un seguro de viaje y envíame la cotización en PDF',
  },
  {
    id: 'perfil',
    icon: 'psychology',
    title: 'Recomendación por perfil',
    desc: 'Hiperperfilado con IA: etapa de vida, riesgo y capacidad de pago para recomendarte lo que sí necesitas.',
    category: 'comprar',
    prompt: '¿Qué seguro me recomiendas? Tengo 35 años, dos hijos y trabajo independiente',
  },
  {
    id: 'compra',
    icon: 'workspace_premium',
    title: 'Compra 100% autónoma',
    desc: 'De “no sé qué necesito” a póliza emitida en el mismo chat: datos, consentimiento, riesgo y emisión sin humanos.',
    category: 'comprar',
    prompt: 'Quiero comprar ya un seguro de vida, ¿qué necesitas de mí?',
  },
  {
    id: 'formulario',
    icon: 'assignment',
    title: 'Formulario inteligente',
    desc: '¿Prefieres llenar todo de una vez? La IA arma el formulario exacto para tu producto.',
    category: 'comprar',
    prompt: 'Prefiero llenar todos mis datos de una vez, dame el formulario',
  },
  {
    id: 'documentos',
    icon: 'document_scanner',
    title: 'Lee tus documentos',
    desc: 'Sube tu cédula, RUT o tarjeta de propiedad y la IA extrae y completa tus datos automáticamente.',
    category: 'comprar',
    prompt: 'Quiero adjuntar mi cédula para que completes mis datos automáticamente',
  },

  // ── Pagos y pólizas ───────────────────────────────────────────────────
  {
    id: 'pago',
    icon: 'credit_card',
    title: 'Link de pago seguro',
    desc: 'Cobro con Polar en COP: tu tarjeta nunca pasa por el chat y la póliza se emite al confirmarse el pago.',
    category: 'pagos',
    prompt: 'Quiero pagar mi póliza con tarjeta, genérame el link de pago',
  },
  {
    id: 'verificar-pago',
    icon: 'price_check',
    title: 'Verificación de pago',
    desc: 'La IA consulta el estado real de tu transacción y solo emite cuando está aprobada.',
    category: 'pagos',
    prompt: 'Ya pagué, ¿me confirmas si el pago quedó aprobado?',
  },
  {
    id: 'aclaraciones',
    icon: 'currency_exchange',
    title: 'Reembolsos y aclaraciones',
    desc: 'Cobros dobles, disputas o derecho de retracto: la IA gestiona la aclaración por ti.',
    category: 'pagos',
    prompt: 'Necesito un reembolso: me cobraron doble',
  },
  {
    id: 'renovacion',
    icon: 'autorenew',
    title: 'Renovación proactiva',
    desc: '¿Tu póliza está por vencer? La IA cotiza la renovación antes de que te quedes sin cobertura.',
    category: 'pagos',
    prompt: 'Mi póliza está por vencer, ¿me cotizas la renovación?',
  },
  // ── Siniestros ────────────────────────────────────────────────────────
  {
    id: 'siniestro',
    icon: 'car_crash',
    title: 'Reportar un siniestro',
    desc: 'FNOL conversacional con triage antifraude: reporta el incidente y recibe tu número de reclamo al instante.',
    category: 'siniestros',
    prompt: 'Chocaron mi carro, quiero reportar el siniestro',
  },
  {
    id: 'estado-reclamo',
    icon: 'search_insights',
    title: 'Estado del reclamo',
    desc: 'Consulta en qué va tu reclamo con solo el número CLM, sin llamadas ni filas.',
    category: 'siniestros',
    prompt: '¿Cómo va mi reclamo? Tengo el número CLM',
  },
  {
    id: 'docs-siniestro',
    icon: 'checklist',
    title: 'Documentos del reclamo',
    desc: 'La lista exacta de soportes que necesitas según el tipo de siniestro.',
    category: 'siniestros',
    prompt: '¿Qué documentos necesito para el reclamo de mi carro?',
  },

  // ── Para tu negocio ───────────────────────────────────────────────────
  {
    id: 'insights',
    icon: 'query_stats',
    title: 'Insights de ventas',
    desc: 'KPIs, funnel de conversión y ventas por país y producto, respondidos en lenguaje natural.',
    category: 'negocio',
    prompt: '¿Cómo van las ventas este mes? Muéstrame el funnel',
    managerMode: true,
  },
  {
    id: 'leads',
    icon: 'group_search',
    title: 'Leads recientes',
    desc: 'Los últimos leads con sus cotizaciones y primas, priorizados por scoring de intención.',
    category: 'negocio',
    prompt: 'Muéstrame los últimos leads con sus cotizaciones',
    managerMode: true,
  },
  {
    id: 'informes',
    icon: 'forward_to_inbox',
    title: 'Informes por email',
    desc: 'Suscríbete a reportes diarios, semanales o mensuales directamente desde el chat.',
    category: 'negocio',
    prompt: 'Suscríbeme al informe semanal de ventas por correo',
    managerMode: true,
  },
  {
    id: 'whatsapp',
    icon: 'chat',
    title: 'WhatsApp con IA',
    desc: 'La misma asesora vive en WhatsApp: cotiza, emite, envía PDFs y hasta notas de voz.',
    category: 'negocio',
    prompt: '¿Puedo cotizar y comprar mi seguro por WhatsApp?',
  },

  // ── Experiencias completas ────────────────────────────────────────────
  {
    id: 'llamada',
    icon: 'graphic_eq',
    title: 'Llamada con IA en vivo',
    desc: 'Habla con la asesora por voz, estilo Gemini Live: cotización y cierre sin teclado.',
    category: 'experiencias',
    to: '/llamada',
  },
  {
    id: 'gerente',
    icon: 'monitoring',
    title: 'Dashboard gerencial',
    desc: 'KPIs del día, impacto de la IA, alertas, reclamos y ranking de agentes en tiempo real.',
    category: 'experiencias',
    to: '/gerente',
  },
  {
    id: 'clientes',
    icon: 'diversity_3',
    title: 'Cartera de clientes 360',
    desc: 'Expediente completo de cada cliente con scoring HOT/WARM/COLD, riesgo, pólizas y conversación con la IA.',
    category: 'experiencias',
    to: '/gerente?tab=clientes',
  },
  {
    id: 'embed',
    icon: 'code_blocks',
    title: 'Seguro embebido',
    desc: 'Widget para aliados: cualquier e-commerce agrega “protege tu compra” sin login.',
    category: 'experiencias',
    to: '/embed',
  },
]

/** Destino del clic: experiencia directa o chat con la pregunta pre-cargada. */
export function featureHref(card: FeatureCard): string {
  if (card.to) return card.to
  return `/asistente?q=${encodeURIComponent(card.prompt ?? '')}`
}
