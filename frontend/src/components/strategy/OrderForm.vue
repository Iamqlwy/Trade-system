<template>
  <el-card shadow="never" class="order-form-card">
    <template #header>
      <span class="card-section-title">下单</span>
    </template>
    <el-form ref="formRef" :model="form" :rules="rules" label-width="80px" size="default">
      <el-form-item label="股票代码" prop="stock_code">
        <el-input v-model="form.stock_code" placeholder="如 000001" maxlength="10" />
      </el-form-item>
      <el-form-item label="方向" prop="order_type">
        <el-radio-group v-model="form.order_type" class="direction-group">
          <el-radio-button :value="23">
            <span class="direction-buy">买入</span>
          </el-radio-button>
          <el-radio-button :value="24">
            <span class="direction-sell">卖出</span>
          </el-radio-button>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="价格类型" prop="price_type">
        <el-select v-model="form.price_type" style="width: 100%">
          <el-option :value="11" label="限价" />
          <el-option :value="5" label="最新价" />
        </el-select>
      </el-form-item>
      <el-form-item label="委托价格" prop="price">
        <el-input-number
          v-model="form.price"
          :min="0.01"
          :step="0.01"
          :precision="2"
          style="width: 100%"
        />
      </el-form-item>
      <el-form-item label="委托数量" prop="order_volume">
        <el-input-number
          v-model="form.order_volume"
          :min="100"
          :step="100"
          style="width: 100%"
        />
      </el-form-item>
      <el-form-item label="备注">
        <el-input v-model="form.order_remark" placeholder="可选" maxlength="200" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :loading="submitting" @click="handleSubmit" class="submit-order-btn">
          提交委托
        </el-button>
      </el-form-item>
    </el-form>
  </el-card>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { showApiError } from '@/utils/notify'
import type { FormInstance, FormRules } from 'element-plus'
import * as ordersApi from '@/api/orders'
import type { OrderRequest } from '@/types/order'
import { isValidStockCode, cleanSingleLineInput } from '@/utils/validation'

const props = defineProps<{ strategyId: string }>()
const emit = defineEmits<{ success: [] }>()

const formRef = ref<FormInstance>()
const submitting = ref(false)

const form = reactive<OrderRequest>({
  stock_code: '',
  order_type: 23,
  price: 0,
  order_volume: 100,
  price_type: 11,
  order_remark: '',
})

const rules: FormRules = {
  stock_code: [
    { required: true, message: '请输入股票代码', trigger: 'blur' },
    {
      validator: (_rule: any, value: string, callback: any) => {
        if (value && !isValidStockCode(value)) {
          callback(new Error('股票代码格式错误，应为 6 位数字（如 000001 或 000001.SZ）'))
        } else {
          callback()
        }
      },
      trigger: 'blur',
    },
  ],
  order_type: [{ required: true, message: '请选择方向', trigger: 'change' }],
  price: [
    { required: true, message: '请输入委托价格', trigger: 'blur' },
    {
      validator: (_rule: any, value: number, callback: any) => {
        if (value > 999999.99) {
          callback(new Error('委托价格不能超过 999999.99'))
        } else {
          callback()
        }
      },
      trigger: 'blur',
    },
  ],
  order_volume: [{ required: true, message: '请输入委托数量', trigger: 'blur' }],
}

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  try {
    const res = await ordersApi.placeOrder(props.strategyId, form)
    if (res.data.success) {
      ElMessage.success(`委托成功，订单号: ${res.data.order_id}`)
      emit('success')
      form.stock_code = ''
      form.price = 0
      form.order_volume = 100
      form.order_remark = ''
    } else {
      ElMessage.error(res.data.message || '委托失败')
    }
  } catch (err: unknown) {
    showApiError(err, '提交失败')
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.order-form-card {
  border-radius: var(--radius-md) !important;
}

.card-section-title {
  font-family: var(--font-display);
  font-weight: 600;
  font-size: 15px;
}

.submit-order-btn {
  width: 100%;
  height: 42px;
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0.05em;
  border-radius: var(--radius-sm) !important;
}
</style>
