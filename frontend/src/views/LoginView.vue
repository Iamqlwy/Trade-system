<template>
  <div class="login-page">
    <!-- Left panel: decorative -->
    <div class="login-visual">
      <div class="visual-content">
        <div class="brand-mark">
          <img src="/favicon.png" alt="WFDL" class="brand-logo-image" />
        </div>
        <h1 class="brand-title">WFDL</h1>
        <p class="brand-subtitle">AI Quant Trading Engine</p>
        <div class="brand-features">
          <div class="feature-item">
            <span class="feature-icon">◈</span>
            <span>多策略管理</span>
          </div>
          <div class="feature-item">
            <span class="feature-icon">◈</span>
            <span>实时行情推送</span>
          </div>
          <div class="feature-item">
            <span class="feature-icon">◈</span>
            <span>智能风控分析</span>
          </div>
          <div class="feature-item">
            <span class="feature-icon">◈</span>
            <span>AI 交易助手</span>
          </div>
        </div>
      </div>
      <!-- Decorative grid lines -->
      <div class="grid-overlay" />
    </div>

    <!-- Right panel: form -->
    <div class="login-form-panel">
      <div class="form-container">
        <div class="form-header">
          <h2>欢迎回来</h2>
          <p>请登录您的账户以继续</p>
        </div>

        <el-tabs v-model="activeTab" stretch class="login-tabs">
          <el-tab-pane label="登录" name="login">
            <el-form ref="loginFormRef" :model="loginForm" :rules="loginRules" @submit.prevent="handleLogin">
              <el-form-item prop="username">
                <el-input
                  v-model="loginForm.username"
                  placeholder="用户名"
                  :prefix-icon="User"
                  size="large"
                  maxlength="20"
                />
              </el-form-item>
              <el-form-item prop="password">
                <el-input
                  v-model="loginForm.password"
                  type="password"
                  placeholder="密码"
                  :prefix-icon="Lock"
                  size="large"
                  show-password
                  maxlength="128"
                  @keyup.enter="handleLogin"
                />
              </el-form-item>
              <el-form-item>
                <el-button
                  type="primary"
                  size="large"
                  :loading="loading"
                  class="submit-btn"
                  @click="handleLogin"
                >
                  登 录
                </el-button>
              </el-form-item>
            </el-form>
          </el-tab-pane>

          <el-tab-pane label="注册" name="register">
            <el-form ref="registerFormRef" :model="registerForm" :rules="registerRules" @submit.prevent="handleRegister">
              <el-form-item prop="username">
                <el-input
                  v-model="registerForm.username"
                  placeholder="用户名（字母数字下划线）"
                  :prefix-icon="User"
                  size="large"
                  maxlength="20"
                />
              </el-form-item>
              <el-form-item prop="password">
                <el-input
                  v-model="registerForm.password"
                  type="password"
                  placeholder="至少8位，含字母和数字"
                  :prefix-icon="Lock"
                  size="large"
                  show-password
                  maxlength="128"
                />
              </el-form-item>
              <el-form-item prop="confirmPassword">
                <el-input
                  v-model="registerForm.confirmPassword"
                  type="password"
                  placeholder="确认密码"
                  :prefix-icon="Lock"
                  size="large"
                  show-password
                  maxlength="128"
                  @keyup.enter="handleRegister"
                />
              </el-form-item>
              <el-form-item>
                <el-button
                  type="primary"
                  size="large"
                  :loading="loading"
                  class="submit-btn"
                  @click="handleRegister"
                >
                  注 册
                </el-button>
              </el-form-item>
            </el-form>
          </el-tab-pane>
        </el-tabs>
      </div>

      <!-- Footer -->
      <div class="form-footer">
        <span>© 2026 Precision Capital</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { ElMessage } from 'element-plus'
import { showApiError } from '@/utils/notify'
import { User, Lock } from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const activeTab = ref('login')
const loading = ref(false)
const loginFormRef = ref<FormInstance>()
const registerFormRef = ref<FormInstance>()

const loginForm = reactive({ username: '', password: '' })
const registerForm = reactive({ username: '', password: '', confirmPassword: '' })

const loginRules: FormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { max: 20, message: '用户名最多 20 个字符', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { max: 128, message: '密码最多 128 个字符', trigger: 'blur' },
  ],
}

