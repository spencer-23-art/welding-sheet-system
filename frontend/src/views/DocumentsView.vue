<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listDocuments,
  createDocument,
  renameDocument,
  deleteDocument,
  restoreDocument,
  type DocumentItem,
} from '@/api/documents'

const router = useRouter()
const docs = ref<DocumentItem[]>([])
const loading = ref(false)
const keyword = ref('')
const showTrash = ref(false)

// 面包屑栈：记录进入的文件夹层级
const crumbs = ref<{ id: number; name: string }[]>([])
const currentParent = ref<number | null>(null)

async function load() {
  loading.value = true
  try {
    if (keyword.value.trim()) {
      docs.value = await listDocuments({ q: keyword.value.trim() })
    } else {
      docs.value = await listDocuments({
        parent_id: currentParent.value,
        include_deleted: showTrash.value,
      })
    }
  } finally {
    loading.value = false
  }
}

function openFolder(d: DocumentItem) {
  currentParent.value = d.id
  crumbs.value.push({ id: d.id, name: d.name })
  keyword.value = ''
  load()
}

function goCrumb(index: number) {
  if (index < 0) {
    currentParent.value = null
    crumbs.value = []
  } else {
    currentParent.value = crumbs.value[index].id
    crumbs.value = crumbs.value.slice(0, index + 1)
  }
  keyword.value = ''
  load()
}

function openSheet(d: DocumentItem) {
  router.push(`/sheets/${d.id}/edit`)
}

async function newFolder() {
  const { value } = await ElMessageBox.prompt('请输入文件夹名称', '新建文件夹', {
    inputValidator: (v) => !!v.trim() || '名称不能为空',
  })
  await createDocument({ name: value.trim(), is_folder: true, parent_id: currentParent.value })
  ElMessage.success('已创建文件夹')
  load()
}

async function newSheet() {
  const { value } = await ElMessageBox.prompt('请输入表格名称', '新建表格', {
    inputValidator: (v) => !!v.trim() || '名称不能为空',
  })
  await createDocument({ name: value.trim(), is_folder: false, parent_id: currentParent.value })
  ElMessage.success('已创建表格')
  load()
}

async function onRename(d: DocumentItem) {
  const { value } = await ElMessageBox.prompt('重命名', '重命名', {
    inputValue: d.name,
    inputValidator: (v) => !!v.trim() || '名称不能为空',
  })
  await renameDocument(d.id, value.trim())
  ElMessage.success('已重命名')
  load()
}

async function onDelete(d: DocumentItem) {
  await ElMessageBox.confirm(`确定将「${d.name}」移入回收站？`, '删除', { type: 'warning' })
  await deleteDocument(d.id)
  ElMessage.success('已移入回收站')
  load()
}

async function onRestore(d: DocumentItem) {
  await restoreDocument(d.id)
  ElMessage.success('已恢复')
  load()
}

onMounted(load)
</script>

<template>
  <div class="doc-page">
    <div class="doc-toolbar">
      <div class="crumbs">
        <span class="crumb" @click="goCrumb(-1)">根目录</span>
        <template v-for="(c, i) in crumbs" :key="c.id">
          <span class="sep">/</span>
          <span class="crumb" @click="goCrumb(i)">{{ c.name }}</span>
        </template>
      </div>
      <div class="doc-actions">
        <el-input
          v-model="keyword"
          placeholder="搜索文档"
          clearable
          style="width: 200px"
          @keyup.enter="load"
          @clear="load"
        />
        <el-button @click="load">搜索</el-button>
        <el-switch v-model="showTrash" @change="load" active-text="回收站" />
        <el-button type="primary" @click="newFolder">新建文件夹</el-button>
        <el-button type="primary" @click="newSheet">新建表格</el-button>
      </div>
    </div>

    <el-table :data="docs" v-loading="loading" stripe empty-text="暂无文档">
      <el-table-column label="名称" min-width="240">
        <template #default="{ row }">
          <span
            class="name-cell"
            @click="row.is_folder ? openFolder(row) : openSheet(row)"
          >
            {{ row.is_folder ? '📁' : '📊' }} {{ row.name }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="project_id" label="项目" width="100" />
      <el-table-column prop="updated_at" label="更新时间" width="200" />
      <el-table-column label="操作" width="260" fixed="right">
        <template #default="{ row }">
          <template v-if="!row.is_deleted">
            <el-button v-if="!row.is_folder" link type="primary" @click="openSheet(row)">
              打开
            </el-button>
            <el-button link @click="onRename(row)">重命名</el-button>
            <el-button link type="danger" @click="onDelete(row)">删除</el-button>
          </template>
          <template v-else>
            <el-button link type="success" @click="onRestore(row)">恢复</el-button>
          </template>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.doc-page {
  padding: 16px;
}
.doc-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 12px;
}
.doc-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}
.crumbs {
  display: flex;
  align-items: center;
  font-size: 14px;
}
.crumb {
  cursor: pointer;
  color: #409eff;
}
.crumb:hover {
  text-decoration: underline;
}
.sep {
  margin: 0 6px;
  color: #999;
}
.name-cell {
  cursor: pointer;
}
.name-cell:hover {
  color: #409eff;
}
</style>
