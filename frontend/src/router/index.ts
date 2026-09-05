import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import AppLayout from '@/components/layout/AppLayout.vue'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { guest: true },
  },
  {
    path: '/',
    component: AppLayout,
    meta: { requiresAuth: true },
    children: [
      { path: '', redirect: '/dashboard' },
      {
        path: 'dashboard',
        name: 'dashboard',
        component: () => import('@/views/DashboardView.vue'),
      },
      {
        path: 'profile',
        name: 'profile',
        component: () => import('@/views/ProfileView.vue'),
      },
      {
        path: 'messages',
        name: 'messages',
        component: () => import('@/views/MessagesView.vue'),
      },
      {
        path: 'messages/:id',
        name: 'message-detail',
        component: () => import('@/views/MessageDetailView.vue'),
        props: true,
      },
      {
        path: 'strategies',
        name: 'strategies',
        component: () => import('@/views/StrategyListView.vue'),
      },
      {
        path: 'strategies/:id',
        name: 'strategy-detail',
        component: () => import('@/views/StrategyDetailView.vue'),
        props: true,
      },
      {
        path: 'orders',
        name: 'orders',
        component: () => import('@/views/OrdersView.vue'),
      },
      {
        path: 'trades',
        name: 'trades',
        component: () => import('@/views/TradesView.vue'),
      },
      {
        path: 'admin',
        name: 'admin-dashboard',
        component: () => import('@/views/AdminDashboardView.vue'),
        meta: { requiresAdmin: true },
      },
      {
        path: 'settings',
        name: 'settings',
        component: () => import('@/views/SettingsView.vue'),
        meta: { requiresAdmin: true },
      },
      {
        path: 'agent',
        name: 'agent',
        component: () => import('@/views/AgentView.vue'),
      },
      {
        path: 'agent/cron',
        name: 'agent-cron',
        component: () => import('@/views/AgentView.vue'),
      },
      {
        path: 'agent/:sessionId',
        name: 'agent-session',
        component: () => import('@/views/AgentView.vue'),
      },
      {
        path: 'monitors',
        name: 'monitors',
        component: () => import('@/views/MonitorView.vue'),
      },
      {
        path: 'knowledge',
        name: 'knowledge-graph',
        component: () => import('@/views/KnowledgeGraphView.vue'),
      },
      {
        path: 'knowledge/search',
        name: 'knowledge-search',
        component: () => import('@/views/KnowledgeSearchView.vue'),
      },
      {
        path: 'knowledge/experience',
        name: 'knowledge-experience',
        component: () => import('@/views/ExperienceView.vue'),
      },
      {
        path: 'analysis/equity',
        name: 'analysis-equity',
        component: () => import('@/views/analysis/EquityView.vue'),
      },
      {
        path: 'analysis/risk',
        name: 'analysis-risk',
        component: () => import('@/views/analysis/RiskView.vue'),
      },
      {
        path: 'analysis/compare',
        name: 'analysis-compare',
        component: () => import('@/views/analysis/CompareView.vue'),
      },
      {
        path: 'analysis/dayt',
        name: 'analysis-dayt',
        component: () => import('@/views/analysis/DayTView.vue'),
      },
      {
        path: 'analysis/settlement',
        name: 'analysis-settlement',
        component: () => import('@/views/analysis/SettlementView.vue'),
      },
      {
        path: 'analysis/statistics',
        name: 'analysis-statistics',
        component: () => import('@/views/analysis/StatisticsView.vue'),
      },
      {
        path: 'analysis/positions',
        name: 'analysis-positions',
        component: () => import('@/views/analysis/PositionsView.vue'),
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 路由守卫
router.beforeEach(async (to, from) => {
  const authStore = useAuthStore()

  // 等待启动启动时 token 验证完成，避免路由放行后才发现 token 过期
  await authStore.waitReady()

  console.log('[Router] beforeEach: from=%s → to=%s, name=%s',
    from.fullPath, to.fullPath, to.name)

  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    console.warn('[Router] 🔴 需要认证但未登录，拦截 → login (from %s)', to.fullPath)
    return { name: 'login', query: { next: to.fullPath } }
  }
  if (to.meta.guest && authStore.isAuthenticated) {
    console.log('[Router] 已登录，guest 页面 → dashboard')
    return { name: 'dashboard' }
  }
  if (to.meta.requiresAdmin && !authStore.isAdmin) {
    console.warn('[Router] 🔴 需要管理员权限，拦截 → dashboard')
    return { name: 'dashboard' }
  }
})

router.onError((error) => {
  console.error('[Router] ❌ 导航错误:', error.message, error)
})

export default router
