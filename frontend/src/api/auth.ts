import api from './index'
import type { LoginRequest, LoginResponse, UserInfo } from '@/types/auth'

export function login(data: LoginRequest) {
  return api.post<LoginResponse>('/auth/login', data)
}

export function register(data: LoginRequest) {
  return api.post<LoginResponse>('/auth/register', data)
}

export function getMe() {
  return api.get<UserInfo>('/auth/me')
}
