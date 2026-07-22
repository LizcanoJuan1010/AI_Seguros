/**
 * Contexto multitenant del frontend.
 *
 * Un "tenant" es un equipo (Team del backend NestJS). El equipo seleccionado
 * se persiste en localStorage y scopea todas las vistas de la app: dashboard
 * del gerente, bandeja de leads del vendedor y la sesión del asistente IA.
 * teamId '' significa "Todos los equipos" (sin filtro).
 *
 * Si el backend no responde, `offline` queda en true y las vistas degradan a
 * sus datos demo sin romper la navegación.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import {
  api,
  getStoredTenantId,
  storeTenantId,
  type Team,
  type TeamUser,
} from '../lib/api'

type TenantContextValue = {
  teams: Team[]
  teamId: string
  team: Team | null
  /** Usuarios (agentes/gerentes) del equipo seleccionado; todos si teamId=''. */
  agents: TeamUser[]
  setTeamId: (id: string) => void
  loading: boolean
  offline: boolean
}

const TenantContext = createContext<TenantContextValue>({
  teams: [],
  teamId: '',
  team: null,
  agents: [],
  setTeamId: () => undefined,
  loading: true,
  offline: false,
})

export function TenantProvider({ children }: { children: ReactNode }) {
  const [teams, setTeams] = useState<Team[]>([])
  const [teamId, setTeamIdState] = useState<string>(getStoredTenantId)
  const [agents, setAgents] = useState<TeamUser[]>([])
  const [loading, setLoading] = useState(true)
  const [offline, setOffline] = useState(false)

  useEffect(() => {
    let alive = true
    api
      .teams()
      .then((res) => {
        if (!alive) return
        setTeams(res.data)
        setOffline(false)
        // Un tenant guardado que ya no existe vuelve a "Todos los equipos".
        if (teamId && !res.data.some((t) => t.id === teamId)) {
          setTeamIdState('')
          storeTenantId('')
        }
      })
      .catch(() => alive && setOffline(true))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- solo al montar
  }, [])

  useEffect(() => {
    if (offline) return
    let alive = true
    api
      .users(teamId || undefined)
      .then((res) => alive && setAgents(res.data))
      .catch(() => alive && setAgents([]))
    return () => {
      alive = false
    }
  }, [teamId, offline])

  const setTeamId = useCallback((id: string) => {
    setTeamIdState(id)
    storeTenantId(id)
  }, [])

  const value = useMemo<TenantContextValue>(
    () => ({
      teams,
      teamId,
      team: teams.find((t) => t.id === teamId) ?? null,
      agents,
      setTeamId,
      loading,
      offline,
    }),
    [teams, teamId, agents, setTeamId, loading, offline],
  )

  return <TenantContext.Provider value={value}>{children}</TenantContext.Provider>
}

export function useTenant(): TenantContextValue {
  return useContext(TenantContext)
}
