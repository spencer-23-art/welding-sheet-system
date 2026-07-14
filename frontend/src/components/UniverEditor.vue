<script setup lang="ts">
import { onMounted, onBeforeUnmount, shallowRef } from 'vue'
import { createUniver, defaultTheme, LocaleType, mergeLocales } from '@univerjs/presets'
import { UniverSheetsCorePreset } from '@univerjs/preset-sheets-core'
import UniverPresetSheetsCoreZhCN from '@univerjs/preset-sheets-core/lib/locales/zh-CN'
import { UniverSheetsFilterPreset } from '@univerjs/preset-sheets-filter'
import SheetsFilterZhCN from '@univerjs/preset-sheets-filter/lib/locales/zh-CN'
import { UniverSheetsConditionalFormattingPreset } from '@univerjs/preset-sheets-conditional-formatting'
import SheetsCFZhCN from '@univerjs/preset-sheets-conditional-formatting/lib/locales/zh-CN'
import { UniverSheetsDataValidationPreset } from '@univerjs/preset-sheets-data-validation'
import SheetsDVZhCN from '@univerjs/preset-sheets-data-validation/lib/locales/zh-CN'
import '@univerjs/preset-sheets-core/lib/index.css'
import '@univerjs/preset-sheets-filter/lib/index.css'
import '@univerjs/preset-sheets-conditional-formatting/lib/index.css'
import '@univerjs/preset-sheets-data-validation/lib/index.css'
import api from '@/api/client'
import { saveSheet, saveSheetRows } from '@/api/documents'
import { ElMessage } from 'element-plus'

const props = defineProps<{
  docId: number
  initialData?: Record<string, any> | null
  docType?: string
  rowVersions?: Record<string, number>
}>()

const emit = defineEmits<{
  (e: 'cursor', payload: { row: number; col: number } | null): void
  (e: 'saved'): void
}>()

// 33 列属性顺序（与后端 COLUMN_DEFS 一致），用于把单元格映射回结构化字段
const ROW_ATTRS = [
  'seq', 'zone_code', 'medium', 'pipe_level', 'pipeline_no', 'joint_no', 'joint_remark',
  'pipe_grade', 'ndt_ratio', 'material', 'spec', 'nominal_diameter', 'nominal_thickness',
  'weld_date', 'welder', 'inch_port', 'team', 'entrust_date', 'entrust_no', 'ndt_date',
  'actual_ndt_date', 'ndt_method', 'ndt_result_1', 'ndt_result_2', 'ndt_result_3',
  'film_count_1', 'ng_count', 'film_total', 'test_unit', 'expand1', 'expand2', 'film_status', 'ng_notice',
]

const containerId = `univer-${props.docId}-${Math.random().toString(36).slice(2, 8)}`
const univerRef = shallowRef<any>(null)
const univerAPIRef = shallowRef<any>(null)
let saveTimer: number | undefined
let cursorTimer: number | undefined
let lastCursorSent = 0

// —— 增量保存所需基线 ——
// baseline: 行键 -> 行内容哈希；versionMap: "管线号|焊口号" -> 版本号
let baseline: Record<string, string> = {}
const versionMap: Record<string, number> = { ...(props.rowVersions || {}) }

function normCell(cell: any): string | undefined {
  // 仅比较「值」，且统一成字符串，忽略 Univer 加载后附加的样式(s)/公式(f)/富文本(p)
  // 以及 数字/文本 的形态差异（如 5 与 "5"），避免「非数据变化」被误判为修改导致全表重传。
  if (!cell || typeof cell !== 'object') return undefined
  if (cell.v === undefined || cell.v === null || cell.v === '') return undefined
  return String(cell.v)
}

function rowHash(rowDict: Record<string, any>): string {
  const parts: any[] = []
  for (let c = 0; c < ROW_ATTRS.length; c++) {
    parts.push(normCell(rowDict?.[String(c)]))
  }
  return JSON.stringify(parts)
}

function buildBaseline(data: Record<string, any> | null) {
  baseline = {}
  if (!data || !data.sheets) return
  const sheet = data.sheets[data.sheetOrder[0]]
  const cd = sheet?.cellData || {}
  for (const rk of Object.keys(cd)) {
    if (rk === '0') continue
    baseline[rk] = rowHash(cd[rk])
  }
}

function cellVal(rowDict: Record<string, any> | undefined, col: number): any {
  const cell = rowDict?.[String(col)]
  return cell && typeof cell === 'object' ? cell.v : undefined
}

function getSnapshot(): Record<string, any> | null {
  const u = univerAPIRef.value
  if (!u) return null
  const wb = u.getActiveWorkbook()
  if (!wb) return null
  return wb.save()
}

function isWeldingDb(): boolean {
  return props.docType === 'welding_db'
}

