import api from './index'
import type { UserProfile, UserMemory, ProfileUpdatePayload } from '@/types/memory'

export const memoryApi = {
  /** 获取用户画像 */
  getProfile() {
    return api.get<UserProfile>('/memory/profile')
  },

  /** 更新用户画像 */
  updateProfile(data: ProfileUpdatePayload) {
    return api.put<UserProfile>('/memory/profile', data)
  },

  /** 获取记忆列表 */
  getMemories(category?: string) {
    return api.get<{ memories: UserMemory[] }>('/memory/memories', {
      params: category ? { category } : {},
    })
  },

  /** 添加记忆 */
  addMemory(data: { category: string; content: string }) {
    return api.post<UserMemory>('/memory/memories', data)
  },

  /** 删除记忆 */
  deleteMemory(id: number) {
    return api.delete<{ success: boolean }>(`/memory/memories/${id}`)
  },
}
