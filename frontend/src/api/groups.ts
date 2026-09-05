import api from './index'
import type { UserGroup, GroupDetail } from '@/types/group'

export function getGroups() {
  return api.get<UserGroup[]>('/settings/groups')
}

export function getGroupDetail(groupId: number) {
  return api.get<GroupDetail>(`/settings/groups/${groupId}`)
}

export function createGroup(data: { name: string; description?: string }) {
  return api.post<{ id: number }>('/settings/groups', data)
}

export function updateGroup(groupId: number, data: { name?: string; description?: string }) {
  return api.put(`/settings/groups/${groupId}`, data)
}

export function deleteGroup(groupId: number) {
  return api.delete(`/settings/groups/${groupId}`)
}

export function addGroupMembers(groupId: number, userIds: number[]) {
  return api.post(`/settings/groups/${groupId}/members`, { user_ids: userIds })
}

export function removeGroupMember(groupId: number, userId: number) {
  return api.delete(`/settings/groups/${groupId}/members/${userId}`)
}

export function setGroupPermissions(groupId: number, permissions: Record<string, any>) {
  return api.put(`/settings/groups/${groupId}/permissions`, permissions)
}

export function setGroupStrategyPermission(
  groupId: number,
  data: { strategy_id: string; can_trade: boolean }
) {
  return api.post(`/settings/groups/${groupId}/strategy-permissions`, data)
}

export function deleteGroupStrategyPermission(groupId: number, strategyId: string) {
  return api.delete(`/settings/groups/${groupId}/strategy-permissions/${strategyId}`)
}

export function setGroupToolPermission(
  groupId: number,
  data: { tool_key: string; enabled: boolean }
) {
  return api.post(`/settings/groups/${groupId}/tool-permissions`, data)
}
