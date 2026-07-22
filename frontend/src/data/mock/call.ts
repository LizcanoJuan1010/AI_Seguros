import type { Quote, TranscriptLine } from './types'

export const callTranscript: TranscriptLine[] = [
  {
    id: '1',
    role: 'ai',
    text: 'Entiendo perfectamente. Basado en que vives en Medellín y usas tu vehículo principalmente para ir al trabajo, he diseñado una cobertura que prioriza asistencia en vía y protección contra terceros.',
  },
  {
    id: '2',
    role: 'user',
    text: 'Me parece bien, pero ¿qué pasa si viajo a la costa en vacaciones?',
  },
  {
    id: '3',
    role: 'ai',
    text: 'Excelente pregunta. La cobertura es nacional. He actualizado la cotización para incluir asistencia 24/7 en cualquier carretera de Colombia sin costo adicional. ¿Te gustaría ver el detalle del ahorro mensual?',
  },
]

export const callQuote: Quote = {
  vehicle: 'Mazda CX-30 (2023)',
  coverages: [
    'Responsabilidad Civil ($2.000M)',
    'Asistencia Premium en vía',
    'Daños totales y parciales',
    'Cobertura Nacional (Viajes)',
  ],
  monthly: '$185.000',
  savingsLabel: 'Ahorro IA 15%',
}
