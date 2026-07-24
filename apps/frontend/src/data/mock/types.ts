export type LeadStatus = 'todos' | 'seguimiento' | 'cerrados'
export type IntentTone = 'hot' | 'warm' | 'cold'

export type Lead = {
  id: string
  /** Id del Customer en el backend; los leads mock (demo) no lo tienen. */
  customerId?: string
  name: string
  initials: string
  when: string
  type: string
  typeIcon: string
  summary: string
  intent: IntentTone
  intentLabel: string
  premium: string
  phone: string
  email: string
  location: string
  status: Exclude<LeadStatus, 'todos'>
  insight: string
  checks: string[]
  transcript: { speaker: string; time: string; text: string; side: 'bot' | 'client' }[]
}

export type TranscriptLine = {
  id: string
  role: 'ai' | 'user'
  text: string
}

export type Quote = {
  vehicle: string
  coverages: string[]
  monthly: string
  savingsLabel: string
}

export type Kpi = {
  id: string
  label: string
  value: string
  delta: string
  deltaUp: boolean
  hint: string
  icon: string
}

export type AgentRow = {
  id: string
  name: string
  role: string
  avatar: string
  leads: number
  calls: number
  closes: number
  conversion: string
  conversionTone: 'good' | 'warn'
  spark: string
  sparkTone: 'up' | 'down'
}

export type Alert = {
  id: string
  title: string
  body: string
  tone: 'amber' | 'error'
  cta?: string
}

export type LeaderEntry = {
  id: string
  rank: string
  name: string
  amount: string
  width: string
  tone: 'gold' | 'silver' | 'bronze'
}
