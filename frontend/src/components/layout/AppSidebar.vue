<template>
  <!-- Mobile overlay -->
  <div
    v-if="isMobile && !isCollapse"
    class="sidebar-overlay"
    @click="isCollapse = true"
  />
  <el-aside :width="sidebarWidth" class="app-sidebar" :class="{ 'mobile-open': isMobile && !isCollapse }">
    <!-- Logo -->
    <div class="logo-area">
      <div class="logo-mark">
        <img src="/favicon.png" alt="WFDL" class="logo-image" />
      </div>
      <transition name="fade-text">
        <div v-show="!isCollapse" class="logo-text-group">
          <span class="logo-text">WFDL</span>
          <span class="logo-sub">AI Quant Trading Engine</span>
        </div>
      </transition>
    </div>

    <!-- Navigation -->
    <el-menu
      :default-active="activeMenu"
      :collapse="isCollapse"
      background-color="transparent"
      text-color="rgba(255,255,255,0.55)"
      active-text-color="#c9a55a"
      class="sidebar-menu"
    >
      <el-menu-item index="/dashboard" @click="navigateTo('/dashboard')">
        <el-icon><Odometer /></el-icon>
        <template #title>仪表盘</template>
      </el-menu-item>

      <el-sub-menu index="strategy-group">
        <template #title>
          <el-icon><Briefcase /></el-icon>
          <span>策略管理</span>
        </template>
        <el-menu-item index="/strategies" @click="navigateTo('/strategies')">策略列表</el-menu-item>
        <el-menu-item index="/orders" @click="navigateTo('/orders')">订单管理</el-menu-item>
        <el-menu-item index="/trades" @click="navigateTo('/trades')">成交记录</el-menu-item>
      </el-sub-menu>

      <el-sub-menu index="analysis-group">
        <template #title>
          <el-icon><TrendCharts /></el-icon>
          <span>数据分析</span>
        </template>
        <el-menu-item index="/analysis/equity" @click="navigateTo('/analysis/equity')">净值曲线</el-menu-item>
        <el-menu-item index="/analysis/risk" @click="navigateTo('/analysis/risk')">风险评估</el-menu-item>
        <el-menu-item index="/analysis/compare" @click="navigateTo('/analysis/compare')">策略对比</el-menu-item>
        <el-menu-item index="/analysis/dayt" @click="navigateTo('/analysis/dayt')">做T分析</el-menu-item>
        <el-menu-item index="/analysis/settlement" @click="navigateTo('/analysis/settlement')">清算分析</el-menu-item>
        <el-menu-item index="/analysis/statistics" @click="navigateTo('/analysis/statistics')">交易统计</el-menu-item>
        <el-menu-item index="/analysis/positions" @click="navigateTo('/analysis/positions')">持仓监控</el-menu-item>
      </el-sub-menu>

      <el-menu-item index="/agent" @click="navigateTo('/agent')">
        <el-icon><ChatDotRound /></el-icon>
        <template #title>AI 助手</template>
      </el-menu-item>

      <el-menu-item index="/monitors" @click="navigateTo('/monitors')">
        <el-icon><Bell /></el-icon>
        <template #title>监控中心</template>
      </el-menu-item>

      <el-sub-menu index="knowledge-group">
        <template #title>
          <el-icon><Reading /></el-icon>
          <span>知识中心</span>
        </template>
        <el-menu-item index="/knowledge" @click="navigateTo('/knowledge')">
          <el-icon><Share /></el-icon>
          <template #title>知识图谱</template>
        </el-menu-item>
        <el-menu-item index="/knowledge/search" @click="navigateTo('/knowledge/search')">
          <el-icon><Files /></el-icon>
          <template #title>知识库搜索</template>
        </el-menu-item>
        <el-menu-item index="/knowledge/experience" @click="navigateTo('/knowledge/experience')">
          <el-icon><Memo /></el-icon>
          <template #title>经验沉淀</template>
        </el-menu-item>
      </el-sub-menu>

      <el-sub-menu v-if="authStore.isAdmin" index="system-group">
        <template #title>
          <el-icon><Setting /></el-icon>
          <span>系统管理</span>
        </template>
        <el-menu-item index="/admin" @click="navigateTo('/admin')">
          <el-icon><DataAnalysis /></el-icon>
          <template #title>管理面板</template>
        </el-menu-item>
        <el-menu-item index="/settings" @click="navigateTo('/settings')">
          <el-icon><Tools /></el-icon>
          <template #title>系统设置</template>
        </el-menu-item>
      </el-sub-menu>
    </el-menu>

    <!-- Collapse Toggle -->
    <div class="collapse-btn" @click="isCollapse = !isCollapse">
      <el-icon :size="16">
        <Fold v-if="!isCollapse" />
        <Expand v-else />
      </el-icon>
      <span v-show="!isCollapse" class="collapse-label">收起菜单</span>
    </div>
  </el-aside>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import {
  Odometer,
  Briefcase,
  TrendCharts,
  ChatDotRound,
  Bell,
  Setting,
  Fold,
  Expand,
  Message,
  DataAnalysis,
  Share,
  Reading,
  Files,
  Tools,
  Memo,
} from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const isCollapse = ref(false)
const windowWidth = ref(typeof window !== 'undefined' ? window.innerWidth : 1280)

