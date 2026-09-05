import { ref, computed, triggerRef } from 'vue'
import { ElMessage } from 'element-plus'
import { useWebSocket } from './useWebSocket'
import { notify } from './useNotification'
import api from '@/api'
import { cleanInput } from '@/utils/validation'

// 消息块类型 - 按顺序显示
export interface TextBlock {
  type: 'text'
  content: string
}

export interface ImageBlock {
  type: 'image'
  url: string
  name?: string
}

export interface ToolCallBlock {
  type: 'tool_call'
  toolCall: ToolCall
}

export interface SubAgentBlock {
  type: 'sub_agent'
  subAgent: SubAgentInfo
}

export type MessageBlock = TextBlock | ImageBlock | ToolCallBlock | SubAgentBlock

export interface AgentMessage {
  id: string
  role: 'user' | 'assistant'
  blocks: MessageBlock[]  // 按顺序的块
  timestamp: number
  isThinking?: boolean
  rawContent?: string     // 用户原始输入（加工前）
}

export interface ToolCall {
  id: string
  name: string
  args: string
  result?: string
  status: 'running' | 'done' | 'completed' | 'error' | 'interrupted'
}

export interface SubAgentInfo {
  id: string
  label: string
  type: string
  status: 'running' | 'completed' | 'error'
  task_description: string
  output?: string
  toolCalls?: ToolCall[]
}

export interface SessionInfo {
  id: string
  title: string
  summary: string
  message_count: number
  updated_at: string
}

export interface PendingQuestion {
  question: string
  header: string
  options: string[]
  multi: boolean
  requestId: string
}

import type { CronEvent } from '@/types/cron'

