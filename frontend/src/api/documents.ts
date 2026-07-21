import api from './client'

export interface DocumentItem {
  id: number
  name: string
  is_folder: boolean
  owner_id: number
  parent_id: number | null
  department_id: number | null
  project_id: string | null
  is_deleted: boolean
  created_at: string
  updated_at: string
  has_data: boolean
}

export async function listDocuments(params: {
  parent_id?: number | null
  include_deleted?: boolean
  q?: string
}): Promise<DocumentItem[]> {
  const { data } = await api.get<DocumentItem[]>('/documents', { params })
  return data
}

export async function createDocument(payload: {
  name: string
  is_folder?: boolean
  parent_id?: number | null
  department_id?: number
  project_id?: string
}): Promise<DocumentItem> {
  const { data } = await api.post<DocumentItem>('/documents', payload)
  return data
}

export async function renameDocument(id: number, name: string): Promise<DocumentItem> {
  const { data } = await api.patch<DocumentItem>(`/documents/${id}`, { name })
  return data
}

export async function deleteDocument(id: number): Promise<void> {
  await api.delete(`/documents/${id}`)
}

export async function restoreDocument(id: number): Promise<DocumentItem> {
  const { data } = await api.post<DocumentItem>(`/documents/${id}/restore`)
  return data
}

export async function getSheetMeta(id: number): Promise<{
  id: number
  name: string
  doc_type: string
  record_count: number
  updated_at: string | null
}> {
  const { data } = await api.get(`/sheets/${id}`)
  return data
}

export async function syncSheet(
  id: number,
  payload: { tencent_url?: string; rows?: any[][] },
): Promise<{ parsed_rows: number; updated: number; updated_at: string }> {
  const { data } = await api.post(`/sheets/${id}/sync`, payload)
  return data
}