// 计算变更行（与基线 diff），组装成结构化行
function collectChangedRows(snapshot: Record<string, any>): Array<Record<string, any>> {
  const sheet = snapshot.sheets[snapshot.sheetOrder[0]]
  const cd = sheet?.cellData || {}
  const rows: Array<Record<string, any>> = []
  for (const rk of Object.keys(cd)) {
    if (rk === '0') continue
    const rowDict = cd[rk]
    const hash = rowHash(rowDict)
    if (baseline[rk] === hash) continue // 未变化
    const row: Record<string, any> = {}
    for (let c = 0; c < ROW_ATTRS.length; c++) row[ROW_ATTRS[c]] = cellVal(rowDict, c)
    const pno = (row.pipeline_no ?? '').toString().trim()
    const jno = (row.joint_no ?? '').toString().trim()
    if (!pno && !jno) continue // 空行忽略
    row.version = versionMap[`${pno}|${jno}`] ?? 0
    rows.push(row)
  }
  return rows
}

async function save(): Promise<boolean> {
  const snapshot = getSnapshot()
  if (!snapshot) return false
  try {
    if (isWeldingDb()) {
      const rows = collectChangedRows(snapshot)
      if (rows.length === 0) {
        emit('saved')
        return true // 无变更，直接成功
      }
      const res = await saveSheetRows(props.docId, rows)
      // 更新本地基线 + 版本号，避免下次误报冲突
      const sheet = snapshot.sheets[snapshot.sheetOrder[0]]
      const cd = sheet?.cellData || {}
      for (const r of rows) {
        const pno = (r.pipeline_no ?? '').toString().trim()
        const jno = (r.joint_no ?? '').toString().trim()
        const key = `${pno}|${jno}`
        const nv = res.versions?.[key]
        if (nv != null) versionMap[key] = nv
      }
      // 重新计算这些行在快照中的哈希，写入基线
      for (const rk of Object.keys(cd)) {
        if (rk === '0') continue
        const rd = cd[rk]
        const pno = (cellVal(rd, 4) ?? '').toString().trim()
        const jno = (cellVal(rd, 5) ?? '').toString().trim()
        const key = `${pno}|${jno}`
        if (key in versionMap || res.versions?.[key] != null) baseline[rk] = rowHash(rd)
      }
      if (res.conflicts && res.conflicts.length) {
        const sample = res.conflicts.slice(0, 3)
          .map((c: any) => `${c.pipeline_no}/${c.joint_no}(${c.reason === 'zone_denied' ? '无权限' : '他人已改'})`)
          .join('、')
        ElMessage.warning(`有 ${res.conflicts.length} 行未保存：${sample}；请刷新后再编辑冲突行`)
        emit('saved')
        return false
      }
      emit('saved')
      return true
    }
    // 普通表格：全量保存
    await saveSheet(props.docId, snapshot)
    emit('saved')
    return true
  } catch {
    return false
  }
}

// —— 光标广播（实时在线感知）——
function extractCell(cmd: any): { row: number; col: number } | null {
  const p = cmd?.params || {}
  const ranges: any[] = p.ranges || p.selections || (p.range ? [p.range] : [])
  const r = ranges[0]
  if (!r) return null
  const row = r.startRow ?? r.row ?? r.actualRange?.startRow
  const col = r.startColumn ?? r.col ?? r.actualRange?.startColumn
  if (row == null || col == null) return null
  return { row, col }
}

function onCommandExecuted(cmd: any) {
  const cell = extractCell(cmd)
  if (!cell) return
  const now = Date.now()
  if (now - lastCursorSent < 800) return // 节流
  lastCursorSent = now
  emit('cursor', cell)
}

onMounted(() => {
  buildBaseline(props.initialData || null)
  const { univer, univerAPI } = createUniver({
    locale: LocaleType.ZH_CN,
    locales: {
      [LocaleType.ZH_CN]: mergeLocales(
        UniverPresetSheetsCoreZhCN,
        SheetsFilterZhCN,
        SheetsCFZhCN,
        SheetsDVZhCN,
      ),
    },
    theme: defaultTheme,
    presets: [
      UniverSheetsCorePreset({ container: containerId }),
      UniverSheetsFilterPreset(),
      UniverSheetsConditionalFormattingPreset(),
      UniverSheetsDataValidationPreset(),
    ],
  } as any)
  univerRef.value = univer
  univerAPIRef.value = univerAPI

  if (props.initialData && props.initialData.sheets) {
    univerAPI.createWorkbook(props.initialData as any)
  } else {
    univerAPI.createWorkbook({} as any)
  }

  // 监听选择/编辑命令，广播光标
  try {
    if (typeof univerAPI.onCommandExecuted === 'function') {
      univerAPI.onCommandExecuted(onCommandExecuted)
    }
  } catch {
    /* 部分版本无该 API，忽略光标广播 */
  }

  // 每 30s 自动保存
  saveTimer = window.setInterval(() => {
    save()
  }, 30000)

  // 心跳（保持在线状态）
  cursorTimer = window.setInterval(() => {
    emit('cursor', null)
  }, 15000)
})

onBeforeUnmount(() => {
  if (saveTimer) window.clearInterval(saveTimer)
  if (cursorTimer) window.clearInterval(cursorTimer)
  save().catch(() => {})
  univerRef.value?.dispose()
})

defineExpose({ save, getSnapshot })
</script>

<template>
  <div :id="containerId" class="univer-container"></div>
</template>

<style scoped>
.univer-container {
  width: 100%;
  height: 100%;
}
</style>
