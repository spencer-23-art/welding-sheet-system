import api from './client'

export interface TencentConfig {
  app_id: string | null
  open_id: string | null
  has_token: boolean
  book_id: string | null
  poll_enabled: boolean
  poll_interval_minutes: number
}

export async function getTencentConfig(): Promise<TencentConfig> {
  const { data } = await api.get('/tencent/config')
  return data
}

export async function putTencentConfig(payload: {
  app_id?: string
  open_id?: string
  access_token?: string
  book_id?: string
}) {
  const { data } = await api.put('/tencent/config', payload)
  return data
}

export async function syncTencent(payload: {
  book_id: string
  sheet_id?: string
  cell_range?: string
}) {
  const { data } = await api.post('/tencent/sync', payload)
  return data
}

export interface PollStatus {
  enabled: boolean
  interval_minutes: number
  start_hour: number
  end_hour: number
  modify_poll_interval_minutes: number
  full_reconcile_hours: number
  full_reconcile_minutes: number
  book_id: string | null
  has_token: boolean
  webhook_ready: boolean
  today_api_calls: number
  api_call_date: string
  last_run: string | null
  last_error: string | null
  last_result: unknown
  last_full_sync: string | null
  last_modify_scan: string | null
  incremental_cursor: {
    header_row: number | null
    last_data_row: number | null
  } | null
}

export async function getPollStatus(): Promise<PollStatus> {
  const { data } = await api.get('/tencent/poll/status')
  return data
}

export async function setPoll(payload: {
  enabled?: boolean
  interval_minutes?: number
  book_id?: string
}) {
  const { data } = await api.post('/tencent/poll/set', payload)
  return data
}

export async function triggerPoll() {
  const { data } = await api.post('/tencent/poll/trigger')
  return data
}
