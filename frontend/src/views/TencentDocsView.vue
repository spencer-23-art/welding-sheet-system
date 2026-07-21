<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getSheetMeta, syncSheet } from '@/api/documents'

const route = useRoute()
const router = useRouter()
const docId = Number(route.params.id)
const sheetName = ref('')
const docType = ref('')
const tencentUrl = ref(localStorage.getItem(`tdoc_url_${docId}`) || '')
const rowsText = ref('')
const loading = ref(true)
const syncing = ref(false)
const lastResult = ref<Record<string, any> | null>(null)
const lastSyncAt = ref('')

onMounted(async () => {
  try {
    const data = await getSheetMeta(docId)
    sheetName.value = data.name
    docType.value = data.doc_type
  } catch {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
})

function saveUrl() {
  localStorage.setItem(`tdoc_url_${docId}`, tencentUrl.value)
  ElMessage.success('链接已保存（本机缓存）')
}

async function onSync() {
  syncing.value = true
  try {
    let rows: any = null
    if (rowsText.value.trim()) {
      try {
        rows = JSON.parse(rowsText.value)
      } catch {
        ElMessage.error('粘贴的数据不是合法 JSON（应为二维数组）')
        return
      }
    }
    const res = await syncSheet(docId, {
      tencent_url: tencentUrl.value || undefined,
      rows,
    })
    lastResult.value = res
    lastSyncAt.value = new Date().toLocaleString()
    ElMessage.success(`同步完成：解析 ${res.parsed_rows} 行，更新 ${res.updated} 行`)
  } catch (e: any) {
    ElMessage.error('同步失败：' + (e?.response?.data?.detail || e?.message || '未知错误'))
  } finally {
    syncing.value = false
  }
}

function onBack() {
  router.push('/sheets')
}
</script>

<template>
  <div class="tdoc-page">
    <div class="bar">
      <el-button @click="onBack">← 返回</el-button>
      <span class="title">{{ sheetName || '表格' }}</span>
      <el-tag v-if="docType === 'welding_db'" size="small" type="info">腾讯文档同步</el-tag>
      <span class="sync-at" v-if="lastSyncAt">上次同步：{{ lastSyncAt }}</span>
    </div>

    <el-alert
      type="info"
      :closable="false"
      title="编辑在腾讯文档中进行"
      description="本页把腾讯文档表格同步到本地缓存，供大屏读取。可直接在下方嵌入的腾讯文档里编辑，或粘贴二维数据手动同步。"
      style="margin: 12px 16px"
    />

    <div class="body">
      <div class="left">
        <el-form label-width="92px" class="url-form">
          <el-form-item label="腾讯文档链接">
            <el-input
              v-model="tencentUrl"
              placeholder="粘贴腾讯文档分享/编辑链接，如 https://docs.qq.com/sheet/XXXX"
              @keyup.enter="saveUrl"
            />
          </el-form-item>
          <el-form-item>
            <el-button @click="saveUrl">保存链接</el-button>
          </el-form-item>
        </el-form>

        <el-divider>手动同步（粘贴二维数据）</el-divider>
        <el-input
          v-model="rowsText"
          type="textarea"
          :rows="8"
          placeholder='可选：粘贴从腾讯文档复制的二维数组 JSON，例如 [["管线号","焊口号",...],["P1","J1",...]]'
        />
        <div style="margin-top: 10px">
          <el-button type="primary" :loading="syncing" @click="onSync">同步到本地缓存</el-button>
        </div>

        <el-result
          v-if="lastResult"
          icon="success"
          :title="`已解析 ${lastResult.parsed_rows} 行，更新 ${lastResult.updated} 行`"
          sub-title="大屏将在数秒内刷新"
          style="padding: 12px 0"
        />
      </div>

      <div class="right">
        <iframe
          v-if="tencentUrl"
          :src="tencentUrl"
          class="tdoc-frame"
          frameborder="0"
          allow="clipboard-read; clipboard-write"
        />
        <el-empty v-else description="填写腾讯文档链接后可在此直接编辑" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.tdoc-page { display: flex; flex-direction: column; height: calc(100vh - 110px); }
.bar { display: flex; align-items: center; gap: 12px; padding: 10px 16px; border-bottom: 1px solid #eee; flex-wrap: wrap; }
.bar .title { font-weight: 600; }
.sync-at { margin-left: auto; color: #888; font-size: 12px; }
.body { flex: 1; min-height: 0; display: flex; gap: 16px; padding: 12px 16px; }
.left { width: 420px; max-width: 46%; overflow: auto; }
.right { flex: 1; min-width: 0; }
.tdoc-frame { width: 100%; height: 100%; border: 1px solid #eee; border-radius: 8px; }
</style>
