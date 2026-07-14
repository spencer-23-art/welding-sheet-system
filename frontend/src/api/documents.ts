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

export async function loadSheet(id: number): Promise<{
  id: number
  name: string
  doc_type: string
  workbook_data: Record<string, any> | null
  row_versions: Record<string, number>
}> {
  const { data } = await api.get(`/sheets/${id}`)
  return data
}

export async function saveSheet(id: number, workbook_data: Record<string, any>): Promise<void> {
  await api.post(`/sheets/${id}/save`, { workbook_data })
}

export async function saveSheetRows(
  id: number,
  rows: Array<Record<string, any>>,
): Promise<{ ok: boolean; updated: number; conflicts: Array<Record<string, any>>; versions: Record<string, number> }> {
  const { data } = await api.post(`/sheets/${id}/save_rows`, { rows })
  return data
}
