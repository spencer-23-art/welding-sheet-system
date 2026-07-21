import axios, { type AxiosInstance } from 'axios'
import { ElMessage } from 'element-plus'

const api: AxiosInstance = axios.create({
  baseURL: '/api',
  timeout: 15000,
})

function getToken(): string | null {
  return localStorage.getItem('access_token')
}
function getRefresh(): string | null {
  return localStorage.getItem('refresh_token')
}
function setTokens(access: string, refresh: string) {
  localStorage.setItem('access_token', access)
  localStorage.setItem('refresh_token', refresh)
}
function clearTokens() {
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
  localStorage.removeItem('user')
}

api.interceptors.request.use((config) => {
  const t = getToken()
  if (t) config.headers.Authorization = `Bearer ${t}`
  return config
})

// 刷新锁，避免并发 401 同时刷新
let refreshPromise: Promise<string> | null = null

function refreshAccessToken(refreshToken: string): Promise<string> {
  if (!refreshPromise) {
    refreshPromise = axios
      .post('/api/refresh', { refresh_token: refreshToken })
      .then((response) => {
        const { access_token: access, refresh_token: refresh } = response.data
        setTokens(access, refresh)
        return access
      })
      .finally(() => {
        refreshPromise = null
      })
  }
  return refreshPromise
}

api.interceptors.response.use(
  (resp) => resp,
  async (error) => {
    const original: any = error.config
    if (error.response?.status === 401 && original && !original._retry) {
      const refresh = getRefresh()
      if (!refresh) {
        clearTokens()
        window.location.href = '/login'
        return Promise.reject(error)
      }
      original._retry = true
      try {
        const token = await refreshAccessToken(refresh)
        original.headers = original.headers || {}
        original.headers.Authorization = `Bearer ${token}`
        return api(original)
      } catch {
        clearTokens()
        window.location.href = '/login'
        return Promise.reject(error)
      }
    }
    const msg = error.response?.data?.detail || error.message || '请求失败'
    ElMessage.error(typeof msg === 'string' ? msg : JSON.stringify(msg))
    return Promise.reject(error)
  }
)

export { api, setTokens, clearTokens, getToken }
export default api
