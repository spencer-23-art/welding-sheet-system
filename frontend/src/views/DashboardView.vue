<template>
  <div>
    <el-card>
      <h2 style="margin-top: 0">工作台</h2>
      <p style="color: #64748b">
        当前阶段：用户系统与 RBAC 权限已完成。腾讯文档接入与数据同步已上线，编辑在腾讯文档内进行。
      </p>
      <el-descriptions border :column="2" v-if="auth.user">
        <el-descriptions-item label="用户名">{{ auth.user.username }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="auth.user.is_active ? 'success' : 'danger'">
            {{ auth.user.is_active ? '正常' : '已禁用' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="角色">
          <el-tag v-for="r in auth.user.roles" :key="r.id" style="margin-right: 6px">
            {{ r.name }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="权限数">{{ auth.user.permissions.length }}</el-descriptions-item>
      </el-descriptions>

      <el-alert
        v-if="auth.hasPerm('page:admin')"
        style="margin-top: 16px"
        type="success"
        :closable="false"
        title="您拥有管理权限"
        description="可在左侧「用户管理」中查看 / 创建 / 禁用 / 删除用户，并分配角色。"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { useAuthStore } from '@/store/auth'
const auth = useAuthStore()
</script>
