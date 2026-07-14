<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import UniverEditor from '@/components/UniverEditor.vue'
import { loadSheet } from '@/api/documents'
import { getToken } from '@/api/client'
import { useAuthStore } from '@/store/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const docId = Number(route.params.id)
const sheetName = ref('')
const docType = ref('')
const initialData = ref<Record<string, any> | null>(null)
const rowVersions = ref<Record<string, number>>({})
const loading = ref(true)
const saving = ref(false)
const editorRef = ref<any>(null)

// —— 在线协作（presence）——
interface RemoteUser {
  id: number
  name: string
  color: string
  cursor: { row: number; col: number } | null
}
const remoteUsers = ref<RemoteUser[]>([])
let ws: WebSocket | null = null
let wsRetry: number | undefined

function wsUrl(): string {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const token = getToken() || ''
  return `${proto}://${location.host}/ws/presence?doc_id=${docId}&token=${encodeURIComponent(token)}`
}

function connectPresence() {
  try {
    ws = new WebSocket(wsUrl())
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data)
        if (msg.type === 'presence' && Array.isArray(msg.users)) {
          const selfId = auth.user?.id
          remoteUsers.value = msg.users
            .filter((u: any) => u.id !== selfId)
            .map((u: any) => ({
              id: u.id,
              name: u.name,
              color: u.color,
              cursor: u.cursor || null,
            }))
        }
      } catch {
        /* ignore */
      }
    }
    ws.onclose = () => {
      ws = null
      // 5s 后重连
      wsRetry = window.setTimeout(connectPresence, 5000)
    }
    ws.onerror = () => {
      ws?.close()
    }
  } catch {
    wsRetry = window.setTimeout(connectPresence, 5000)
  }
}

function sendCursor(payload: { row: number; col: number } | null) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'cursor', cursor: payload }))
  }
}

onMounted(async () => {
  try {
    const data = await loadSheet(docId)
    sheetName.value = data.name
    docType.value = data.doc_type
    initialData.value = data.workbook_data
    rowVersions.value = data.row_versions || {}
  } catch {
    ElMessage.error('加载表格失败')
  } finally {
    loading.value = false
  }
  connectPresence()
})

onBeforeUnmount(() => {
  if (wsRetry) window.clearTimeout(wsRetry)
  if (ws) {
    try {
      ws.close()
    } catch {
      /* ignore */
    }
    ws = null
  }
})

async function onManualSave() {
  saving.value = true
  const ok = await editorRef.value?.save()
  saving.value = false
  if (ok) ElMessage.success('已保存')
  else ElMessage.error('保存失败（可能存在冲突，见提示）')
}

function onBack() {
  router.push('/sheets')
}
</script>

<template>
  <div class="editor-page">
    <div class="editor-bar">
      <el-button @click="onBack">← 返回</el-button>
      <span class="title">{{ sheetName || '表格' }}</span>
      <el-tag v-if="docType === 'welding_db'" size="small" type="info">协同编辑</el-tag>

      <!-- 在线协作面板 -->
      <div class="presence">
        <span class="presence-label">在线：</span>
        <span
          v-for="u in remoteUsers"
          :key="u.id"
          class="presence-chip"
          :style="{ backgroundColor: u.color }"
          :title="u.cursor ? `${u.name} · 第 ${u.cursor.row} 行 / 第 ${u.cursor.col} 列` : u.name"
        >
          {{ u.name }}<template v-if="u.cursor"> · {{ u.cursor.row }}行</template>
        </span>
        <span v-if="remoteUsers.length === 0" class="presence-empty">仅你一人</span>
      </div>

      <el-button type="primary" :loading="saving" @click="onManualSave">保存</el-button>
    </div>
    <div class="editor-body" v-loading="loading">
      <UniverEditor
        v-if="!loading"
        ref="editorRef"
        :doc-id="docId"
        :initial-data="initialData"
        :doc-type="docType"
        :row-versions="rowVersions"
        @cursor="sendCursor"
      />
    </div>
  </div>
</template>

<style scoped>
.editor-page {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 110px);
}
.editor-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  border-bottom: 1px solid #eee;
  flex-wrap: wrap;
}
.editor-bar .title {
  font-weight: 600;
}
.presence {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
  flex-wrap: wrap;
}
.presence-label {
  color: #888;
  font-size: 13px;
}
.presence-chip {
  color: #fff;
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 10px;
  white-space: nowrap;
}
.presence-empty {
  color: #aaa;
  font-size: 12px;
}
.editor-body {
  flex: 1;
  min-height: 0;
  position: relative;
}
</style>
