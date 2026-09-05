import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { StrategySummary, CreateStrategyRequest, UpdateStrategyRequest } from '@/types/strategy'
import * as strategiesApi from '@/api/strategies'
import { showApiError } from '@/utils/notify'

export const useStrategiesStore = defineStore('strategies', () => {
  const strategies = ref<StrategySummary[]>([])
  const loading = ref(false)

  async function fetchStrategies() {
    loading.value = true
    try {
      const res = await strategiesApi.listStrategies()
      strategies.value = res.data
    } catch (err) {
      showApiError(err, '加载策略列表失败')
    } finally {
      loading.value = false
    }
  }

  async function createStrategy(req: CreateStrategyRequest) {
    const res = await strategiesApi.createStrategy(req)
    await fetchStrategies()
    return res.data
  }

  async function updateStrategy(strategyId: string, req: UpdateStrategyRequest) {
    const res = await strategiesApi.updateStrategy(strategyId, req)
    await fetchStrategies()
    return res.data
  }

  async function deleteStrategy(strategyId: string) {
    const res = await strategiesApi.deleteStrategy(strategyId)
    await fetchStrategies()
    return res.data
  }

  return { strategies, loading, fetchStrategies, createStrategy, updateStrategy, deleteStrategy }
})
