import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api, { setTokens, clearTokens } from '@/api/client'

export interface Role {
  id: number
  name: string
  description?: string
}
export interface User {
  id: number
  username: string
  email?: string
  phone?: string
  department_id?: number | null
  is_active: boolean
  roles: Role[]
  permissions: string[]
}

function loadStoredUser(): User | null {
  const stored = localStorage.getItem('user')
  if (!stored) return null
  try {
    return JSON.parse(stored) as User
  } catch {
    localStorage.removeItem('user')
    return null
  }
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('access_token'))
  const user = ref<User | null>(loadStoredUser())

  const isLoggedIn = computed(() => !!token.value)
  const roles = computed(() => user.value?.roles.map((r) => r.name) || [])
  const permissions = computed(() => user.value?.permissions || [])

  function hasPerm(p: string): boolean {
    return permissions.value.includes(p)
  }
  function hasRole(r: string): boolean {
    return roles.value.includes(r)
  }

  async function login(account: string, password: string) {
    const r = await api.post('/login', { account, password })
    setTokens(r.data.access_token, r.data.refresh_token)
    token.value = r.data.access_token
    await fetchMe()
  }

  async function register(payload: Record<string, unknown>) {
    await api.post('/register', payload)
  }

  async function fetchMe() {
    const r = await api.get('/me')
    user.value = r.data
    localStorage.setItem('user', JSON.stringify(r.data))
    return r.data
  }

  function logout() {
    clearTokens()
    token.value = null
    user.value = null
  }

  return {
    token,
    user,
    isLoggedIn,
    roles,
    permissions,
    hasPerm,
    hasRole,
    login,
    register,
    fetchMe,
    logout,
  }
})