const registerRules: FormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 20, message: '用户名长度 3-20 个字符', trigger: 'blur' },
    { pattern: /^[a-zA-Z0-9_]+$/, message: '用户名只能包含字母、数字和下划线', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 8, message: '密码至少 8 个字符', trigger: 'blur' },
    {
      validator: (_rule: unknown, value: string, callback: (err?: Error) => void) => {
        if (value && !/[a-zA-Z]/.test(value)) {
          callback(new Error('密码必须包含至少一个字母'))
        } else if (value && !/[0-9]/.test(value)) {
          callback(new Error('密码必须包含至少一个数字'))
        } else {
          callback()
        }
      },
      trigger: 'blur',
    },
  ],
  confirmPassword: [
    { required: true, message: '请确认密码', trigger: 'blur' },
    {
      validator: (_rule, value, callback) => {
        if (value !== registerForm.password) {
          callback(new Error('两次输入的密码不一致'))
        } else {
          callback()
        }
      },
      trigger: 'blur',
    },
  ],
}

async function handleLogin() {
  const valid = await loginFormRef.value?.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  try {
    await authStore.login(loginForm.username, loginForm.password)
    ElMessage.success('登录成功')
    const next = (route.query.next as string) || '/dashboard'
    router.push(next)
  } catch (err: unknown) {
    showApiError(err, '登录失败')
  } finally {
    loading.value = false
  }
}

async function handleRegister() {
  const valid = await registerFormRef.value?.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  try {
    await authStore.register(registerForm.username, registerForm.password)
    ElMessage.success('注册成功')
    router.push('/dashboard')
  } catch (err: unknown) {
    showApiError(err, '注册失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  height: 100dvh;
  display: flex;
  background: var(--color-bg);
}

/* ── Left Visual Panel ── */
.login-visual {
  flex: 1;
  background: linear-gradient(160deg, #0d1220 0%, #0a0f1a 50%, #070a12 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
  min-width: 0;
}

.visual-content {
  position: relative;
  z-index: 2;
  text-align: center;
  animation: fadeInUp 0.8s cubic-bezier(0.16, 1, 0.3, 1) both;
}

.brand-mark {
  margin-bottom: 24px;
  opacity: 0.9;
  display: flex;
  justify-content: center;
}

.brand-logo-image {
  max-width: 120px;
  height: auto;
}

.brand-title {
  font-family: var(--font-display);
  font-size: 42px;
  font-weight: 700;
  color: #fff;
  letter-spacing: 0.02em;
  line-height: 1.1;
  margin-bottom: 8px;
}

.brand-subtitle {
  font-size: 15px;
  color: rgba(255, 255, 255, 0.4);
  letter-spacing: 0.1em;
  font-weight: 400;
}

.brand-features {
  margin-top: 48px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  align-items: flex-start;
}

.feature-item {
  display: flex;
  align-items: center;
  gap: 12px;
  color: rgba(255, 255, 255, 0.5);
  font-size: 14px;
  font-weight: 500;
  letter-spacing: 0.02em;
  animation: fadeInUp 0.6s cubic-bezier(0.16, 1, 0.3, 1) both;
}

.feature-item:nth-child(1) { animation-delay: 0.2s; }
.feature-item:nth-child(2) { animation-delay: 0.3s; }
.feature-item:nth-child(3) { animation-delay: 0.4s; }
.feature-item:nth-child(4) { animation-delay: 0.5s; }

.feature-icon {
  color: var(--color-accent-light);
  font-size: 10px;
}

/* ── Grid Overlay ── */
.grid-overlay {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.02) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.02) 1px, transparent 1px);
  background-size: 60px 60px;
  z-index: 1;
}

/* ── Right Form Panel ── */
.login-form-panel {
  width: 480px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  background: var(--color-surface);
  border-left: 1px solid var(--border-subtle);
  position: relative;
}

.form-container {
  width: 100%;
  max-width: 360px;
  padding: 0 24px;
  animation: fadeInUp 0.5s cubic-bezier(0.16, 1, 0.3, 1) 0.1s both;
}

.form-header {
  margin-bottom: 36px;
}

.form-header h2 {
  font-family: var(--font-display);
  font-size: 26px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 6px;
}

.form-header p {
  font-size: 14px;
  color: var(--text-secondary);
}

.submit-btn {
  width: 100%;
  height: 44px;
  font-size: 15px;
  letter-spacing: 0.1em;
  border-radius: var(--radius-sm) !important;
}

.form-footer {
  position: absolute;
  bottom: 24px;
  font-size: 12px;
  color: var(--text-muted);
}

/* ── Tabs ── */
.login-tabs :deep(.el-tabs__nav-wrap::after) {
  background-color: var(--border-subtle);
}

/* ── Responsive ── */
@media (max-width: 900px) {
  .login-visual {
    display: none;
  }

  .login-form-panel {
    width: 100%;
    border-left: none;
  }
}

@media (max-width: 480px) {
  .form-container {
    padding: 0 16px;
  }

  .form-header h2 {
    font-size: 22px;
  }

  .brand-title {
    font-size: 32px;
  }
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
