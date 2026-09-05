<template>
  <Teleport to="body">
    <Transition name="confirm-fade">
      <div v-if="visible" class="confirm-overlay">
        <div class="confirm-card">
          <!-- Header -->
          <div class="confirm-header">
            <div class="confirm-icon">
              <el-icon :size="24"><Warning /></el-icon>
            </div>
            <div>
              <h3 class="confirm-title">下单确认</h3>
              <p class="confirm-subtitle">
                API Token <strong>{{ item.api_token_name || '未命名' }}</strong> 请求下单
              </p>
            </div>
          </div>

          <!-- Order Details -->
          <div class="confirm-details">
            <div class="detail-row">
              <span class="detail-label">策略</span>
              <span class="detail-value">{{ item.strategy_name }} ({{ item.strategy_id }})</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">股票</span>
              <span class="detail-value">{{ item.stock_name }} {{ item.stock_code }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">方向</span>
              <span class="detail-value" :class="isBuy ? 'color-buy' : 'color-sell'">
                {{ isBuy ? '买入' : '卖出' }}
              </span>
            </div>
            <div class="detail-row">
              <span class="detail-label">价格</span>
              <span class="detail-value">¥{{ item.price }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">数量</span>
              <span class="detail-value">{{ item.order_volume }} 股</span>
            </div>
            <div v-if="item.order_remark" class="detail-row">
              <span class="detail-label">备注</span>
              <span class="detail-value">{{ item.order_remark }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">剩余时间</span>
              <span class="detail-value countdown" :class="{ urgent: remainingSeconds <= 60 }">
                {{ formatCountdown(remainingSeconds) }}
              </span>
            </div>
          </div>

          <!-- Actions (normal mode) -->
          <div v-if="!showRejectPanel" class="confirm-actions">
            <el-button
              type="danger"
              size="large"
              :loading="rejecting"
              @click="showRejectPanel = true"
            >
              拒绝
            </el-button>
            <el-button
              type="primary"
              size="large"
              :loading="approving"
              @click="handleApprove"
            >
              确认下单
            </el-button>
          </div>

          <!-- Reject reason panel -->
          <div v-else class="reject-panel">
            <p class="reject-panel-title">请选择拒绝原因：</p>
            <div class="reject-reasons">
              <div
                v-for="reason in presetReasons"
                :key="reason"
                class="reason-tag"
                :class="{ active: selectedReason === reason }"
                @click="selectedReason = reason"
              >
                {{ reason }}
              </div>
            </div>
            <el-input
              v-model="customReason"
              type="textarea"
              :rows="2"
              placeholder="补充说明（可选）"
              maxlength="200"
              show-word-limit
              class="reject-custom-input"
            />
            <div class="reject-actions">
              <el-button size="large" @click="cancelReject">取消</el-button>
              <el-button
                type="danger"
                size="large"
                :loading="rejecting"
                @click="handleReject"
              >
                确认拒绝
              </el-button>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue'
import { Warning } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { showApiError } from '@/utils/notify'
import { approveConfirmation, rejectConfirmation } from '@/api/confirmApi'
import type { OrderConfirmNotification } from '@/composables/useNotifications'

const props = defineProps<{
  item: OrderConfirmNotification
  visible: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'approved', orderId: string): void
  (e: 'rejected'): void
}>()

const approving = ref(false)
const rejecting = ref(false)
const showRejectPanel = ref(false)
const selectedReason = ref('')
const customReason = ref('')

const presetReasons = ['价格不合适', '市场风险', '策略判断有误', '资金不足']

const isBuy = computed(() => [23, 27].includes(props.item.order_type))

// 倒计时
const remainingSeconds = ref(0)
let countdownTimer: ReturnType<typeof setInterval> | null = null

function startCountdown() {
  updateRemaining()
  countdownTimer = setInterval(updateRemaining, 1000)
}

function updateRemaining() {
  const expires = new Date(props.item.expires_at).getTime()
  const now = Date.now()
  remainingSeconds.value = Math.max(0, Math.floor((expires - now) / 1000))
  if (remainingSeconds.value <= 0) {
    stopCountdown()
    emit('close')
    ElMessage.warning('确认请求已过期')
  }
}

function stopCountdown() {
  if (countdownTimer) {
    clearInterval(countdownTimer)
    countdownTimer = null
  }
}

function formatCountdown(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

watch(() => props.visible, (val) => {
  if (val) {
    startCountdown()
    showRejectPanel.value = false
    selectedReason.value = ''
    customReason.value = ''
  } else {
    stopCountdown()
  }
})

onUnmounted(() => {
  stopCountdown()
})

async function handleApprove() {
  approving.value = true
  try {
    const res = await approveConfirmation(props.item.confirmation_id)
    ElMessage.success(res.data.message || '订单已执行')
    emit('approved', res.data.order_id)
    emit('close')
  } catch (err: any) {
    showApiError(err, '确认失败')
  } finally {
    approving.value = false
  }
}

async function handleReject() {
  const reason = selectedReason.value === '其他'
    ? customReason.value
    : [selectedReason.value, customReason.value].filter(Boolean).join('；')

  rejecting.value = true
  try {
    await rejectConfirmation(props.item.confirmation_id, reason)
    ElMessage.info('已拒绝')
    emit('rejected')
    emit('close')
  } catch (err: any) {
    showApiError(err, '操作失败')
  } finally {
    rejecting.value = false
  }
}

function cancelReject() {
  showRejectPanel.value = false
  selectedReason.value = ''
  customReason.value = ''
}
</script>

<style scoped>
.confirm-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10000;
  backdrop-filter: blur(4px);
}

.confirm-card {
  background: #1a1f2e;
  border: 1px solid rgba(201, 165, 90, 0.3);
  border-radius: 16px;
  padding: 28px;
  width: 420px;
  max-width: 90vw;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
}

.confirm-header {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  margin-bottom: 20px;
}

.confirm-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  background: rgba(231, 76, 60, 0.15);
  color: #e74c3c;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.confirm-title {
  font-size: 18px;
  font-weight: 600;
  color: #fff;
  margin: 0 0 4px;
}

.confirm-subtitle {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.5);
  margin: 0;
}

