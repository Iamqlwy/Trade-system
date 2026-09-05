<template>
  <el-header class="app-header">
    <div class="header-left">
      <el-icon class="mobile-menu-btn" :size="20" @click="toggleSidebar">
        <Operation />
      </el-icon>
      <el-breadcrumb separator="/">
        <el-breadcrumb-item :to="{ path: '/dashboard' }">首页</el-breadcrumb-item>
        <el-breadcrumb-item v-if="currentTitle">{{ currentTitle }}</el-breadcrumb-item>
      </el-breadcrumb>
    </div>

    <div class="header-right">
      <!-- Theme Toggle -->
      <div class="theme-toggle" @click="themeStore.toggle()" :title="themeStore.mode === 'dark' ? '切换白天模式' : '切换黑夜模式'">
        <transition name="theme-icon" mode="out-in">
          <svg v-if="themeStore.mode === 'dark'" key="moon" class="theme-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
          </svg>
          <svg v-else key="sun" class="theme-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="5" />
            <line x1="12" y1="1" x2="12" y2="3" />
            <line x1="12" y1="21" x2="12" y2="23" />
            <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
            <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
            <line x1="1" y1="12" x2="3" y2="12" />
            <line x1="21" y1="12" x2="23" y2="12" />
            <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
            <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
          </svg>
        </transition>
      </div>

      <!-- Message Bell -->
      <MessageBell />

      <!-- Market Status -->
      <div class="market-status" :class="{ connected: marketStore.connected }">
        <span class="status-dot" />
        <span class="status-text">{{ marketStore.connected ? '行情已连接' : '行情断开' }}</span>
      </div>

      <!-- User Menu -->
      <el-dropdown trigger="click" @command="handleCommand">
        <div class="user-menu">
          <div class="user-avatar">
            {{ authStore.user?.username?.charAt(0)?.toUpperCase() || '?' }}
          </div>
          <span class="username">{{ authStore.user?.username || '未登录' }}</span>
          <el-icon :size="12" class="chevron"><ArrowDown /></el-icon>
        </div>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="profile">个人中心</el-dropdown-item>
            <el-dropdown-item divided command="logout">退出登录</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </el-header>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useMarketStore } from '@/stores/market'
import { useThemeStore } from '@/stores/theme'
import { ArrowDown, Operation } from '@element-plus/icons-vue'
import MessageBell from '@/components/notification/MessageBell.vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const marketStore = useMarketStore()
const themeStore = useThemeStore()

function toggleSidebar() {
  // Dispatch custom event for sidebar to listen
  window.dispatchEvent(new CustomEvent('toggle-sidebar'))
}

const titleMap: Record<string, string> = {
  dashboard: '仪表盘',
  profile: '个人中心',
  strategies: '策略列表',
  orders: '订单管理',
  trades: '成交记录',
  agent: 'AI 助手',
  settings: '系统设置',
  'analysis-equity': '净值曲线',
  'analysis-risk': '风险评估',
  'analysis-compare': '策略对比',
  'analysis-dayt': '做T分析',
  'analysis-settlement': '清算分析',
  'analysis-statistics': '交易统计',
  'analysis-positions': '持仓监控',
}

const currentTitle = computed(() => {
  const name = route.name as string
  if (name === 'strategy-detail') return '策略详情'
  return titleMap[name] || ''
})

function handleCommand(cmd: string) {
  if (cmd === 'logout') {
    authStore.logout()
    router.push('/login')
  } else if (cmd === 'profile') {
    router.push('/profile')
  }
}
</script>

<style scoped>
.app-header {
  height: 60px;
  background: var(--color-header-bg);
  backdrop-filter: blur(16px) saturate(180%);
  -webkit-backdrop-filter: blur(16px) saturate(180%);
  border-bottom: 1px solid var(--border-subtle);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 28px;
  transition: background var(--duration-normal) var(--ease-out),
    border-color var(--duration-normal) var(--ease-out);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.mobile-menu-btn {
  display: none;
  cursor: pointer;
  color: var(--text-secondary);
  flex-shrink: 0;
}

@media (max-width: 767px) {
  .app-header {
    padding: 0 16px;
  }

  .mobile-menu-btn {
    display: flex;
  }
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-shrink: 0;
}

@media (max-width: 767px) {
  .header-right {
    gap: 10px;
  }

  .status-text {
    display: none;
  }

  .username {
    display: none;
  }

  .chevron {
    display: none;
  }
}

/* ── Market Status ── */
.market-status {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 5px 12px;
  border-radius: 20px;
  background: rgba(220, 38, 38, 0.06);
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  transition: all 0.3s;
}

.market-status.connected {
  background: rgba(22, 163, 74, 0.06);
  color: var(--color-success);
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-danger);
  transition: background 0.3s;
}

.market-status.connected .status-dot {
  background: var(--color-success);
  animation: pulseGlow 2.5s infinite;
  --el-color-primary: var(--color-success);
  box-shadow: 0 0 0 0 rgba(22, 163, 74, 0.3);
}

@keyframes pulseGlow {
  0%, 100% { box-shadow: 0 0 0 0 rgba(22, 163, 74, 0.3); }
  50% { box-shadow: 0 0 0 5px rgba(22, 163, 74, 0); }
}

/* ── User Menu ── */
.user-menu {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  padding: 4px 8px 4px 4px;
  border-radius: var(--radius-sm);
  transition: background 0.15s;
}

.user-menu:hover {
  background: rgba(0, 0, 0, 0.03);
}

:global(html[data-theme="dark"]) .user-menu:hover {
  background: rgba(255, 255, 255, 0.05);
}

.user-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--color-accent), var(--color-accent-light));
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: var(--font-display);
  font-weight: 700;
  font-size: 13px;
  letter-spacing: 0.02em;
}

.username {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
}

.chevron {
  color: var(--text-muted);
}

/* ── Theme Toggle ── */
.theme-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s;
  color: var(--text-secondary);
}

.theme-toggle:hover {
  background: rgba(0, 0, 0, 0.04);
  color: var(--color-accent-light);
}

:global(html[data-theme="dark"]) .theme-toggle:hover {
  background: rgba(255, 255, 255, 0.06);
}

.theme-icon {
  width: 18px;
  height: 18px;
}

.theme-icon-enter-active,
.theme-icon-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.theme-icon-enter-from {
  opacity: 0;
  transform: rotate(-30deg) scale(0.8);
}

.theme-icon-leave-to {
  opacity: 0;
  transform: rotate(30deg) scale(0.8);
}
</style>
