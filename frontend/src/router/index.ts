import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/store/auth'

const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { public: true },
  },
  {
    path: '/register',
    name: 'register',
    component: () => import('@/views/RegisterView.vue'),
    meta: { public: true },
  },
  {
    path: '/',
    component: () => import('@/layout/MainLayout.vue'),
    children: [
      {
        path: '',
        name: 'dashboard',
        component: () => import('@/views/DashboardView.vue'),
        meta: { perm: 'page:sheet' },
      },
      {
        path: 'admin/users',
        name: 'admin-users',
        component: () => import('@/views/AdminUsersView.vue'),
        meta: { perm: 'page:admin' },
      },
      // 第二阶段：Univer 表格文档管理
      {
        path: 'sheets',
        name: 'sheets',
        component: () => import('@/views/DocumentsView.vue'),
        meta: { perm: 'page:sheet' },
      },
      {
        path: 'sheets/:id/edit',
        name: 'sheet-edit',
        component: () => import('@/views/SheetEditorView.vue'),
        meta: { perm: 'page:sheet' },
      },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (to.meta.public) return true

  if (!auth.isLoggedIn) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (!auth.user) {
    try {
      await auth.fetchMe()
    } catch {
      return { name: 'login' }
    }
  }
  if (to.meta.perm && !auth.hasPerm(to.meta.perm as string)) {
    return { name: 'dashboard' }
  }
  return true
})

export default router
