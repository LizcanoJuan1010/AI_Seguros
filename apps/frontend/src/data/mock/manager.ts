import type { AgentRow, Alert, Kpi, LeaderEntry } from './types'

export const kpis: Kpi[] = [
  {
    id: 'calls',
    label: 'Llamadas IA hoy',
    value: '1,284',
    delta: '12%',
    deltaUp: true,
    hint: 'vs. promedio semanal',
    icon: 'smart_toy',
  },
  {
    id: 'conv',
    label: 'Tasa de Conversión',
    value: '18.5%',
    delta: '2%',
    deltaUp: false,
    hint: 'Objetivo: 20%',
    icon: 'conversion_path',
  },
  {
    id: 'rev',
    label: 'Ingresos (COP)',
    value: '$72.4M',
    delta: '5.4%',
    deltaUp: true,
    hint: 'Acumulado mes actual',
    icon: 'payments',
  },
  {
    id: 'aht',
    label: 'Tiempo Prom. (AHT)',
    value: '4:12 min',
    delta: '30s',
    deltaUp: true,
    hint: 'Optimización por IA activa',
    icon: 'timer',
  },
]

export const agents: AgentRow[] = [
  {
    id: 'elena',
    name: 'Elena Gómez',
    role: 'Senior Lead',
    avatar: '/assets/avatars/elena.png',
    leads: 142,
    calls: 120,
    closes: 28,
    conversion: '19.7%',
    conversionTone: 'good',
    spark: '0,35 20,30 40,32 60,15 80,18 100,5',
    sparkTone: 'up',
  },
  {
    id: 'julian',
    name: 'Julián Restrepo',
    role: 'Agente IA Hybrid',
    avatar: '/assets/avatars/julian.png',
    leads: 115,
    calls: 108,
    closes: 21,
    conversion: '18.2%',
    conversionTone: 'good',
    spark: '0,30 20,35 40,25 60,20 80,10 100,5',
    sparkTone: 'up',
  },
  {
    id: 'sofia',
    name: 'Sofía Méndez',
    role: 'Junior Associate',
    avatar: '/assets/avatars/sofia.png',
    leads: 98,
    calls: 95,
    closes: 12,
    conversion: '12.2%',
    conversionTone: 'warn',
    spark: '0,5 20,15 40,10 60,25 80,30 100,35',
    sparkTone: 'down',
  },
]

export const alerts: Alert[] = [
  {
    id: 'hot',
    title: 'Leads Calientes Sin Atender',
    body: 'Hay 3 leads VIP esperando contacto hace >15 min.',
    tone: 'amber',
    cta: 'ASIGNAR AHORA',
  },
  {
    id: 'drop',
    title: 'Caída en Conversión',
    body: 'Campaña "Seguros Vida" bajó un 10% en la última hora.',
    tone: 'error',
  },
]

export const leaders: LeaderEntry[] = [
  {
    id: '1',
    rank: '1º',
    name: 'Elena Gómez',
    amount: '$12.4M',
    width: '85%',
    tone: 'gold',
  },
  {
    id: '2',
    rank: '2º',
    name: 'Julián Restrepo',
    amount: '$9.8M',
    width: '65%',
    tone: 'silver',
  },
  {
    id: '3',
    rank: '3º',
    name: 'Ricardo Silva',
    amount: '$7.2M',
    width: '45%',
    tone: 'bronze',
  },
]
