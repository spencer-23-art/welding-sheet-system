<template>
  <div class="settings">
    <h2>腾讯文档接入设置</h2>
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="数据链路：腾讯文档 → 后端同步 → 本地缓存 → 数据大屏"
      description="分享链接中的 D… ID 会由后端自动转换为 API 所需的 file ID；大屏只读取本地缓存。"
    />

    <el-card class="block">
      <template #header>① 开发者凭证</template>
      <el-form label-width="132px">
        <el-form-item label="Client ID">
          <el-input v-model="form.app_id" placeholder="腾讯文档开放生态中的 client_id" />
        </el-form-item>
        <el-form-item label="Open ID">
          <el-input v-model="form.open_id" placeholder="腾讯文档开放生态中的 open_id" />
        </el-form-item>
        <el-form-item label="Access Token">
          <el-input
            v-model="form.access_token"
            type="password"
            show-password
            placeholder="仅写入后端；已保存时可留空以保持不变"
          />
        </el-form-item>
        <el-form-item label="默认表格链接">
          <el-input v-model="form.book_id" placeholder="https://docs.qq.com/sheet/D..." />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="saving" @click="saveConfig">保存配置</el-button>
          <el-tag v-if="cfg" :type="cfg.has_token ? 'success' : 'warning'" class="status-tag">
            {{ cfg.has_token ? '令牌已配置' : '尚未配置令牌' }}
          </el-tag>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card class="block">
      <template #header>② 立即同步</template>
      <el-form label-width="132px">
        <el-form-item label="文档链接/ID">
          <el-input v-model="sync.book_id" placeholder="腾讯文档在线表格分享链接或 file ID" />
        </el-form-item>
        <el-form-item label="工作表 ID">
          <el-input v-model="sync.sheet_id" placeholder="可选；留空自动读取第一个工作表" />
        </el-form-item>
        <el-form-item>
          <el-button type="success" :loading="syncing" @click="doSync">同步到大屏缓存</el-button>
        </el-form-item>
      </el-form>
      <el-alert
        v-if="lastResult"
        type="success"
        :closable="false"
        :title="`同步完成：解析 ${lastResult.result?.parsed_rows ?? 0} 行，写入 ${lastResult.result?.updated ?? 0} 行`"
      />
    </el-card>

    <el-card class="block">
      <template #header>③ 定时同步</template>
      <el-form label-width="132px">
        <el-form-item label="轮询开关">
          <el-switch v-model="poll.enabled" @change="savePoll" />
          <span class="hint">{{ poll.enabled ? '已开启' : '已关闭' }}</span>
        </el-form-item>
        <el-form-item label="间隔（分钟）">
          <el-input-number v-model="poll.interval_minutes" :min="1" :max="120" @change="savePoll" />
          <span class="hint">建议 1–5 分钟</span>
        </el-form-item>
        <el-form-item label="轮询文档">
          <el-input v-model="poll.book_id" placeholder="留空时使用默认表格链接" @change="savePoll" />
        </el-form-item>
      </el-form>
      <div class="poll-actions">
        <el-button type="warning" :loading="polling" @click="triggerPoll">立即执行一次</el-button>
        <span class="hint">上次运行：{{ pollStatus?.last_run || '尚未运行' }}</span>
        <el-tag v-if="pollStatus?.last_error" type="danger" size="small">{{ pollStatus.last_error }}</el-tag>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getPollStatus,
  getTencentConfig,
  putTencentConfig,
  setPoll,
  syncTencent,
  triggerPoll as triggerPollRequest,
  type PollStatus,
  type TencentConfig,
} from '@/api/tencent'

const cfg = ref<TencentConfig | null>(null)
const form = ref({ app_id: '', open_id: '', access_token: '', book_id: '' })
const sync = ref({ book_id: '', sheet_id: '' })
const poll = ref({ enabled: false, interval_minutes: 5, book_id: '' })
const pollStatus = ref<PollStatus | null>(null)
const lastResult = ref<any>(null)
const saving = ref(false)
const syncing = ref(false)
const polling = ref(false)

async function loadPollStatus() {
  pollStatus.value = await getPollStatus()
}

async function load() {
  try {
    const current = await getTencentConfig()
    cfg.value = current
    form.value.app_id = current.app_id || ''
    form.value.open_id = current.open_id || ''
    form.value.book_id = current.book_id || ''
    sync.value.book_id = current.book_id || ''
    poll.value = {
      enabled: current.poll_enabled,
      interval_minutes: current.poll_interval_minutes,
      book_id: current.book_id || '',
    }
    await loadPollStatus()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '加载腾讯文档配置失败')
  }
}

async function saveConfig() {
  saving.value = true
  try {
    await putTencentConfig({
      app_id: form.value.app_id || undefined,
      open_id: form.value.open_id || undefined,
      access_token: form.value.access_token || undefined,
      book_id: form.value.book_id || undefined,
    })
    form.value.access_token = ''
    ElMessage.success('腾讯文档配置已保存')
    await load()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '保存配置失败')
  } finally {
    saving.value = false
  }
}

async function doSync() {
  if (!sync.value.book_id) {
    ElMessage.warning('请填写腾讯文档表格链接')
    return
  }
  syncing.value = true
  lastResult.value = null
  try {
    lastResult.value = await syncTencent({
      book_id: sync.value.book_id,
      sheet_id: sync.value.sheet_id || undefined,
    })
    ElMessage.success('同步成功，数据大屏将自动刷新')
    await loadPollStatus()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '同步失败')
  } finally {
    syncing.value = false
  }
}

async function savePoll() {
  try {
    await setPoll({
      enabled: poll.value.enabled,
      interval_minutes: poll.value.interval_minutes,
      book_id: poll.value.book_id || undefined,
    })
    ElMessage.success('轮询配置已保存')
    await loadPollStatus()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '轮询配置保存失败')
  }
}

async function triggerPoll() {
  polling.value = true
  try {
    lastResult.value = await triggerPollRequest()
    ElMessage.success('轮询同步完成')
    await loadPollStatus()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '轮询同步失败')
  } finally {
    polling.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.settings { max-width: 880px; margin: 0 auto; padding: 16px; }
.block { margin-top: 16px; }
.status-tag, .hint { margin-left: 12px; }
.hint { color: #888; font-size: 13px; }
.poll-actions { display: flex; align-items: center; gap: 12px; }
</style>
