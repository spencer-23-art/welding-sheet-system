<template>
  <div>
    <el-card>
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px">
        <h2 style="margin: 0">用户管理</h2>
        <el-button v-if="auth.hasPerm('user:create')" type="primary" @click="openCreate">
          <el-icon><Plus /></el-icon> 新建用户
        </el-button>
      </div>

      <el-table :data="users" border v-loading="loading" style="width: 100%">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="username" label="用户名" />
        <el-table-column prop="email" label="邮箱" />
        <el-table-column prop="phone" label="手机号" />
        <el-table-column label="角色">
          <template #default="{ row }">
            <el-tag v-for="r in row.roles" :key="r.id" size="small" style="margin-right: 4px">
              {{ r.name }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="数据范围" width="200">
          <template #default="{ row }">
            <span v-if="!row.assigned_projects && !row.assigned_zones" style="color: #999">全部</span>
            <template v-else>
              <el-tag v-for="p in (row.assigned_projects || [])" :key="'p'+p" size="small" type="warning" style="margin-right: 4px">
                项目{{ p }}
              </el-tag>
              <el-tag v-for="z in (row.assigned_zones || [])" :key="'z'+z" size="small" type="success" style="margin-right: 4px">
                区{{ z }}
              </el-tag>
            </template>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'danger'" size="small">
              {{ row.is_active ? '正常' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220" v-if="auth.hasPerm('user:update') || auth.hasPerm('user:delete')">
          <template #default="{ row }">
            <el-button
              v-if="auth.hasPerm('user:update')"
              size="small"
              @click="toggleActive(row)"
            >
              {{ row.is_active ? '禁用' : '启用' }}
            </el-button>
            <el-button
              v-if="auth.hasPerm('user:update')"
              size="small"
              @click="openEdit(row)"
            >
              编辑
            </el-button>
            <el-button
              v-if="auth.hasPerm('user:delete')"
              size="small"
              type="danger"
              @click="remove(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialog" :title="editing ? '编辑用户' : '新建用户'" width="460px">
      <el-form :model="form" label-width="90px">
        <el-form-item label="用户名">
          <el-input v-model="form.username" :disabled="editing" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" show-password placeholder="留空则不修改" :disabled="!editing && false" />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="form.email" />
        </el-form-item>
        <el-form-item label="手机号">
          <el-input v-model="form.phone" />
        </el-form-item>
        <el-form-item label="部门ID">
          <el-input v-model.number="form.department_id" />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="form.role_names" multiple placeholder="选择角色" style="width: 100%">
            <el-option v-for="r in roleOptions" :key="r.id" :label="r.name" :value="r.name" />
          </el-select>
        </el-form-item>
        <el-form-item label="可访问项目">
          <el-select v-model="form.assigned_projects" multiple filterable placeholder="不选择=不限制项目" style="width: 100%">
            <el-option v-for="p in projectOptions" :key="p" :label="p" :value="p" />
          </el-select>
        </el-form-item>
        <el-form-item label="可访问装置区">
          <el-select v-model="form.assigned_zones" multiple filterable placeholder="不选择=不限制装置区" style="width: 100%">
            <el-option v-for="z in zoneOptions" :key="z" :label="z" :value="z" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/api/client'
import { useAuthStore } from '@/store/auth'

const auth = useAuthStore()
const users = ref<any[]>([])
const roleOptions = ref<any[]>([])
const projectOptions = ref<string[]>([])
const zoneOptions = ref<string[]>([])
const loading = ref(false)
const dialog = ref(false)
const editing = ref(false)
const saving = ref(false)

const emptyForm = {
  id: 0,
  username: '',
  password: '',
  email: '',
  phone: '',
  department_id: null as number | null,
  role_names: [] as string[],
  assigned_projects: [] as string[],
  assigned_zones: [] as string[],
}
const form = reactive({ ...emptyForm })

async function load() {
  loading.value = true
  try {
    const [u, r, p, z] = await Promise.all([
      api.get('/users'),
      api.get('/roles'),
      api.get('/meta/projects'),
      api.get('/meta/zones'),
    ])
    users.value = u.data
    roleOptions.value = r.data
    projectOptions.value = p.data
    zoneOptions.value = z.data
  } finally {
    loading.value = false
  }
}

function openCreate() {
  Object.assign(form, emptyForm)
  editing.value = false
  dialog.value = true
}

function openEdit(row: any) {
  Object.assign(form, {
    id: row.id,
    username: row.username,
    password: '',
    email: row.email || '',
    phone: row.phone || '',
    department_id: row.department_id,
    role_names: row.roles.map((r: any) => r.name),
    assigned_projects: row.assigned_projects ? [...row.assigned_projects] : [],
    assigned_zones: row.assigned_zones ? [...row.assigned_zones] : [],
  })
  editing.value = true
  dialog.value = true
}

async function save() {
  saving.value = true
  try {
    if (editing.value) {
      const { password, email, phone, department_id, role_names, assigned_projects, assigned_zones } = form
      await api.patch(`/users/${form.id}`, {
        email,
        phone,
        department_id,
        role_names,
        assigned_projects,
        assigned_zones,
        ...(password ? { password } : {}),
      })
      ElMessage.success('已保存')
    } else {
      await api.post('/users', { ...form })
      ElMessage.success('用户已创建')
    }
    dialog.value = false
    await load()
  } finally {
    saving.value = false
  }
}

async function toggleActive(row: any) {
  await api.patch(`/users/${row.id}`, { is_active: !row.is_active })
  ElMessage.success('已更新状态')
  await load()
}

async function remove(row: any) {
  await ElMessageBox.confirm(`确认删除用户 ${row.username}？`, '提示', { type: 'warning' })
  await api.delete(`/users/${row.id}`)
  ElMessage.success('已删除')
  await load()
}

onMounted(load)
</script>