/**
 * 使用 Vue Router 进行 SPA 导航，避免整页刷新。
 * 同时处理移动端点击后自动收起侧边栏。
 */
function navigateTo(path: string) {
  if (route.path !== path) {
    router.push(path)
  }
  // 移动端点击菜单项后自动收起侧边栏
  if (isMobile.value) {
    isCollapse.value = true
  }
}

const isMobile = computed(() => windowWidth.value < 768)
const sidebarWidth = computed(() => {
  if (isMobile.value) return '0px'
  return isCollapse.value ? '68px' : '240px'
})

const activeMenu = computed(() => {
  // /agent/:sessionId 也高亮 "AI 助手" 菜单项
  if (route.path.startsWith('/agent')) return '/agent'
  // /messages/:id 也高亮 "消息中心" 菜单项
  if (route.path.startsWith('/messages')) return '/messages'
  return route.path
})

function onResize() {
  windowWidth.value = window.innerWidth
  // Auto-collapse sidebar on mobile, auto-expand on desktop
  if (windowWidth.value < 768) {
    isCollapse.value = true
  }
}

function onToggleSidebar() {
  isCollapse.value = !isCollapse.value
}

onMounted(() => {
  window.addEventListener('resize', onResize)
  window.addEventListener('toggle-sidebar', onToggleSidebar)
  onResize()
})

onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  window.removeEventListener('toggle-sidebar', onToggleSidebar)
})
</script>

<style scoped>
/* Mobile overlay backdrop */
.sidebar-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: 998;
  animation: fadeIn 0.2s ease;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.app-sidebar {
  background: linear-gradient(195deg, #0e1118 0%, #0a0d14 40%, #080b10 100%);
  display: flex;
  flex-direction: column;
  transition: width 0.35s cubic-bezier(0.16, 1, 0.3, 1);
  overflow: hidden;
  position: relative;
  z-index: 999;
}

@media (max-width: 767px) {
  .app-sidebar {
    position: fixed;
    top: 0;
    left: 0;
    bottom: 0;
    width: 260px !important;
    transform: translateX(-100%);
    transition: transform 0.35s cubic-bezier(0.16, 1, 0.3, 1);
  }

  .app-sidebar.mobile-open {
    transform: translateX(0);
  }
}

/* Subtle top-edge gold accent line */
.app-sidebar::before {
  content: '';
  position: absolute;
  top: 0;
  left: 24px;
  right: 24px;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(201, 165, 90, 0.3), transparent);
}

/* ── Logo ── */
.logo-area {
  height: 64px;
  display: flex;
  align-items: center;
  padding: 0 20px;
  gap: 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.logo-mark {
  flex-shrink: 0;
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.logo-image {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}

.logo-text-group {
  display: flex;
  flex-direction: column;
  line-height: 1.1;
}

.logo-text {
  font-family: var(--font-display);
  font-size: 16px;
  font-weight: 700;
  color: #fff;
  letter-spacing: 0.04em;
}

.logo-sub {
  font-family: var(--font-display);
  font-size: 10px;
  font-weight: 500;
  color: var(--color-accent-light);
  letter-spacing: 0.16em;
  text-transform: uppercase;
  margin-top: 1px;
}

/* ── Menu ── */
.sidebar-menu {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 8px 0;
}

.sidebar-menu::-webkit-scrollbar {
  width: 0;
}

.sidebar-menu:not(.el-menu--collapse) {
  width: 240px;
}

/* ── Collapse Button ── */
.collapse-btn {
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  cursor: pointer;
  color: rgba(255, 255, 255, 0.3);
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  transition: all 0.2s;
  font-size: 12px;
}

.collapse-btn:hover {
  color: var(--color-accent-light);
  background: rgba(255, 255, 255, 0.02);
}

.collapse-label {
  font-size: 12px;
  letter-spacing: 0.02em;
}

/* ── Transition ── */
.fade-text-enter-active,
.fade-text-leave-active {
  transition: opacity 0.2s;
}

.fade-text-enter-from,
.fade-text-leave-to {
  opacity: 0;
}
</style>
