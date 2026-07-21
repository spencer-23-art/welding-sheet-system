<template>
  <div>
    <header class="app-header">
      <div style="font-weight: 600; font-size: 16px">焊接在线表格平台</div>
      <div style="display: flex; align-items: center; gap: 12px">
        <span v-if="auth.user">你好，{{ auth.user.username }}</span>
        <el-button size="small" @click="onLogout">退出</el-button>
      </div>
    </header>
    <div class="app-body">
      <aside class="app-side">
        <el-menu :default-active="active" router>
          <el-menu-item index="/" v-if="auth.hasPerm('page:sheet')">
            <el-icon><Grid /></el-icon><span>工作台</span>
          </el-menu-item>
          <el-menu-item index="/sheets" v-if="auth.hasPerm('page:sheet')">
            <el-icon><Document /></el-icon><span>我的表格</span>
          </el-menu-item>
          <el-menu-item index="/admin/users" v-if="auth.hasPerm('page:admin')">
            <el-icon><User /></el-icon><span>用户管理</span>
          </el-menu-item>
          <el-menu-item index="/tencent-settings" v-if="auth.hasPerm('page:admin')">
            <el-icon><Setting /></el-icon><span>腾讯文档设置</span>
          </el-menu-item>
        </el-menu>
      </aside>
      <main class="app-main">
        <router-view />
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/store/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const active = computed(() => route.path)

function onLogout() {
  auth.logout()
  router.push('/login')
}
</script>
