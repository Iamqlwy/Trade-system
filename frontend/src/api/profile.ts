import api from './index'
import type {
  UserProfile,
  UserProfileUpdate,
  PasswordChangeRequest,
  InvestmentStats,
} from '@/types/auth'

export function getProfile() {
  return api.get<UserProfile>('/profile/me')
}

export function updateProfile(data: UserProfileUpdate) {
  return api.put<UserProfile>('/profile/me', data)
}

export function changePassword(data: PasswordChangeRequest) {
  return api.post<{ success: boolean; message: string }>('/profile/change-password', data)
}

export function getInvestmentStats() {
  return api.get<InvestmentStats>('/profile/stats')
}