export function useAgentChat() {
  // ═══ 按 session 隔离的状态 ═══
  // sessionId → 该会话的消息列表
  const messagesMap = ref(new Map<string, AgentMessage[]>())
  // 哪些 session 正在 streaming
  const streamingSessions = ref(new Set<string>())
  // sessionId → 当前正在构建的 assistant 消息 id
  const assistantIdMap = new Map<string, string | null>()
  // sessionId → 该会话的待回答问题数组（支持多问题同时提问）
  const pendingQuestionMap = ref(new Map<string, PendingQuestion[]>())

  // ═══ Cron 事件流 ═══
  const cronEvents = ref<CronEvent[]>([])

  // ═══ 会话级共享状态 ═══
  const sessions = ref<SessionInfo[]>([])
  const currentSessionId = ref<string | null>(null)
  // 等待会话创建完成后发送的消息（含图片）
  let pendingSendMessage: { content: string; images?: Array<{ url: string; name: string }> } | null = null
  // 是否正在等待会话创建（用于 UI 立即切换到消息视图）
  const sessionCreating = ref(false)
  // 是否正在恢复会话历史（用于 UI 显示加载状态）
  const sessionRestoring = ref(false)
  // 恢复超时定时器（安全网：防止 restored 事件丢失导致永久 loading）
  let restoreTimer: ReturnType<typeof setTimeout> | null = null

  // ═══ Plan mode 状态 ═══
  // sessionId → 该会话是否处于 plan mode
  const planModeMap = ref(new Map<string, boolean>())
  // 无会话时的临时 plan mode 状态
  const pendingPlanMode = ref(false)

  const planMode = computed(() => {
    const sid = currentSessionId.value
    if (!sid) return pendingPlanMode.value
    return planModeMap.value.get(sid) || false
  })

  /** 检查指定会话是否处于 plan mode */
  function isPlanMode(sessionId: string): boolean {
    return planModeMap.value.get(sessionId) || false
  }

  // ═══ 当前会话的 computed 视图 ═══
  const messages = computed(() => {
    const sid = currentSessionId.value
    if (!sid) return []
    return messagesMap.value.get(sid) || []
  })

  const streaming = computed(() => {
    const sid = currentSessionId.value
    return sid ? streamingSessions.value.has(sid) : false
  })

  const pendingQuestion = computed(() => {
    const sid = currentSessionId.value
    if (!sid) return []
    return pendingQuestionMap.value.get(sid) || []
  })

  const { connected, connect, disconnect, send } = useWebSocket('/ws/agent', {
    onMessage: (raw) => {
      const event = raw as Record<string, unknown>
      if (event.type === 'cron_event') {
        cronEvents.value = [...cronEvents.value.slice(-49), event as unknown as CronEvent]
        // OS 通知：cron 任务完成/失败
        const cronEvent = event.event as string
        if (cronEvent === 'cron_run_completed' || cronEvent === 'cron_run_failed') {
          const jobName = (event.data as Record<string, unknown>)?.name as string || '定时任务'
          const isSuccess = cronEvent === 'cron_run_completed'
          notify({
            title: isSuccess ? '定时任务完成' : '定时任务失败',
            body: `「${jobName}」${isSuccess ? '已执行完成' : '执行失败'}`,
            tag: `cron-${(event.data as Record<string, unknown>)?.run_id || ''}`,
            navigateTo: '/agent',
          })
        }
        return
      }
      if (event.type === 'agent_stream') {
        handleAgentEvent(event)
      }
    },
    onError: () => {
      // WebSocket 连接错误（如后端崩溃、网络断开），在 UI 上给出提示
      console.warn('[AgentChat] WebSocket 连接异常，消息将无法实时推送')
    },
  })

  // ---------------------------------------------------------------------------
  // 辅助函数
  // ---------------------------------------------------------------------------

  /** 获取或创建指定 session 的消息数组 */
  function getMessagesForSession(sessionId: string): AgentMessage[] {
    let arr = messagesMap.value.get(sessionId)
    if (!arr) {
      arr = []
      const newMap = new Map(messagesMap.value)
      newMap.set(sessionId, arr)
      messagesMap.value = newMap
    }
    return arr
  }

  /** 获取指定 session 当前 assistant id */
  function getAssistantId(sessionId: string): string | null {
    return assistantIdMap.get(sessionId) ?? null
  }

  /** 设置指定 session 的 assistant id */
  function setAssistantId(sessionId: string, id: string | null) {
    assistantIdMap.set(sessionId, id)
  }

  /** 确保有 assistant 消息（per-session），返回该消息 */
  function ensureAssistantMessage(sessionId: string): AgentMessage {
    const msgs = getMessagesForSession(sessionId)
    const asstId = getAssistantId(sessionId)
    const last = msgs[msgs.length - 1]
    if (last && last.role === 'assistant' && last.id === asstId) {
      return last
    }
    // 创建新的 assistant 消息
    const newId = `asst-${Date.now()}-${sessionId.slice(0, 4)}`
    setAssistantId(sessionId, newId)
    const newMsg: AgentMessage = {
      id: newId,
      role: 'assistant',
      blocks: [],
      timestamp: Date.now(),
      isThinking: true,
    }
    msgs.push(newMsg)
    return newMsg
  }

  /** 获取或创建最后一个文本块 */
  function getOrCreateTextBlock(msg: AgentMessage): TextBlock {
    const lastBlock = msg.blocks[msg.blocks.length - 1]
    if (lastBlock && lastBlock.type === 'text') {
      return lastBlock
    }
    const newBlock: TextBlock = { type: 'text', content: '' }
    msg.blocks.push(newBlock)
    return newBlock
  }

  // ---------------------------------------------------------------------------
  // 历史记录恢复
  // ---------------------------------------------------------------------------

  /** 从历史记录重建消息列表（支持递归处理压缩记录） */
  function restoreFromHistory(history: Array<Record<string, unknown>>): AgentMessage[] {
    const result: AgentMessage[] = []
    let assistantMsgIndex = 0

    // 预构建 tool_call_id → result 映射（O(1) 查找）
    const toolResultMap = new Map<string, string>()
    for (const m of history) {
      if (m && m.role === 'tool' && m.tool_call_id) {
        toolResultMap.set(m.tool_call_id as string, (m.content as string) || '')
      }
    }

    // 当前正在收集的回复
    let currentReply: { blocks: MessageBlock[] } | null = null

    function flushReply() {
      if (!currentReply || currentReply.blocks.length === 0) {
        currentReply = null
        return
      }
      result.push({
        id: `restored-asst-${assistantMsgIndex++}`,
        role: 'assistant',
        blocks: [...currentReply.blocks],
        timestamp: Date.now(),
      })
      currentReply = null
    }

    function ensureReply() {
      if (!currentReply) {
        currentReply = { blocks: [] }
      }
    }

    for (let i = 0; i < history.length; i++) {
      const m = history[i]
      if (!m) continue

      // 可见性过滤：后端已过滤，此处为双重保险
      const meta = m._meta as Record<string, unknown> | undefined
      if (meta && meta.visible === false) {
        continue
      }

      const role = (m.role as string) || 'assistant'

      if (role === 'user') {
        flushReply()
        // 构建消息块（支持多模态内容）
        const rawContent = meta?.raw_content
        const content = m.content

        // 检查 raw_content 或 content 是否为多模态数组
        const contentArray = (Array.isArray(rawContent) ? rawContent : Array.isArray(content) ? content : null) as Array<Record<string, unknown>> | null

        const blocks: MessageBlock[] = []
        let textContent = ''

        if (contentArray) {
          // 多模态消息：提取文本和图片
          for (const part of contentArray) {
            if (part.type === 'text') {
              const text = (part.text as string) || ''
              if (text) blocks.push({ type: 'text', content: text })
              textContent += text
            } else if (part.type === 'image_url') {
              const imgUrl = (part.image_url as Record<string, unknown>)?.url as string || ''
              if (imgUrl) blocks.push({ type: 'image', url: imgUrl })
            }
          }
        } else {
          // 纯文本消息
          const text = (rawContent as string) || (content as string) || ''
          blocks.push({ type: 'text', content: text })
          textContent = text
        }

        result.push({
          id: `restored-user-${i}`,
          role: 'user',
          blocks,
          timestamp: Date.now() - (history.length - i) * 1000,
          rawContent: textContent || undefined,
        })
      } else if (role === '_command') {
        // 斜杠命令 — 作为用户消息显示（前端可见，但 agent 上下文中不存在）
        flushReply()
        const cmdContent = (meta?.raw_content as string) || (m.content as string) || ''
        result.push({
          id: `restored-cmd-${i}`,
          role: 'user',
          blocks: [{ type: 'text', content: cmdContent }],
          timestamp: Date.now() - (history.length - i) * 1000,
          rawContent: cmdContent,
        })
      } else if (role === 'assistant') {
        ensureReply()
        const content = (m.content as string) || ''
        const toolCallsRaw = m.tool_calls as Array<Record<string, unknown>> | undefined

        // 添加文本内容块
        if (content) {
          currentReply!.blocks.push({ type: 'text', content })
        }

        // 添加工具调用块
        if (toolCallsRaw && toolCallsRaw.length > 0) {
          for (const tcRaw of toolCallsRaw) {
            const tcId = (tcRaw.id as string) || ''
            const func = tcRaw.function as Record<string, unknown> | undefined
            const name = (func?.name as string) || ''
            const args = (func?.arguments as string) || '{}'
            const toolResult = toolResultMap.get(tcId) || ''
            // 从工具结果内容检测是否为错误
            const isErrorResult = _isToolResultError(toolResult)
            currentReply!.blocks.push({
              type: 'tool_call',
              toolCall: {
                id: tcId,
                name,
                args,
                result: toolResult || undefined,
                status: isErrorResult ? 'error' : 'done',
              },
            })
          }
        }
      } else if (role === 'tool') {
        // tool 结果已通过 toolResultMap 匹配，跳过
        continue
      } else if (role === '_sub_agent') {
        ensureReply()
        const action = (m.action as string) || ''
        const subAgentId = (m.sub_agent_id as string) || ''

        if (action === 'spawned') {
          const subAgent: SubAgentInfo = {
            id: subAgentId,
            label: (m.label as string) || (m.task_description as string) || '子任务',
            type: (m.sub_agent_type as string) || '',
            status: 'running',
            task_description: (m.task_description as string) || '',
            toolCalls: [],
          }
          currentReply!.blocks.push({ type: 'sub_agent', subAgent })
        } else if (action === 'completed') {
          const subBlock = currentReply!.blocks.find(
            b => b.type === 'sub_agent' && b.subAgent.id === subAgentId
          ) as SubAgentBlock | undefined
          if (subBlock) {
            subBlock.subAgent.status = (m.status as 'completed' | 'error') || 'completed'
            subBlock.subAgent.output = (m.result_summary as string) || ''
          }
        }
      } else if (role === '_tool_start') {
        // 子 agent 的工具调用开始（持久化记录）
        ensureReply()
        const subAgentId = (m.sub_agent_id as string) || ''
        const tcId = (m.tool_call_id as string) || ''
        const name = (m.name as string) || ''
        const args = JSON.stringify(m.args || {})

        if (subAgentId) {
          // 关联到对应的子 agent
          const subBlock = currentReply!.blocks.find(
            b => b.type === 'sub_agent' && b.subAgent.id === subAgentId
          ) as SubAgentBlock | undefined
          if (subBlock) {
            if (!subBlock.subAgent.toolCalls) subBlock.subAgent.toolCalls = []
            subBlock.subAgent.toolCalls.push({ id: tcId, name, args, status: 'done' })
          }
        } else {
          currentReply!.blocks.push({
            type: 'tool_call',
            toolCall: { id: tcId, name, args, status: 'done' },
          })
        }
      } else if (role === '_tool_end') {
        // 子 agent 的工具调用结束（更新结果）
        const subAgentId = (m.sub_agent_id as string) || ''
        const tcId = (m.tool_call_id as string) || ''
        const preview = (m.preview as string) || ''
        const isError = (m.is_error as boolean) || false

        if (subAgentId) {
          const subBlock = currentReply!.blocks.find(
            b => b.type === 'sub_agent' && b.subAgent.id === subAgentId
          ) as SubAgentBlock | undefined
          if (subBlock?.subAgent.toolCalls) {
            const tc = subBlock.subAgent.toolCalls.find(t => t.id === tcId)
            if (tc) {
              tc.result = preview
              tc.status = isError ? 'error' : 'done'
            }
          }
        } else {
          const toolBlock = currentReply!.blocks.find(
            b => b.type === 'tool_call' && b.toolCall.id === tcId
          ) as ToolCallBlock | undefined
          if (toolBlock) {
            toolBlock.toolCall.result = preview
            toolBlock.toolCall.status = isError ? 'error' : 'done'
          }
        }
      } else if (role === '_cmd_response') {
        // 斜杠命令的响应 — 作为 assistant 回复显示
        ensureReply()
        const cmdRespContent = (m.content as string) || ''
        if (cmdRespContent) {
          currentReply!.blocks.push({ type: 'text', content: cmdRespContent })
        }
      } else if (role === '_compact') {
        // 压缩记录 — 从 compressed_messages 递归重建
        flushReply()
        const compressedMessages = m.compressed_messages as Array<Record<string, unknown>> | undefined
        if (compressedMessages && compressedMessages.length > 0) {
          const restored = restoreFromHistory(compressedMessages)
          result.push(...restored)
        }
      }
    }

    flushReply()
    return result
  }

  // ---------------------------------------------------------------------------
  // 事件处理（核心：按 session_id 隔离）
  // ---------------------------------------------------------------------------

  function handleAgentEvent(event: Record<string, unknown>) {
    const evt = event.event as string
    const data = event.data as Record<string, unknown> | undefined
    const content = event.content as string | undefined
    const eventSessionId = event.session_id as string | undefined

    // ── 会话级事件（不关联特定 session 的消息流，始终处理） ──
    if (evt === 'session_list') {
      const list = (Array.isArray(data) ? data : Array.isArray(event) ? event : []) as SessionInfo[]
      sessions.value = list
      return
    }
    if (evt === 'session_created') {
      const sid = (data?.session_id as string) || ''
      if (sid) {
        currentSessionId.value = sid
        sessionCreating.value = false
        // 将临时 plan mode 状态应用到新会话
        if (pendingPlanMode.value) {
          planModeMap.value.set(sid, true)
          planModeMap.value = new Map(planModeMap.value)
          // 通知后端同步状态
          send({ action: 'toggle_plan_mode', session_id: sid })
          pendingPlanMode.value = false
        }
        if (!sessions.value.find(s => s.id === sid)) {
          sessions.value.unshift({
            id: sid,
            title: '新对话',
            summary: '',
            message_count: 0,
            updated_at: new Date().toISOString(),
          })
        }
        // 如果有等待发送的消息，会话创建好后立即发送
        if (pendingSendMessage !== null) {
          const { content: pendingContent, images: pendingImages } = pendingSendMessage
          pendingSendMessage = null
          // 构建消息块
          const blocks: MessageBlock[] = [{ type: 'text', content: pendingContent }]
          if (pendingImages) {
            for (const img of pendingImages) {
              blocks.push({ type: 'image', url: img.url, name: img.name })
            }
          }
          // 添加用户消息到会话
          const msgs = getMessagesForSession(sid)
          msgs.push({
            id: `user-${Date.now()}`,
            role: 'user',
            blocks,
            timestamp: Date.now(),
            rawContent: pendingContent,
          })
          const wsPayload: Record<string, unknown> = {
            action: 'send_message',
            session_id: sid,
            content: pendingContent,
          }
          if (pendingImages && pendingImages.length > 0) {
            wsPayload.images = pendingImages
          }
          send(wsPayload)
        }
      }
      return
    }
    if (evt === 'session_upgraded') {
      // 临时会话升级为真实会话：迁移所有前端状态
      const oldId = (data?.old_id as string) || ''
      const newId = (data?.session_id as string) || ''
      if (oldId && newId) {
        // 迁移消息列表
        const oldMsgs = messagesMap.value.get(oldId)
        if (oldMsgs) {
          messagesMap.value.set(newId, oldMsgs)
          messagesMap.value.delete(oldId)
        }
        // 迁移 sessions 列表条目
        const session = sessions.value.find(s => s.id === oldId)
        if (session) session.id = newId
        // 迁移 streaming 状态
        if (streamingSessions.value.has(oldId)) {
          streamingSessions.value.delete(oldId)
          streamingSessions.value.add(newId)
        }
        // 迁移其他映射
        if (assistantIdMap.has(oldId)) {
          assistantIdMap.set(newId, assistantIdMap.get(oldId) ?? null)
          assistantIdMap.delete(oldId)
        }
        if (pendingQuestionMap.value.has(oldId)) {
          const pq = pendingQuestionMap.value.get(oldId)
          if (pq) pendingQuestionMap.value.set(newId, pq)
          pendingQuestionMap.value.delete(oldId)
        }
        // 迁移 plan mode 状态
        if (planModeMap.value.has(oldId)) {
          planModeMap.value.set(newId, planModeMap.value.get(oldId)!)
          planModeMap.value.delete(oldId)
          planModeMap.value = new Map(planModeMap.value)
        }
        // 切换当前会话 ID
        if (currentSessionId.value === oldId) {
          currentSessionId.value = newId
        }
        // 如果有排队等待升级后发送的消息，现在发送
        if (pendingSendMessage !== null) {
          const { content: pendingContent, images: pendingImages } = pendingSendMessage
          pendingSendMessage = null
          const blocks: MessageBlock[] = [{ type: 'text', content: pendingContent }]
          if (pendingImages) {
            for (const img of pendingImages) {
              blocks.push({ type: 'image', url: img.url, name: img.name })
            }
          }
          const msgs = getMessagesForSession(newId)
          msgs.push({
            id: `user-${Date.now()}`,
            role: 'user',
            blocks,
            timestamp: Date.now(),
            rawContent: pendingContent,
          })
          const wsPayload: Record<string, unknown> = {
            action: 'send_message',
            session_id: newId,
            content: pendingContent,
          }
          if (pendingImages && pendingImages.length > 0) {
            wsPayload.images = pendingImages
          }
          send(wsPayload)
        }
      }
      return
    }
    if (evt === 'session_title_updated') {
      const sid = (data?.session_id as string) || ''
      const title = (data?.title as string) || ''
      if (sid && title) {
        const session = sessions.value.find(s => s.id === sid)
        if (session) {
          session.title = title
        }
      }
      return
    }
    if (evt === 'session_deleted') {
      const sid = (data?.session_id as string) || ''
      if (sid) {
        sessions.value = sessions.value.filter(s => s.id !== sid)
        // 清理该 session 的缓存状态
        messagesMap.value.delete(sid)
        assistantIdMap.delete(sid)
        pendingQuestionMap.value.delete(sid)
        streamingSessions.value.delete(sid)
        planModeMap.value.delete(sid)
        if (currentSessionId.value === sid) {
          currentSessionId.value = null
          sessionRestoring.value = false
          if (restoreTimer) {
            clearTimeout(restoreTimer)
            restoreTimer = null
          }
          localStorage.removeItem('agent_current_session')
        }
      }
      return
    }

    // ── plan_mode_toggled 事件：始终处理 ──
    if (evt === 'plan_mode_toggled') {
      const sid = eventSessionId || ''
      const newMode = (data?.plan_mode as boolean) || false
      if (sid) {
        planModeMap.value.set(sid, newMode)
        planModeMap.value = new Map(planModeMap.value)
      }
      return
    }

    // ── restored 事件：会话历史恢复（始终处理，不受 isCurrentSession 过滤）──
    // 这是 restore_session action 的直接响应，不是流式消息事件。
    // 页面刷新时，currentSessionId 与 eventSessionId 可能存在微妙的时序竞争，
    // 因此必须在这里处理，否则 sessionRestoring 会永远卡在 true。
    if (evt === 'restored') {
      const sid = eventSessionId || ''
      if (sid === currentSessionId.value) {
        sessionRestoring.value = false
        if (restoreTimer) {
          clearTimeout(restoreTimer)
          restoreTimer = null
        }
      }
      if (sid) {
        const history = (data?.messages as Array<Record<string, unknown>>) || []
        const restored = restoreFromHistory(history)
        const arr = getMessagesForSession(sid)
        arr.length = 0
        arr.push(...restored)
        // 触发 messagesMap 响应式更新（computed messages 依赖此 Map）
        messagesMap.value = new Map(messagesMap.value)
        // 如果恢复的消息末尾是 assistant，将 assistantId 指向它，
        // 这样后续 streaming 事件会追加到该消息而非创建新气泡（避免一次回复被切割成多个头像）
        const lastRestored = restored[restored.length - 1]
        if (lastRestored && lastRestored.role === 'assistant') {
          setAssistantId(sid, lastRestored.id)
        } else {
          setAssistantId(sid, null)
        }
        // 恢复 plan mode 状态
        const restoredPlanMode = (data?.plan_mode as boolean) || false
        if (restoredPlanMode !== undefined) {
          planModeMap.value.set(sid, restoredPlanMode)
          planModeMap.value = new Map(planModeMap.value)
        }
      }
      return
    }

    // ── error 事件：如果正在恢复会话，先清除恢复状态（防止永久 loading）──
    if (evt === 'error' && eventSessionId && eventSessionId === currentSessionId.value && sessionRestoring.value) {
      sessionRestoring.value = false
      if (restoreTimer) {
        clearTimeout(restoreTimer)
        restoreTimer = null
      }
      // 继续往下走，在"当前会话"分支中显示错误消息
    }

    // ── 消息流事件：按 session_id 过滤 ──
    if (!eventSessionId) return

    const isCurrentSession = eventSessionId === currentSessionId.value

    // 非当前会话的事件：只更新 streaming 状态，不修改消息内容
    if (!isCurrentSession) {
      if (evt === 'token' || evt === 'thinking' || evt === 'tool_start') {
        streamingSessions.value.add(eventSessionId)
      } else if (evt === 'done' || evt === 'error') {
        streamingSessions.value.delete(eventSessionId)
      }
      // ask_user 事件需要在对应会话中追加，以便切换后显示（支持多问题）
      if (evt === 'ask_user') {
        const arr = pendingQuestionMap.value.get(eventSessionId) || []
        arr.push({
          question: (data?.question as string) || '',
          header: (data?.header as string) || 'Question',
          options: (data?.options as string[]) || [],
          multi: (data?.multi as boolean) || false,
          requestId: (data?.request_id as string) || '',
        })
        pendingQuestionMap.value.set(eventSessionId, arr)
        triggerRef(pendingQuestionMap)
      }
      return
    }

    // ── 当前会话的事件：完整处理 ──
    const msgs = getMessagesForSession(eventSessionId)

    if (evt === 'token') {
      streamingSessions.value.add(eventSessionId)
      const msg = ensureAssistantMessage(eventSessionId)
      msg.isThinking = false
      const textBlock = getOrCreateTextBlock(msg)
      textBlock.content += content || ''
    } else if (evt === 'thinking') {
      streamingSessions.value.add(eventSessionId)
      const msg = ensureAssistantMessage(eventSessionId)
      msg.isThinking = true
    } else if (evt === 'tool_start') {
      const subAgentId = data?.sub_agent_id as string | undefined
      const msg = ensureAssistantMessage(eventSessionId)
      msg.isThinking = false

      const toolCall: ToolCall = {
        id: (data?.tool_call_id as string) || '',
        name: (data?.name as string) || '',
        args: JSON.stringify(data?.args || {}),
        status: 'running',
      }

      // 如果有 sub_agent_id，将工具调用关联到对应的子 agent
      if (subAgentId) {
        const subBlock = msg.blocks.find(
          b => b.type === 'sub_agent' && b.subAgent.id === subAgentId
        ) as SubAgentBlock | undefined
        if (subBlock) {
          if (!subBlock.subAgent.toolCalls) subBlock.subAgent.toolCalls = []
          subBlock.subAgent.toolCalls.push(toolCall)
          return
        }
      }

      // 否则作为独立的工具调用块
      msg.blocks.push({ type: 'tool_call', toolCall })
    } else if (evt === 'tool_end') {
      const subAgentId = data?.sub_agent_id as string | undefined
      const toolCallId = data?.tool_call_id as string
      const msg = ensureAssistantMessage(eventSessionId)

      // 在子 agent 块中查找
      if (subAgentId) {
        const subBlock = msg.blocks.find(
          b => b.type === 'sub_agent' && b.subAgent.id === subAgentId
        ) as SubAgentBlock | undefined
        if (subBlock?.subAgent.toolCalls) {
          const tc = subBlock.subAgent.toolCalls.find(t => t.id === toolCallId)
          if (tc) {
            tc.result = (data?.preview as string) || ''
            tc.status = (data?.is_error as boolean) ? 'error' : 'done'
          }
          return
        }
      }

      // 在独立的工具调用块中查找
      const toolBlock = msg.blocks.find(
        b => b.type === 'tool_call' && b.toolCall.id === toolCallId
      ) as ToolCallBlock | undefined
      if (toolBlock) {
        toolBlock.toolCall.result = (data?.preview as string) || ''
        toolBlock.toolCall.status = (data?.is_error as boolean) ? 'error' : 'done'
      }
    } else if (evt === 'sub_agent') {
      const subData = data || {}
      const subId = (subData.sub_agent_id as string) || ''
      const action = (subData.action as string) || ''
      const msg = ensureAssistantMessage(eventSessionId)

      if (action === 'spawned') {
        const subAgent: SubAgentInfo = {
          id: subId,
          label: (subData.label as string) || (subData.task_description as string) || '子任务',
          type: (subData.sub_agent_type as string) || '',
          status: 'running',
          task_description: (subData.task_description as string) || '',
          toolCalls: [],
        }
        msg.blocks.push({ type: 'sub_agent', subAgent })
      } else if (action === 'completed') {
        const subBlock = msg.blocks.find(
          b => b.type === 'sub_agent' && b.subAgent.id === subId
        ) as SubAgentBlock | undefined
        if (subBlock) {
          subBlock.subAgent.status = (subData.status as 'completed' | 'error') || 'completed'
          subBlock.subAgent.output = (subData.result_summary as string) || ''
        }
      }
    } else if (evt === 'done') {
      streamingSessions.value.delete(eventSessionId)
      setAssistantId(eventSessionId, null)
      const last = msgs[msgs.length - 1]
      if (last) {
        last.isThinking = false
        if (last.role === 'assistant' && last.blocks.length === 0) {
          last.blocks.push({ type: 'text', content: '(无响应)' })
        }
      }
      // OS 通知：agent 任务完成（找会话标题）
      const session = sessions.value.find(s => s.id === eventSessionId)
      const sessionTitle = session?.title || 'Agent 对话'
      notify({
        title: 'Agent 任务完成',
        body: `「${sessionTitle}」已完成`,
        tag: `agent-done-${eventSessionId}`,
        navigateTo: `/agent/${eventSessionId}`,
      })
    } else if (evt === 'error') {
      streamingSessions.value.delete(eventSessionId)
      sessionRestoring.value = false
      if (restoreTimer) {
        clearTimeout(restoreTimer)
        restoreTimer = null
      }
      const errorMsg = (data?.message as string) || '发生错误'
      const msg = ensureAssistantMessage(eventSessionId)
      msg.blocks.push({ type: 'text', content: `⚠️ ${errorMsg}` })
    } else if (evt === 'ask_user') {
      // AskUserQuestion — 工具调用中等待用户输入，不改变 streaming 状态
      // 追加到数组（支持多问题同时提问）
      const arr = pendingQuestionMap.value.get(eventSessionId) || []
      arr.push({
        question: (data?.question as string) || '',
        header: (data?.header as string) || 'Question',
        options: (data?.options as string[]) || [],
        multi: (data?.multi as boolean) || false,
        requestId: (data?.request_id as string) || '',
      })
      pendingQuestionMap.value.set(eventSessionId, arr)
      triggerRef(pendingQuestionMap)
      // OS 通知：agent 需要用户回答问题
      const session = sessions.value.find(s => s.id === eventSessionId)
      const sessionTitle = session?.title || 'Agent 对话'
      notify({
        title: 'Agent 需要你的回答',
        body: `「${sessionTitle}」正在等待你的输入`,
        tag: `agent-ask-${eventSessionId}`,
        navigateTo: `/agent/${eventSessionId}`,
      })
    }
  }

  // ---------------------------------------------------------------------------
  // 用户操作
  // ---------------------------------------------------------------------------

  function sendMessage(content: string, images?: Array<{ url: string; name: string }>) {
    // ── 输入净化与长度检查 ──
    const MAX_CHAT_LENGTH = 50000
    content = cleanInput(content, MAX_CHAT_LENGTH)
    if (!content.trim() && (!images || images.length === 0)) {
      ElMessage.warning('消息内容不能为空')
      return
    }
    if (content.length > MAX_CHAT_LENGTH) {
      ElMessage.warning(`消息内容过长，上限 ${MAX_CHAT_LENGTH} 字符`)
      return
    }

    const isCommand = content.trim().startsWith('/')
    const hasImages = images && images.length > 0

    if (!currentSessionId.value) {
      if (isCommand && !hasImages) {
        // 斜杠命令且无会话：创建临时 session 仅用于显示结果，
        // 不发送 create_session 到后端 → 会话不保存到数据库
        const tempSid = `tmp-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
        currentSessionId.value = tempSid
        // 立即加入左侧会话列表，无需刷新才能看到
        sessions.value.unshift({
          id: tempSid,
          title: '新对话',
          summary: content.trim(),
          message_count: 0,
          updated_at: new Date().toISOString(),
        })
        getMessagesForSession(tempSid).push({
          id: `user-${Date.now()}`,
          role: 'user',
          blocks: [{ type: 'text', content }],
          timestamp: Date.now(),
          rawContent: content,
        })
        send({ action: 'send_message', session_id: tempSid, content })
        return
      }
      // 非命令（或有图片）：先创建会话，排队等待发送第一条消息
      // session_created 事件回来后会 flush pendingSendMessage
      pendingSendMessage = { content, images: hasImages ? images : undefined }
      sessionCreating.value = true
      send({ action: 'create_session' })
      return
    }

    const sid = currentSessionId.value

    // 临时会话（tmp-xxx）→ 先升级为真实会话，消息排队等升级完成后发送
    if (sid.startsWith('tmp-')) {
      // 不在此处添加用户消息 — 由 session_upgraded 处理器统一添加并发送
      pendingSendMessage = { content, images: hasImages ? images : undefined }
      send({ action: 'upgrade_session', session_id: sid })
      return
    }

    // 构建消息块
    const blocks: MessageBlock[] = [{ type: 'text', content }]
    if (hasImages) {
      for (const img of images!) {
        blocks.push({ type: 'image', url: img.url, name: img.name })
      }
    }

    // 添加用户消息到当前会话
    const msgs = getMessagesForSession(sid)
    msgs.push({
      id: `user-${Date.now()}`,
      role: 'user',
      blocks,
      timestamp: Date.now(),
      rawContent: content,
    })

    const wsPayload: Record<string, unknown> = {
      action: 'send_message',
      session_id: sid,
      content,
    }
    if (hasImages) {
      wsPayload.images = images
    }
    send(wsPayload)
  }

  function createNewSession() {
    // 只清空当前会话引用，不立即创建后端会话
    // 当用户发送第一条消息时，后端会自动创建会话
    console.log('[useAgentChat][createNewSession] currentSessionId: %s → null', currentSessionId.value)
    currentSessionId.value = null
    pendingPlanMode.value = false  // 重置临时 plan mode 状态
    sessionRestoring.value = false
    if (restoreTimer) {
      clearTimeout(restoreTimer)
      restoreTimer = null
    }
  }

  function switchSession(sessionId: string) {
    if (sessionId === currentSessionId.value) return
    console.log('[useAgentChat][switchSession] currentSessionId: %s → %s', currentSessionId.value, sessionId)
    // 只需切换 currentSessionId，messages computed 会自动指向对应的消息列表
    currentSessionId.value = sessionId
    sessionRestoring.value = true
    send({ action: 'restore_session', session_id: sessionId })
    // 安全超时：如果 3 秒内没有收到 restored 事件，重试一次 restore_session。
    // 正常情况下消息队列已保证送达，这里仅作为极端情况的兜底。
    if (restoreTimer) clearTimeout(restoreTimer)
    restoreTimer = setTimeout(() => {
      restoreTimer = null
      if (sessionRestoring.value && currentSessionId.value === sessionId) {
        console.warn('[useAgentChat] restored 事件超时，重试 restore_session:', sessionId)
        send({ action: 'restore_session', session_id: sessionId })
      }
    }, 3000)
  }

  function loadSessions() {
    send({ action: 'list_sessions' })
  }

  function answerQuestion(answer: string, requestId?: string) {
    const sid = currentSessionId.value
    if (!sid) return
    const arr = pendingQuestionMap.value.get(sid)
    if (!arr || arr.length === 0) return

    // 找到要回答的问题：优先用 requestId 匹配，否则取第一个
    const idx = requestId
      ? arr.findIndex(q => q.requestId === requestId)
      : 0
    if (idx < 0 || idx >= arr.length) return
    const q = arr[idx]

    // 通过 answer_question action 回复（作为工具输出，不创建 user 消息）
    send({
      action: 'answer_question',
      request_id: q.requestId,
      answer,
    })

    // 只移除已回答的那一个问题
    arr.splice(idx, 1)
    if (arr.length === 0) {
      pendingQuestionMap.value.delete(sid)
    } else {
      pendingQuestionMap.value.set(sid, arr)
    }
    triggerRef(pendingQuestionMap)

    // 所有问题都已回答后，恢复 streaming 状态
    if (arr.length === 0) {
      streamingSessions.value.add(sid)
    }
  }

  function clearMessages() {
    const sid = currentSessionId.value
    if (!sid) return
    messagesMap.value.delete(sid)
    assistantIdMap.delete(sid)
    // 触发响应式更新
    messagesMap.value = new Map(messagesMap.value)
  }

  /** 中断当前会话的 LLM 生成（不删除已有上下文，仅停止当前轮次的流式输出） */
  function interrupt() {
    const sid = currentSessionId.value
    if (!sid) return
    send({ action: 'interrupt', session_id: sid })
    // 立即更新前端状态，不等后端确认
    streamingSessions.value.delete(sid)
    // 结束当前 assistant 消息的 thinking 状态，标记未完成的工具调用为 interrupted
    const msgs = getMessagesForSession(sid)
    const last = msgs[msgs.length - 1]
    if (last && last.role === 'assistant') {
      last.isThinking = false
      let hasContent = false
      for (const block of last.blocks) {
        if (block.type === 'text' && block.content.trim()) {
          hasContent = true
        }
        // 将所有 running 状态的工具调用标记为 interrupted
        if (block.type === 'tool_call' && block.toolCall.status === 'running') {
          block.toolCall.status = 'interrupted'
          block.toolCall.result = block.toolCall.result || '{"interrupted": true, "message": "Tool execution was interrupted by the user."}'
        }
      }
      // 仅当 LLM 还没来得及输出任何内容时，添加中断占位提示
      if (!hasContent) {
        last.blocks.push({ type: 'text', content: '*(已停止)*' })
      }
    }
    setAssistantId(sid, null)
  }

  async function deleteSession(sessionId: string) {
    try {
      await api.delete(`/agent/sessions/${sessionId}`)
      // 从列表中移除
      sessions.value = sessions.value.filter(s => s.id !== sessionId)
      // 清理缓存
      messagesMap.value.delete(sessionId)
      assistantIdMap.delete(sessionId)
      pendingQuestionMap.value.delete(sessionId)
      streamingSessions.value.delete(sessionId)
      messagesMap.value = new Map(messagesMap.value)
      // 如果删除的是当前会话，清空引用
      if (currentSessionId.value === sessionId) {
        currentSessionId.value = null
        sessionRestoring.value = false
        if (restoreTimer) {
          clearTimeout(restoreTimer)
          restoreTimer = null
        }
        localStorage.removeItem('agent_current_session')
      }
    } catch (e) {
      console.error('Failed to delete session:', e)
      throw e
    }
  }

  async function renameSession(sessionId: string, title: string) {
    try {
      await api.put(`/agent/sessions/${sessionId}`, { title })
      const session = sessions.value.find(s => s.id === sessionId)
      if (session) {
        session.title = title
      }
    } catch (e) {
      console.error('Failed to rename session:', e)
      throw e
    }
  }

  /** 切换当前会话的 plan mode，返回是否成功切换 */
  function togglePlanMode(): boolean {
    const sid = currentSessionId.value
    if (!sid) {
      // 无会话时，切换临时状态
      pendingPlanMode.value = !pendingPlanMode.value
      return true
    }
    send({ action: 'toggle_plan_mode', session_id: sid })
    return true
  }

  return {
    messages,
    streaming,
    sessions,
    currentSessionId,
    pendingQuestion,
    sessionCreating,
    sessionRestoring,
    planMode,
    isPlanMode,
    togglePlanMode,
    connected,
    connect,
    disconnect,
    sendMessage,
    createNewSession,
    switchSession,
    loadSessions,
    answerQuestion,
    clearMessages,
    interrupt,
    deleteSession,
    renameSession,
    cronEvents,
  }
}


/** 检测工具结果内容是否为错误（用于历史记录恢复） */
function _isToolResultError(content: string): boolean {
  if (!content) return false
  try {
    const parsed = JSON.parse(content)
    return parsed && typeof parsed === 'object' && 'error' in parsed
  } catch {
    return false
  }
}