.confirm-subtitle strong {
  color: #c9a55a;
}

.confirm-details {
  background: rgba(0, 0, 0, 0.2);
  border-radius: 10px;
  padding: 14px 16px;
  margin-bottom: 20px;
}

.detail-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 0;
  font-size: 13px;
}

.detail-row + .detail-row {
  border-top: 1px solid rgba(255, 255, 255, 0.05);
}

.detail-label {
  color: rgba(255, 255, 255, 0.4);
}

.detail-value {
  color: #fff;
  font-weight: 500;
}

.color-buy {
  color: #e74c3c;
}

.color-sell {
  color: #27ae60;
}

.countdown {
  font-family: 'JetBrains Mono', monospace;
  color: #c9a55a;
}

.countdown.urgent {
  color: #e74c3c;
  animation: blink 1s infinite;
}

@keyframes blink {
  50% { opacity: 0.5; }
}

.confirm-actions {
  display: flex;
  gap: 12px;
}

.confirm-actions .el-button {
  flex: 1;
}

/* Transition */
.confirm-fade-enter-active,
.confirm-fade-leave-active {
  transition: opacity 0.25s ease;
}
.confirm-fade-enter-active .confirm-card,
.confirm-fade-leave-active .confirm-card {
  transition: transform 0.25s ease;
}

.confirm-fade-enter-from,
.confirm-fade-leave-to {
  opacity: 0;
}
.confirm-fade-enter-from .confirm-card {
  transform: scale(0.9);
}
.confirm-fade-leave-to .confirm-card {
  transform: scale(0.9);
}

/* Reject panel */
.reject-panel {
  margin-top: 4px;
}

.reject-panel-title {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.6);
  margin: 0 0 10px;
}

.reject-reasons {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.reason-tag {
  padding: 6px 14px;
  border-radius: 6px;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.7);
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.1);
  cursor: pointer;
  transition: all 0.2s;
  user-select: none;
}

.reason-tag:hover {
  background: rgba(231, 76, 60, 0.1);
  border-color: rgba(231, 76, 60, 0.3);
  color: #e74c3c;
}

.reason-tag.active {
  background: rgba(231, 76, 60, 0.15);
  border-color: #e74c3c;
  color: #e74c3c;
}

.reject-custom-input {
  margin-bottom: 14px;
}

.reject-custom-input :deep(.el-textarea__inner) {
  background: rgba(0, 0, 0, 0.2);
  border-color: rgba(255, 255, 255, 0.1);
  color: #fff;
}

.reject-custom-input :deep(.el-textarea__inner::placeholder) {
  color: rgba(255, 255, 255, 0.3);
}

.reject-custom-input :deep(.el-input__count) {
  background: transparent;
  color: rgba(255, 255, 255, 0.3);
}

.reject-actions {
  display: flex;
  gap: 12px;
}

.reject-actions .el-button {
  flex: 1;
}
</style>
