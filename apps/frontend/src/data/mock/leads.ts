import type { Lead } from './types'

export const leads: Lead[] = [
  {
    id: 'carlos',
    name: 'Carlos Ruiz',
    initials: 'CR',
    when: 'Llamada hace 5 min',
    type: 'Vida',
    typeIcon: 'favorite',
    summary:
      'Interesado en cobertura familiar extendida y beneficios de hospitalización.',
    intent: 'hot',
    intentLabel: 'HOT',
    premium: '$1.200.000',
    phone: '+57 310 123 4567',
    email: 'c.ruiz@email.com',
    location: 'Bogotá, Colombia',
    status: 'seguimiento',
    insight:
      'Ofrecer el paquete Premium de Vida con descuento del 10% por pago anual. El cliente mostró preocupación por la educación de sus hijos.',
    checks: [
      'Verificó identidad con éxito',
      'Presupuesto aprobado: $1.5M COP',
    ],
    transcript: [
      {
        speaker: 'Tequendama Bot',
        time: '0:12',
        side: 'bot',
        text: '¡Hola Carlos! Soy el asistente virtual de Tequendama. Vi que estabas buscando información sobre seguros de vida en nuestro portal.',
      },
      {
        speaker: 'Cliente',
        time: '0:25',
        side: 'client',
        text: 'Hola, sí. Estoy buscando algo que cubra a mi familia, especialmente si algo me pasa a mí por el tema de la universidad de los niños.',
      },
      {
        speaker: 'Tequendama Bot',
        time: '0:38',
        side: 'bot',
        text: 'Entiendo perfectamente, Carlos. Tenemos una opción que incluye una renta educativa garantizada. ¿Te gustaría que te cotice esa cobertura ahora mismo?',
      },
    ],
  },
  {
    id: 'elena',
    name: 'Elena Gómez',
    initials: 'EG',
    when: 'Llamada hace 14 min',
    type: 'Auto',
    typeIcon: 'directions_car',
    summary:
      'Solicitó cotización para SUV 2024 con cobertura contra terceros y robo total.',
    intent: 'warm',
    intentLabel: 'WARM',
    premium: '$850.000',
    phone: '+57 320 555 0199',
    email: 'e.gomez@email.com',
    location: 'Medellín, Colombia',
    status: 'seguimiento',
    insight:
      'Priorizar asistencia en vía y cobertura nacional. Cliente compara 2 cotizaciones.',
    checks: ['Identidad verificada', 'Vehículo: SUV 2024'],
    transcript: [
      {
        speaker: 'Tequendama Bot',
        time: '0:08',
        side: 'bot',
        text: 'Hola Elena, puedo ayudarte a cotizar tu SUV con cobertura contra terceros.',
      },
      {
        speaker: 'Cliente',
        time: '0:20',
        side: 'client',
        text: 'Sí, también quiero robo total y asistencia en carretera.',
      },
    ],
  },
  {
    id: 'juan',
    name: 'Juan Pérez',
    initials: 'JP',
    when: 'Llamada hace 2 horas',
    type: 'Hogar',
    typeIcon: 'home',
    summary:
      'Interés bajo. Comparando precios de seguros para apartamento en arriendo.',
    intent: 'cold',
    intentLabel: 'COLD',
    premium: '$450.000',
    phone: '+57 301 444 7788',
    email: 'j.perez@email.com',
    location: 'Cali, Colombia',
    status: 'cerrados',
    insight: 'Seguimiento suave en 48h. No forzar cierre hoy.',
    checks: ['Lead capturado', 'Comparando 3 ofertas'],
    transcript: [
      {
        speaker: 'Tequendama Bot',
        time: '0:05',
        side: 'bot',
        text: 'Hola Juan, ¿buscas cobertura para tu apartamento en arriendo?',
      },
      {
        speaker: 'Cliente',
        time: '0:18',
        side: 'client',
        text: 'Solo estoy comparando precios por ahora.',
      },
    ],
  },
]
