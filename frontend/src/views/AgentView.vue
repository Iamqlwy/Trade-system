<template>
  <div class="agent-page">
    <!-- 无权限提示 -->
    <div v-if="!authStore.canUseAgent" class="no-permission-wrapper">
      <el-empty description="您没有 Agent 使用权限，请联系管理员开通">
        <template #image>
          <el-icon :size="80" color="#909399"><Lock /></el-icon>
        </template>
      </el-empty>
    </div>
    <template v-else>
    <!-- 左侧：会话列表 -->
    <aside class="sidebar">
      <!-- Tab 切换 -->
      <div class="sidebar-tabs">
        <button
          :class="['tab-btn', { active: activeTab === 'chat' }]"
          @click="navigateToTab('chat')"
        >
          <span class="tab-icon">
            <el-icon :size="18"><ChatDotRound /></el-icon>
          </span>
          <span class="tab-label">对话</span>
        </button>
        <button
          :class="['tab-btn', { active: activeTab === 'cron' }]"
          @click="navigateToTab('cron')"
        >
          <span class="tab-icon">
            <el-icon :size="18"><Clock /></el-icon>
          </span>
          <span class="tab-label">定时任务</span>
        </button>
      </div>
      <!-- 对话视图 -->
      <template v-if="activeTab === 'chat'">
      <div class="sidebar-header">
        <h3>对话</h3>
        <button class="new-chat-btn" @click="handleNewChat" title="新建对话">
          <el-icon><Plus /></el-icon>
        </button>
      </div>
      <div class="session-list">
        <div
          v-for="session in chat.sessions.value"
          :key="session.id"
          :class="['session-item', { active: session.id === chat.currentSessionId.value }]"
          @click="handleSwitchSession(session.id)"
        >
          <el-icon class="session-icon"><ChatDotRound /></el-icon>
          <!-- 重命名编辑模式 -->
          <div v-if="renamingSessionId === session.id" class="rename-row" @click.stop>
            <input
              v-model="renameInput"
              class="rename-input"
              maxlength="200"
              @keydown.enter="confirmRename"
              @keydown.escape="cancelRename"
            />
            <button class="rename-confirm-btn" @click="confirmRename" title="确认">
              <el-icon><Check /></el-icon>
            </button>
            <button class="rename-cancel-btn" @click="cancelRename" title="取消">
              <el-icon><Close /></el-icon>
            </button>
          </div>
          <!-- 正常显示模式 -->
          <template v-else>
            <div class="session-info">
              <div class="session-title-row">
                <span v-if="chat.isPlanMode(session.id)" class="session-plan-dot" title="计划模式"></span>
                <span class="session-title">{{ session.title || '新对话' }}</span>
              </div>
              <span class="session-meta">{{ session.summary || '' }}</span>
            </div>
            <div class="session-menu" @click.stop>
              <button class="menu-trigger" title="更多操作">
                <el-icon><MoreFilled /></el-icon>
              </button>
              <div class="menu-dropdown">
                <button class="menu-item" @click="startRename(session.id)">
                  <el-icon><EditPen /></el-icon>
                  <span>重命名</span>
                </button>
                <button class="menu-item danger" @click="handleDeleteSession(session.id)">
                  <el-icon><Delete /></el-icon>
                  <span>删除</span>
                </button>
              </div>
            </div>
          </template>

        </div>
        <div v-if="chat.sessions.value.length === 0" class="no-sessions">
          <span>暂无对话</span>
        </div>
      </div>
      </template>
      <!-- 定时任务视图 -->
      <template v-if="activeTab === 'cron'">
        <CronPanel ref="cronPanelRef" @job-select="handleCronJobSelect" />
      </template>
    </aside>

    <!-- 右侧：主区域 -->
    <main class="chat-main" :class="{ 'is-plan-mode': chat.planMode.value }">
      <!-- ── 对话模式 ── -->
      <div v-if="activeTab === 'chat' || !cronSelectedJob" class="chat-inner">

      <!-- ── Plan Mode 顶部状态横幅 ── -->
      <Transition name="plan-banner">
        <div v-if="chat.planMode.value" class="plan-mode-banner">
          <div class="plan-banner-left">
            <span class="plan-banner-icon">
              <el-icon :size="16"><Aim /></el-icon>
            </span>
            <div class="plan-banner-text">
              <span class="plan-banner-title">计划模式已启用</span>
              <span class="plan-banner-desc">AI 将进行只读分析，不会执行交易操作</span>
            </div>
          </div>
          <button class="plan-banner-close" @click="chat.togglePlanMode()" title="退出计划模式 (Shift+Tab)">
            <el-icon :size="14"><Close /></el-icon>
            <span>退出</span>
          </button>
        </div>
      </Transition>

      <!-- 空状态：居中显示输入框 -->
      <div v-if="chat.messages.value.length === 0 && !chat.streaming.value && !chat.sessionCreating.value && !chat.sessionRestoring.value" class="empty-state">
        <div class="empty-icon">
          <el-icon :size="48"><ChatLineSquare /></el-icon>
        </div>
        <h2>AI 助手</h2>
        <p class="empty-desc">有什么可以帮你的？</p>
        <div class="empty-input">
          <div class="input-wrapper">
            <!-- 图片预览条 -->
            <div v-if="pendingImages.length > 0" class="pending-images-preview">
              <div v-for="(img, idx) in pendingImages" :key="idx" class="pending-image-thumb">
                <img :src="img.previewUrl" :alt="img.name" />
                <span v-if="img.uploading" class="upload-overlay">上传中...</span>
                <span v-if="img.error && !img.uploading" class="upload-overlay upload-error">
                  <span class="error-text">上传失败</span>
                  <button class="retry-btn" @click.stop="retryPendingImage(idx)" title="重试">
                    <el-icon :size="12"><Refresh /></el-icon>
                  </button>
                </span>
                <button class="remove-image-btn" @click="removePendingImage(idx)">
                  <el-icon :size="14"><Close /></el-icon>
                </button>
              </div>
            </div>
            <el-input
              v-model="inputText"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 6 }"
              :placeholder="chat.planMode.value ? '计划模式：输入分析指令...' : '输入你的问题... (Enter 发送, Shift+Enter 换行)'"
              class="chat-input"
              @keydown.enter.exact.prevent="handleSend"
              @drop="handleDrop"
              @dragover="handleDragOver"
            />
            <button
              class="attach-btn"
              :disabled="chat.streaming.value || chat.sessionCreating.value || pendingImages.length >= _MAX_IMAGES_PER_MESSAGE"
              @click="triggerFileSelect"
              title="上传图片"
            >
              <el-icon><PictureFilled /></el-icon>
            </button>
            <button
              class="send-btn"
              :disabled="!hasSendableContent || imagesUploading || chat.streaming.value || chat.sessionCreating.value"
              @click="handleSend"
            >
              <el-icon><Promotion /></el-icon>
            </button>
            <input
              ref="fileInputRef"
              type="file"
              accept="image/png,image/jpeg,image/gif,image/webp,image/bmp"
              multiple
              style="display: none"
              @change="handleImageSelect"
            />
          </div>
          <div class="quick-actions">
            <button class="quick-btn" @click="quickSend('/help')">/help</button>
            <button class="quick-btn" @click="quickSend('/tools')">/tools</button>
            <button class="quick-btn" @click="quickSend('/skills')">/skills</button>
          </div>
        </div>
      </div>

      <!-- 会话恢复中：显示加载状态 -->
      <div v-else-if="chat.sessionRestoring.value && chat.messages.value.length === 0" class="empty-state restoring-state">
        <div class="empty-icon">
          <el-icon :size="48" class="is-loading"><Loading /></el-icon>
        </div>
        <h2>正在加载会话...</h2>
      </div>

      <!-- 有消息时的对话流 -->
      <template v-else>
        <div ref="chatScrollRef" class="chat-messages" @click="handleImageClick">
          <div
            v-for="msg in chat.messages.value"
            :key="msg.id"
            :class="['message', msg.role]"
          >
            <!-- 头像 -->
            <div class="message-avatar">
              <div v-if="msg.role === 'user'" class="avatar user-avatar">
                <el-icon><User /></el-icon>
              </div>
              <div v-else class="avatar ai-avatar">
                <el-icon><Monitor /></el-icon>
              </div>
            </div>

            <!-- 内容区域 -->
            <div class="message-body">
              <!-- 思考中 -->
              <div v-if="msg.isThinking && msg.blocks.length === 0" class="thinking-dots">
                <span></span><span></span><span></span>
              </div>

              <!-- Assistant 消息：思考过程 + 最终回复 -->
              <template v-if="msg.role === 'assistant'">
                <!-- 思考过程（可折叠） -->
                <div
                  v-if="hasIntermediateSteps(msg)"
                  class="thinking-process"
                  :class="{
                    expanded: expandedSteps.has(msg.id),
                    'thinking-active': msg.isThinking,
                  }"
                >
                  <div class="thinking-header" @click="toggleSteps(msg.id)">
                    <el-icon class="thinking-icon" :class="{ rotated: expandedSteps.has(msg.id) }">
                      <ArrowRight />
                    </el-icon>
                    <span class="thinking-title">
                      思考过程 ({{ countIntermediateSteps(msg) }} 个步骤)
                    </span>
                    <span v-if="expandedSteps.has(msg.id)" class="thinking-hint">点击收起 · UIO 全部折叠</span>
                    <span v-else class="thinking-hint">点击展开 · UIO 全部展开</span>
                  </div>
                  <div v-show="expandedSteps.has(msg.id)" class="thinking-content">
                    <!-- 中间步骤（按原始顺序：文本 / 工具调用 / 子 Agent 交错显示） -->
                    <div
                      v-for="(block, idx) in getIntermediateBlocks(msg)"
                      :key="`step-${idx}`"
                    >
                      <!-- 中间文本（思考过程中的文本输出，空内容跳过） -->
                      <div
                        v-if="block.type === 'text' && (block as TextBlock).content.trim()"
                        class="step-item text-step"
                      >
                        <div class="step-header">
                          <el-icon class="tool-icon"><Promotion /></el-icon>
                          <span class="step-name text-step-label">中间输出</span>
                        </div>
                        <div class="step-details">
                          <div class="intermediate-text" v-html="renderMarkdown((block as TextBlock).content)"></div>
                        </div>
                      </div>
                      <!-- 工具调用 -->
                      <div
                        v-else-if="block.type === 'tool_call'"
                        class="step-item tool-step"
                        :class="'status-' + (block as ToolCallBlock).toolCall.status"
                      >
                        <div class="step-header">
                          <el-icon class="tool-icon"><Operation /></el-icon>
                          <span class="step-name">{{ (block as ToolCallBlock).toolCall.name }}</span>
                          <span class="step-status" :class="(block as ToolCallBlock).toolCall.status">
                            {{ getStatusText((block as ToolCallBlock).toolCall.status) }}
                          </span>
                        </div>
                        <div class="step-details">
                          <div class="detail-section">
                            <span class="detail-label">参数</span>
                            <pre class="detail-content">{{ formatArgs((block as ToolCallBlock).toolCall.args) }}</pre>
                          </div>
                          <div v-if="(block as ToolCallBlock).toolCall.result" class="detail-section">
                            <span class="detail-label">结果</span>
                            <pre class="detail-content">{{ (block as ToolCallBlock).toolCall.result }}</pre>
                          </div>
                        </div>
                      </div>
                      <!-- 子 Agent -->
                      <div
                        v-else-if="block.type === 'sub_agent'"
                        class="step-item sub-agent-step"
                        @click="showSubAgentDetail((block as SubAgentBlock).subAgent)"
                      >
                        <div class="step-header">
                          <el-icon class="sub-agent-icon"><Cpu /></el-icon>
                          <span class="step-name">{{ (block as SubAgentBlock).subAgent.label }}</span>
                          <span class="step-status" :class="(block as SubAgentBlock).subAgent.status">
                            {{ getStatusText((block as SubAgentBlock).subAgent.status) }}
                          </span>
                          <el-icon class="expand-hint"><ArrowRight /></el-icon>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                <!-- 最终回复（文本内容） — 只展示最后一个 tool_call/sub_agent 之后的文本 -->
                <div
                  v-for="(block, idx) in getFinalTextBlocks(msg)"
                  :key="`final-${idx}`"
                  class="final-response"
                  v-html="renderMarkdown((block as TextBlock).content)"
                ></div>
              </template>

              <!-- User 消息 -->
              <template v-else>
                <template
                  v-for="(group, gIdx) in getUserBlockGroups(msg)"
                  :key="gIdx"
                >
                  <div
                    v-if="group.kind === 'text'"
                    class="message-content user-content"
                    v-html="renderMarkdown((group.block as TextBlock).content)"
                  ></div>
                  <div v-else class="user-images-row">
                    <img
                      v-for="(img, iIdx) in group.blocks"
                      :key="iIdx"
                      :src="img.url"
                      :alt="img.name || '图片'"
                      class="msg-image"
                      @click.stop="lightboxSrc = img.url"
                    />
                  </div>
                </template>
              </template>
            </div>
          </div>

          <!-- 流式指示器 -->
          <div v-if="chat.streaming.value && !hasAssistantContent" class="typing-indicator">
            <span class="dot"></span><span class="dot"></span><span class="dot"></span>
          </div>
        </div>

        <!-- 子 Agent 详情抽屉 -->
        <div
          v-if="selectedSubAgent"
          class="sub-agent-drawer-overlay"
          @click="closeSubAgentDetail"
        >
          <div class="sub-agent-drawer" @click.stop>
            <div class="drawer-header">
              <div class="drawer-title">
                <el-icon class="sub-agent-icon"><Cpu /></el-icon>
                <span>{{ selectedSubAgent.label }}</span>
              </div>
              <button class="drawer-close" @click="closeSubAgentDetail">
                <el-icon><Close /></el-icon>
              </button>
            </div>
            <div class="drawer-body">
              <div class="drawer-section">
                <div class="section-title">任务描述</div>
                <div class="section-content">{{ selectedSubAgent.task_description }}</div>
              </div>
              <div class="drawer-section">
                <div class="section-title">类型</div>
                <div class="section-content">{{ getSubAgentTypeName(selectedSubAgent.type) }}</div>
              </div>
              <div class="drawer-section">
                <div class="section-title">状态</div>
                <div class="section-content">
                  <span class="status-badge" :class="selectedSubAgent.status">
                    {{ getStatusText(selectedSubAgent.status) }}
                  </span>
                </div>
              </div>
              <div v-if="selectedSubAgent.toolCalls && selectedSubAgent.toolCalls.length > 0" class="drawer-section">
                <div class="section-title">执行步骤 ({{ selectedSubAgent.toolCalls.length }})</div>
                <div class="tool-call-list">
                  <div
                    v-for="(tc, idx) in selectedSubAgent.toolCalls"
                    :key="idx"
                    class="tool-call-item"
                    :class="'status-' + tc.status"
                  >
                    <div class="tool-call-header">
                      <el-icon class="tool-icon"><Operation /></el-icon>
                      <span class="tool-name">{{ tc.name }}</span>
                      <span class="step-status" :class="tc.status">
                        {{ getStatusText(tc.status) }}
                      </span>
                    </div>
                    <div class="tool-call-details">
                      <div class="detail-section">
                        <span class="detail-label">参数</span>
                        <pre class="detail-content">{{ formatArgs(tc.args) }}</pre>
                      </div>
                      <div v-if="tc.result" class="detail-section">
                        <span class="detail-label">结果</span>
                        <pre class="detail-content">{{ tc.result }}</pre>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
              <div v-if="selectedSubAgent.output" class="drawer-section">
                <div class="section-title">输出结果</div>
                <div class="section-content output-content">{{ selectedSubAgent.output }}</div>
              </div>
            </div>
          </div>
        </div>

        <!-- AskUserQuestion 内联卡片（支持多问题同时显示） -->
        <div
          v-for="(pq, pqIdx) in chat.pendingQuestion.value"
          :key="pq.requestId || pqIdx"
          class="ask-card"
        >
          <div class="ask-header">
            <el-icon class="ask-icon"><QuestionFilled /></el-icon>
            <span class="ask-title">{{ pq.header }}</span>
            <span v-if="chat.pendingQuestion.value.length > 1" class="ask-index">
              {{ pqIdx + 1 }}/{{ chat.pendingQuestion.value.length }}
            </span>
          </div>
          <p class="ask-question">{{ pq.question }}</p>
          <div v-if="pq.options.length" class="ask-options">
            <button
              v-for="opt in pq.options"
              :key="opt"
              class="ask-option-btn"
              @click="handleAnswerQuestion(opt, pq.requestId)"
            >
              {{ opt }}
            </button>
          </div>
          <div class="ask-input-row">
            <el-input
              v-model="askAnswerTexts[pqIdx]"
              placeholder="输入回答..."
              @keydown.enter.prevent="handleAnswerQuestion(askAnswerTexts[pqIdx], pq.requestId)"
              class="ask-input"
            />
            <button
              class="send-btn ask-send-btn"
              :disabled="!(askAnswerTexts[pqIdx] && askAnswerTexts[pqIdx].trim())"
              @click="handleAnswerQuestion(askAnswerTexts[pqIdx], pq.requestId)"
            >
              <el-icon><Promotion /></el-icon>
            </button>
          </div>
        </div>

        <!-- 输入区域 -->
        <div class="chat-input-area">
          <div class="input-wrapper">
            <!-- 图片预览条 -->
            <div v-if="pendingImages.length > 0" class="pending-images-preview">
              <div v-for="(img, idx) in pendingImages" :key="idx" class="pending-image-thumb">
                <img :src="img.previewUrl" :alt="img.name" />
                <span v-if="img.uploading" class="upload-overlay">上传中...</span>
                <span v-if="img.error && !img.uploading" class="upload-overlay upload-error">
                  <span class="error-text">上传失败</span>
                  <button class="retry-btn" @click.stop="retryPendingImage(idx)" title="重试">
                    <el-icon :size="12"><Refresh /></el-icon>
                  </button>
                </span>
                <button class="remove-image-btn" @click="removePendingImage(idx)">
                  <el-icon :size="14"><Close /></el-icon>
                </button>
              </div>
            </div>
            <el-input
              v-model="inputText"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 6 }"
              :placeholder="chat.planMode.value ? '计划模式：输入分析指令...' : '输入消息...'"
              class="chat-input"
              @keydown.enter.exact.prevent="handleSend"
              @drop="handleDrop"
              @dragover="handleDragOver"
            />
            <button
              class="attach-btn"
              :disabled="chat.streaming.value || chat.sessionCreating.value || pendingImages.length >= _MAX_IMAGES_PER_MESSAGE"
              @click="triggerFileSelect"
              title="上传图片"
            >
              <el-icon><PictureFilled /></el-icon>
            </button>
            <button
              class="send-btn"
              :disabled="!hasSendableContent || imagesUploading || chat.streaming.value || chat.sessionCreating.value"
              @click="handleSend"
            >
              <el-icon><Promotion /></el-icon>
            </button>
            <input
              ref="fileInputRef"
              type="file"
              accept="image/png,image/jpeg,image/gif,image/webp,image/bmp"
              multiple
              style="display: none"
              @change="handleImageSelect"
            />
          </div>
        </div>
      </template>
      </div><!-- /chat-inner -->

      <!-- ── 定时任务详情模式 ── -->
      <div v-else class="cron-detail-main">
        <div class="cron-detail-header">
          <button class="cron-back-btn" @click="cronBackToList">
            <el-icon><ArrowLeft /></el-icon>
            <span>返回列表</span>
          </button>
          <div class="cron-header-actions">
            <span v-if="cronSelectedJob.next_run_at" class="cron-next-run">
              下次: {{ cronSelectedJob.next_run_at }}
            </span>
          </div>
        </div>

        <div class="cron-detail-body">
          <!-- 运行历史列表 -->
          <aside class="cron-runs-sidebar">
            <div class="cron-runs-header">
              <span>运行历史 ({{ cronRuns.length }})</span>
              <button class="cron-refresh-btn" @click="cronSelectedJob && handleCronJobSelect(cronSelectedJob)" title="刷新">
                <el-icon :size="13"><Refresh /></el-icon>
              </button>
            </div>
            <div v-if="cronRuns.length === 0" class="cron-no-runs">暂无运行记录</div>
            <div
              v-for="run in cronRuns"
              :key="run.id"
              :class="['cron-run-item', { selected: cronSelectedRunId === run.id }]"
              @click="handleCronRunSelect(run)"
            >
              <span class="cron-run-dot" :class="run.status" />
              <div class="cron-run-info">
                <span class="cron-run-time">{{ new Date(run.started_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' }) }}</span>
                <span class="cron-run-status" :class="run.status">
                  {{ run.status === 'completed' ? '完成' : run.status === 'failed' ? '失败' : '运行中' }}
                </span>
              </div>
            </div>
          </aside>

          <!-- 对话区域：复用 Agent 消息组件 + 内联输入框 -->
          <main class="cron-conversation">
            <!-- 未选择运行 -->
            <div v-if="!cronSelectedRunId" class="cron-empty-hint">
              <el-icon :size="32"><Clock /></el-icon>
              <p>选择运行记录查看对话上下文</p>
            </div>

            <!-- 正在创建会话 -->
            <div v-else-if="cronSessionLoading" class="cron-empty-hint">
              <el-icon class="is-loading" :size="28"><Loading /></el-icon>
              <p>加载对话上下文...</p>
            </div>

            <!-- 会话已加载：显示消息 + 输入框 -->
            <template v-else>
              <div ref="cronScrollRef" class="cron-messages" @click="handleImageClick">
                <div v-if="chat.messages.value.length === 0" class="cron-empty-hint">
                  <p>此运行没有记录对话上下文</p>
                </div>

                <div
                  v-for="msg in chat.messages.value"
                  :key="msg.id"
                  :class="['message', msg.role]"
                >
                  <!-- 头像 -->
                  <div class="message-avatar">
                    <div v-if="msg.role === 'user'" class="avatar user-avatar">
                      <el-icon><User /></el-icon>
                    </div>
                    <div v-else class="avatar ai-avatar">
                      <el-icon><Monitor /></el-icon>
                    </div>
                  </div>

                  <!-- 内容区域 -->
                  <div class="message-body">
                    <!-- 思考中 -->
                    <div v-if="msg.isThinking && msg.blocks.length === 0" class="thinking-dots">
                      <span></span><span></span><span></span>
                    </div>

                    <template v-if="msg.role === 'assistant'">
                      <!-- 思考过程（可折叠） -->
                      <div
                        v-if="hasIntermediateSteps(msg)"
                        class="thinking-process"
                        :class="{
                          expanded: cronExpandedSteps.has(msg.id),
                          'thinking-active': msg.isThinking,
                        }"
                      >
                        <div class="thinking-header" @click="cronToggleSteps(msg.id)">
                          <el-icon class="thinking-icon" :class="{ rotated: cronExpandedSteps.has(msg.id) }">
                            <ArrowRight />
                          </el-icon>
                          <span class="thinking-title">
                            思考过程 ({{ countIntermediateSteps(msg) }} 个步骤)
                          </span>
                          <span v-if="cronExpandedSteps.has(msg.id)" class="thinking-hint">点击收起 · UIO 全部折叠</span>
                          <span v-else class="thinking-hint">点击展开 · UIO 全部展开</span>
                        </div>
                        <div v-show="cronExpandedSteps.has(msg.id)" class="thinking-content">
                          <div
                            v-for="(block, idx) in getIntermediateBlocks(msg)"
                            :key="`step-${idx}`"
                          >
                            <div
                              v-if="block.type === 'text' && (block as TextBlock).content.trim()"
                              class="step-item text-step"
                            >
                              <div class="step-header">
                                <el-icon class="tool-icon"><Promotion /></el-icon>
                                <span class="step-name text-step-label">中间输出</span>
                              </div>
                              <div class="step-details">
                                <div class="intermediate-text" v-html="renderMarkdown((block as TextBlock).content)"></div>
                              </div>
                            </div>
                            <div
                              v-else-if="block.type === 'tool_call'"
                              class="step-item tool-step"
                              :class="'status-' + (block as ToolCallBlock).toolCall.status"
                            >
                              <div class="step-header">
                                <el-icon class="tool-icon"><Operation /></el-icon>
                                <span class="step-name">{{ (block as ToolCallBlock).toolCall.name }}</span>
                                <span class="step-status" :class="(block as ToolCallBlock).toolCall.status">
                                  {{ getStatusText((block as ToolCallBlock).toolCall.status) }}
                                </span>
                              </div>
                              <div class="step-details">
                                <div class="detail-section">
                                  <span class="detail-label">参数</span>
                                  <pre class="detail-content">{{ formatArgs((block as ToolCallBlock).toolCall.args) }}</pre>
                                </div>
                                <div v-if="(block as ToolCallBlock).toolCall.result" class="detail-section">
                                  <span class="detail-label">结果</span>
                                  <pre class="detail-content">{{ (block as ToolCallBlock).toolCall.result }}</pre>
                                </div>
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>

                      <!-- 最终回复 -->
                      <div
                        v-for="(block, idx) in getFinalTextBlocks(msg)"
                        :key="`final-${idx}`"
                        class="final-response"
                        v-html="renderMarkdown((block as TextBlock).content)"
                      ></div>
                    </template>

                    <!-- User 消息 -->
                    <template v-else>
                      <template
                        v-for="(group, gIdx) in getUserBlockGroups(msg)"
                        :key="gIdx"
                      >
                        <div
                          v-if="group.kind === 'text'"
                          class="message-content user-content"
                          v-html="renderMarkdown((group.block as TextBlock).content)"
                        ></div>
                        <div v-else class="user-images-row">
                          <img
                            v-for="(img, iIdx) in group.blocks"
                            :key="iIdx"
                            :src="img.url"
                            :alt="img.name || '图片'"
                            class="msg-image"
                            @click.stop="handleImageClick({ target: { src: img.url } } as unknown as MouseEvent)"
                          />
                        </div>
                      </template>
                    </template>
                  </div>
                </div>

                <!-- 流式指示器 -->
                <div v-if="chat.streaming.value" class="typing-indicator">
                  <span class="dot"></span><span class="dot"></span><span class="dot"></span>
                </div>
              </div>

              <!-- 内联输入框 -->
              <div class="cron-input-area">
                <div class="input-wrapper">
                  <el-input
                    v-model="cronInputText"
                    type="textarea"
                    :autosize="{ minRows: 1, maxRows: 4 }"
                    placeholder="输入消息继续对话..."
                    class="chat-input"
                    @keydown.enter.exact.prevent="sendCronMessage"
                  />
                  <button
                    class="send-btn"
                    :disabled="!cronInputText.trim() || chat.streaming.value"
                    @click="sendCronMessage"
                  >
                    <el-icon><Promotion /></el-icon>
                  </button>
                </div>
              </div>
            </template>
          </main>
        </div>
      </div>
    </main>

    <!-- 图片灯箱 -->
    <div v-if="lightboxSrc" class="image-lightbox" @click="closeLightbox">
      <div class="lightbox-backdrop"></div>
      <div class="lightbox-container">
        <button class="lightbox-close" @click="closeLightbox">
          <el-icon><Close /></el-icon>
        </button>
        <img :src="lightboxSrc" class="lightbox-image" @click.stop />
      </div>
    </div>
    </template>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'AgentView' })

import { ref, reactive, computed, nextTick, onMounted, onUnmounted, onActivated, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAgentChat } from '@/composables/useAgentChat'
import api from '@/api'
import CronPanel from '@/components/agent/CronPanel.vue'
import type { AgentMessage, MessageBlock, TextBlock, ImageBlock, ToolCallBlock, SubAgentBlock, SubAgentInfo } from '@/composables/useAgentChat'
import {
  Plus, ChatDotRound, ChatLineSquare, Promotion, Clock,
  User, Monitor, QuestionFilled, ArrowRight, ArrowLeft,
  Operation, Cpu, Close, MoreFilled, Delete, EditPen, Check,
  VideoPlay, Fold, Loading, Refresh, PictureFilled,
} from '@element-plus/icons-vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { showApiError } from '@/utils/notify'
import { marked } from 'marked'
import hljs from 'highlight.js'
import 'highlight.js/styles/github-dark.css'
import { sanitizeHtml } from '@/utils/sanitize'
import { cleanInput } from '@/utils/validation'
import { cronApi } from '@/api/cron'
import type { CronJob, CronJobRun } from '@/types/cron'
import { useAuthStore } from '@/stores/auth'
import { Lock } from '@element-plus/icons-vue'

// 配置 marked：使用 highlight.js 进行代码高亮
marked.setOptions({
  breaks: true,
})

const renderer = new marked.Renderer()
renderer.code = function ({ text, lang }: { text: string; lang?: string }) {
  const language = lang && hljs.getLanguage(lang) ? lang : 'plaintext'
  const highlighted = hljs.highlight(text, { language }).value
  return `<pre><code class="hljs language-${language}">${highlighted}</code></pre>`
}
marked.use({ renderer })

// Memoize markdown rendering — critical for streaming performance
const mdCache = new Map<string, string>()

/**
 * 预处理：将 AI 用代码围栏包裹的图片 Markdown 解包为正常图片语法。
 *
 * AI 经常把 `![alt](path)` 或 ```![alt](path)``` 作为代码返回，
 * 导致 marked 将其渲染为 <code> 文本而非 <img>。
 * 此函数在 marked 解析前把这些模式还原为可渲染的 Markdown。
 */
function unwrapCodeFencedImages(input: string): string {
  let result = input

  // 1. 三反引号围栏中仅含图片语法 → 去掉围栏
  //    ```\n![alt](path)\n```  →  ![alt](path)
  result = result.replace(
    /```[a-z]*\n(!\[[^\]]*\]\([^)]+\))\n```/g,
    '$1',
  )

  // 2. 单反引号包裹的图片语法 → 去掉反引号
  //    文本中 `![alt](path)` → 文本中 ![alt](path)
  result = result.replace(
    /`(!\[[^\]]*\]\([^)]+\))`/g,
    '$1',
  )

  return result
}

function renderMarkdown(content: string): string {
  if (!content) return ''
  const sid = chat.currentSessionId.value
  // 缓存键包含 session ID，避免不同会话间图片路径串用
  const cacheKey = sid ? `${sid}:${content}` : content
  const cached = mdCache.get(cacheKey)
  if (cached) return cached
  try {
    // 先解包代码围栏中的图片语法，再交给 marked 解析
    const preprocessed = unwrapCodeFencedImages(content)
    const parsed = marked.parse(preprocessed) as string
    // 将图片 src 改写为后端工作区直连接口 /api/agent/workspace/{sid}/{path}。
    // 后端鉴权后从 agent 工作区返回文件。
    // <img> 标签无法携带 Authorization header，token 通过 ?token= 查询参数传递。
    //
    // 匹配格式：
    //   1. /workspace/{session_id}/xxx.png  → /api/agent/workspace/{sid}/xxx.png?token=...
    //   2. files/xxx 或 ./files/xxx         → /api/agent/workspace/{sid}/xxx?token=...
    //   3. 裸图片文件名 (gradient.png)      → /api/agent/workspace/{sid}/xxx?token=...
    const IMAGE_EXT = /\.(png|jpg|jpeg|gif|svg|webp|bmp|ico)(\?[^"']*)?$/i
    const authToken = localStorage.getItem('quant_token') || ''
    const tokenSuffix = authToken ? '?token=' + encodeURIComponent(authToken) : ''
    let result: string
    if (sid) {
      result = parsed.replace(
        /src="([^"]+)"/g,
        (m: string, src: string) => {
          // 已经是外部绝对 URL 或 data URI — 跳过
          if (/^https?:\/\//.test(src) || src.startsWith('data:')) return m
          // 已经是工作区 API 路径 — 跳过
          if (src.startsWith('/api/agent/workspace/')) return m

          // 格式 1: /workspace/{session_id}/path — 取 session_id 后的相对路径
          const workspaceMatch = src.match(/^\/workspace\/[^/]+\/(.+)$/)
          if (workspaceMatch) {
            return 'src="/api/agent/workspace/' + sid + '/' + workspaceMatch[1] + tokenSuffix + '"'
          }

          // 去掉 ./ 前缀
          const clean = src.replace(/^\.\//, '')

          // 格式 2: files/xxx — 旧格式兼容
          const filesMatch = clean.match(/^files\/(.+)$/)
          if (filesMatch) {
            return 'src="/api/agent/workspace/' + sid + '/' + filesMatch[1] + tokenSuffix + '"'
          }

          // 格式 3: 裸图片文件名
          if (IMAGE_EXT.test(clean)) {
            return 'src="/api/agent/workspace/' + sid + '/' + clean + tokenSuffix + '"'
          }

          return m
        }
      )
    } else {
      result = parsed
    }
    // XSS 防护：净化最终 HTML（移除危险标签/属性，保留 Markdown 渲染所需的安全标签）
    result = sanitizeHtml(result)
    mdCache.set(cacheKey, result)
    return result
  } catch {
    return content
  }
}

const chat = useAgentChat()
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const activeTab = ref<'chat' | 'cron'>('chat')
const cronPanelRef = ref<InstanceType<typeof CronPanel> | null>(null)
let dataLoaded = false
const inputText = ref('')
const askAnswerTexts = reactive<string[]>([])
const chatScrollRef = ref<HTMLElement>()
const expandedSteps = ref(new Set<string>())  // 存储展开的中间步骤
const selectedSubAgent = ref<SubAgentInfo | null>(null)  // 选中的子 agent 详情
const lightboxSrc = ref<string | null>(null)  // 图片灯箱

// ── 图片上传状态 ──
interface PendingImage {
  file: File
  previewUrl: string     // 本地预览 URL (blob:)
  ossUrl?: string        // 上传成功后的 OSS URL
  name: string
  uploading: boolean
  error?: string
}
const pendingImages = ref<PendingImage[]>([])
const fileInputRef = ref<HTMLInputElement | null>(null)

// ── Cron detail state ──
const cronSelectedJob = ref<CronJob | null>(null)
const cronRuns = ref<CronJobRun[]>([])
const cronSelectedRunId = ref<string | null>(null)
const cronExpandedSteps = ref(new Set<string>())  // cron 消息的思考展开状态
const cronAgentSessionId = ref<string | null>(null)  // 从 cron 运行创建的 Agent 会话 ID
const cronSessionLoading = ref(false)  // 正在创建/加载会话
const cronInputText = ref('')  // cron 视图的输入框
const cronScrollRef = ref<HTMLElement>()  // cron 消息区域滚动容器
const lastChatSessionId = ref<string | null>(null)  // 切到 cron 前记住的 chat 会话

// 从监控中心跳转时，立即预填输入内容（同步设置，不等 WebSocket）
const _initialMsg = route.query.initialMessage as string | undefined
console.log('[AgentView][setup] route=%s, initialMessage=%s, currentSessionId=%s',
  route.fullPath, _initialMsg, chat.currentSessionId.value)
if (_initialMsg) {
  console.log('[AgentView][setup] ✅ 设置 inputText + createNewSession')
  // URL 参数净化：去除控制字符，截断到合理长度
  inputText.value = cleanInput(_initialMsg, 5000)
  chat.createNewSession()
}

// 监听路由 query 变化（immediate 覆盖首次挂载，watcher 覆盖 keep-alive 重新激活）
watch(
  () => route.query.initialMessage,
  (msg) => {
    console.log('[AgentView][watch:initialMessage] msg=%s, route=%s, currentSessionId=%s',
      msg, route.fullPath, chat.currentSessionId.value)
    if (msg) {
      console.log('[AgentView][watch:initialMessage] ✅ createNewSession + set inputText')
      chat.createNewSession()
      // URL 参数净化
      inputText.value = cleanInput(msg as string, 5000)
      console.log('[AgentView][watch:initialMessage] router.replace → agent (清除 query)')
      router.replace({ name: 'agent' })
    }
  },
  { immediate: true },
)

const hasAssistantContent = computed(() => {
  const msgs = chat.messages.value
  const last = msgs[msgs.length - 1]
  return last?.role === 'assistant' && last.blocks.length > 0
})

const imagesUploading = computed(() => pendingImages.value.some(img => img.uploading))
const hasSendableContent = computed(() => {
  const hasText = inputText.value.trim().length > 0
  return hasText
})

// ============ 辅助函数 ============

function hasIntermediateSteps(msg: AgentMessage): boolean {
  return msg.blocks.some(b => b.type === 'tool_call' || b.type === 'sub_agent')
}

function countIntermediateSteps(msg: AgentMessage): number {
  return msg.blocks.filter(b => b.type === 'tool_call' || b.type === 'sub_agent').length
}

// 将用户消息的 blocks 分组：连续的图片合并到一组，文本单独一组
type UserBlockGroup = { kind: 'text'; block: TextBlock } | { kind: 'images'; blocks: ImageBlock[] }
function getUserBlockGroups(msg: AgentMessage): UserBlockGroup[] {
  const groups: UserBlockGroup[] = []
  for (const block of msg.blocks) {
    if (block.type === 'text') {
      groups.push({ kind: 'text', block: block as TextBlock })
    } else if (block.type === 'image') {
      const last = groups[groups.length - 1]
      if (last && last.kind === 'images') {
        last.blocks.push(block as ImageBlock)
      } else {
        groups.push({ kind: 'images', blocks: [block as ImageBlock] })
      }
    }
  }
  return groups
}

/**
 * 获取中间步骤块：最后一个 tool_call/sub_agent 之前的所有块（包括文本）
 * 保持原始顺序，用于在可折叠区域内按序展示
 */
function getIntermediateBlocks(msg: AgentMessage): MessageBlock[] {
  let lastStepIdx = -1
  for (let i = msg.blocks.length - 1; i >= 0; i--) {
    if (msg.blocks[i]?.type === 'tool_call' || msg.blocks[i]?.type === 'sub_agent') {
      lastStepIdx = i
      break
    }
  }
  if (lastStepIdx < 0) return []
  return msg.blocks.slice(0, lastStepIdx + 1)
}

/**
 * 获取最终输出文本块：最后一个 tool_call/sub_agent 之后的所有文本块
 * 如果消息没有任何 tool_call/sub_agent，则返回所有文本块
 */
function getFinalTextBlocks(msg: AgentMessage): TextBlock[] {
  let lastStepIdx = -1
  for (let i = msg.blocks.length - 1; i >= 0; i--) {
    if (msg.blocks[i]?.type === 'tool_call' || msg.blocks[i]?.type === 'sub_agent') {
      lastStepIdx = i
      break
    }
  }
  return msg.blocks.slice(lastStepIdx + 1).filter(b => b.type === 'text') as TextBlock[]
}

function formatArgs(args: string): string {
  try {
    const parsed = JSON.parse(args)
    return JSON.stringify(parsed, null, 2)
  } catch {
    return args
  }
}

function getStatusText(status: string): string {
  const statusMap: Record<string, string> = {
    'running': '执行中',
    'done': '已完成',
    'completed': '已完成',
    'error': '执行错误',
    'interrupted': '已中断',
  }
  return statusMap[status] || status
}

function getSubAgentTypeName(type: string): string {
  const typeMap: Record<string, string> = {
    'general-purpose': '通用助手',
    'explore': '代码探索',
    'plan': '方案规划',
    'researcher': '研究分析',
  }
  return typeMap[type] || type || '未知类型'
}

// ============ 子 Agent 详情抽屉 ============

function showSubAgentDetail(subAgent: SubAgentInfo) {
  selectedSubAgent.value = subAgent
}

function closeSubAgentDetail() {
  selectedSubAgent.value = null
}

// ============ 事件处理 ============

// ── ESC 双击中断 ──
// 第一次 ESC：提示"再按一次停止"；500ms 内第二次 ESC：触发中断
let _lastEscTime = 0
const ESC_DOUBLE_CLICK_MS = 500

function handleEscInterrupt(e: KeyboardEvent) {
  if (e.key !== 'Escape') return
  // 仅在 streaming 状态下响应
  if (!chat.streaming.value) return
  // 如果焦点在输入框内且输入框有内容，不拦截（让用户正常退出输入）
  const target = e.target as HTMLElement
  if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA')) return

  const now = Date.now()
  if (now - _lastEscTime < ESC_DOUBLE_CLICK_MS) {
    // 第二次 ESC — 真正中断
    _lastEscTime = 0
    chat.interrupt()
    ElMessage.info('已停止生成')
  } else {
    // 第一次 ESC — 提示
    _lastEscTime = now
    ElMessage.warning('再按一次 Esc 停止生成')
  }
}

function handleSend() {
  const text = inputText.value.trim()
  if (!text) {
    ElMessage.warning('请输入文字内容后再发送')
    return
  }
  // 如果有图片正在上传，等待完成
  const uploading = pendingImages.value.some(img => img.uploading)
  if (uploading) {
    ElMessage.info('图片正在上传中，请稍候...')
    return
  }
  // 收集上传完成的图片（排除失败的，最多 5 张）
  const uploadedImages = pendingImages.value
    .filter(img => img.ossUrl && !img.error)
    .map(img => ({ url: img.ossUrl!, name: img.name }))
    .slice(0, _MAX_IMAGES_PER_MESSAGE)
  const failedImages = pendingImages.value.filter(img => img.error)
  if (failedImages.length > 0) {
    ElMessage.error({
      message: `${failedImages.length} 张图片上传失败，将只发送成功的图片`,
      duration: 0,
      showClose: true,
    })
  }
  chat.sendMessage(text, uploadedImages.length > 0 ? uploadedImages : undefined)
  inputText.value = ''
  // 清理图片预览
  for (const img of pendingImages.value) {
    URL.revokeObjectURL(img.previewUrl)
  }
  pendingImages.value = []
  nextTick(() => scrollToBottom())
}

// ── 图片上传 ──

function triggerFileSelect() {
  fileInputRef.value?.click()
}

async function handleImageSelect(event: Event) {
  const input = event.target as HTMLInputElement
  const files = input.files
  if (!files) return
  // 并发上传所有图片
  await Promise.all(Array.from(files).map(file => addPendingImage(file)))
  // 重置 input 以便再次选择同一文件
  input.value = ''
}

async function handleDrop(event: DragEvent) {
  event.preventDefault()
  event.stopPropagation()
  const files = event.dataTransfer?.files
  if (!files) return
  await Promise.all(
    Array.from(files)
      .filter(f => f.type.startsWith('image/'))
      .map(file => addPendingImage(file))
  )
}

function handleDragOver(event: DragEvent) {
  event.preventDefault()
  event.stopPropagation()
}

// 校验图片像素尺寸（宽或高超过 8000px 拒绝）
const _MAX_IMAGE_PIXELS = 8000
const _MAX_IMAGES_PER_MESSAGE = 5
function checkImageDimensions(file: File): Promise<{ ok: true } | { ok: false; message: string }> {
  return new Promise((resolve) => {
    const img = new Image()
    const url = URL.createObjectURL(file)
    img.onload = () => {
      URL.revokeObjectURL(url)
      if (img.naturalWidth > _MAX_IMAGE_PIXELS || img.naturalHeight > _MAX_IMAGE_PIXELS) {
        resolve({ ok: false, message: `图片尺寸 ${img.naturalWidth}×${img.naturalHeight} 超过上限（最大 ${_MAX_IMAGE_PIXELS}px）` })
      } else {
        resolve({ ok: true })
      }
    }
    img.onerror = () => {
      URL.revokeObjectURL(url)
      resolve({ ok: false, message: '无法读取图片尺寸' })
    }
    img.src = url
  })
}

async function addPendingImage(file: File) {
  // 校验图片数量（每轮最多 5 张）
  if (pendingImages.value.length >= _MAX_IMAGES_PER_MESSAGE) {
    ElMessage.warning(`每轮最多上传 ${_MAX_IMAGES_PER_MESSAGE} 张图片，请先移除已有图片`)
    return
  }
  // 校验重复（同名+同大小视为同一张图）
  const isDuplicate = pendingImages.value.some(
    img => img.name === file.name && img.file.size === file.size,
  )
  if (isDuplicate) {
    ElMessage.warning(`图片 "${file.name}" 已在待发送列表中，请勿重复添加`)
    return
  }
  // 校验文件大小 (10MB)
  if (file.size > 10 * 1024 * 1024) {
    ElMessage.warning(`图片 "${file.name}" 超过 10MB 限制`)
    return
  }
  // 校验文件类型
  if (!file.type.startsWith('image/')) {
    ElMessage.warning(`"${file.name}" 不是图片文件`)
    return
  }
  // 校验图片像素尺寸
  const dimCheck = await checkImageDimensions(file)
  if (!dimCheck.ok) {
    ElMessage.warning(`图片 "${file.name}" ${dimCheck.message}`)
    return
  }

  const previewUrl = URL.createObjectURL(file)
  const pending: PendingImage = {
    file,
    previewUrl,
    name: file.name,
    uploading: true,
  }
  pendingImages.value.push(pending)
  const idx = pendingImages.value.length - 1

  // 最多上传 3 次（首次 + 2 次重试）
  let lastError = ''
  const retryDelays = [1000, 2000] // 第1次重试等1s，第2次等2s
  for (let attempt = 0; attempt < 3; attempt++) {
    if (attempt > 0) {
      await new Promise(r => setTimeout(r, retryDelays[attempt - 1]))
      const current = pendingImages.value[idx]
      if (!current) return
      pendingImages.value[idx] = { ...current, uploading: true, error: undefined }
    }
    try {
      const formData = new FormData()
      formData.append('file', file)
      const resp = await api.post('/agent/upload-image', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      const current = pendingImages.value[idx]
      if (!current) return
      pendingImages.value[idx] = {
        ...current,
        ossUrl: resp.data.url,
        uploading: false,
        error: undefined,
      }
      return // 上传成功
    } catch (e: unknown) {
      lastError = e instanceof Error ? e.message : '上传失败'
      if (attempt < 2) {
        const delay = retryDelays[attempt] ?? 0
        console.warn(`图片 "${file.name}" 第${attempt + 1}次上传失败，${delay / 1000}s 后重试`)
      }
    }
  }

  // 3 次都失败
  const current = pendingImages.value[idx]
  if (current) {
    pendingImages.value[idx] = {
      ...current,
      uploading: false,
      error: lastError,
    }
  }
  ElMessage.error({
    message: `图片 "${file.name}" 上传失败：${lastError}，可点击重试或移除`,
    duration: 0,  // 不自动关闭，用户手动关闭
    showClose: true,
  })
}

function removePendingImage(index: number) {
  const img = pendingImages.value[index]
  if (img) {
    URL.revokeObjectURL(img.previewUrl)
  }
  pendingImages.value.splice(index, 1)
}

function retryPendingImage(index: number) {
  const img = pendingImages.value[index]
  if (!img || img.uploading) return
  // 移除失败的条目，重新上传
  URL.revokeObjectURL(img.previewUrl)
  pendingImages.value.splice(index, 1)
  addPendingImage(img.file)
}

function quickSend(cmd: string) {
  chat.sendMessage(cmd)
  nextTick(() => scrollToBottom())
}

function handleNewChat() {
  chat.createNewSession()
}

function handleTogglePlanMode() {
  chat.togglePlanMode()
  // 通知由 watch(chat.planMode) 在状态实际变更后显示，避免重复/提前触发
}

/** 计划模式实际变更后显示通知 */
watch(() => chat.planMode.value, (newVal, oldVal) => {
  if (newVal === oldVal) return
  ElMessage.info(newVal ? '已进入计划模式（只读分析）' : '已退出计划模式')
})

/** 检测 AI 调用 ExitPlanMode 工具，提示用户计划已就绪 */
watch(
  () => chat.messages.value,
  (messages) => {
    if (!chat.planMode.value) return
    // 检查最后一条 assistant 消息是否包含 ExitPlanMode 工具调用
    const lastAssistantMsg = [...messages].reverse().find(m => m.role === 'assistant')
    if (!lastAssistantMsg) return

    const hasExitPlanCall = lastAssistantMsg.blocks.some(
      block => block.type === 'tool_call' &&
               (block as ToolCallBlock).toolCall.name === 'ExitPlanMode' &&
               (block as ToolCallBlock).toolCall.status === 'completed'
    )

    if (hasExitPlanCall) {
      // 提取 plan_summary
      const exitCall = lastAssistantMsg.blocks.find(
        block => block.type === 'tool_call' &&
                 (block as ToolCallBlock).toolCall.name === 'ExitPlanMode'
      ) as ToolCallBlock | undefined

      let summary = ''
      if (exitCall?.toolCall.result) {
        try {
          const result = typeof exitCall.toolCall.result === 'string'
            ? JSON.parse(exitCall.toolCall.result)
            : exitCall.toolCall.result
          summary = result.summary || ''
        } catch {
          // 解析失败，忽略
        }
      }

      ElMessage.success({
        message: `计划已就绪${summary ? '：' + summary : ''}`,
        duration: 5000,
        showClose: true,
      })
    }
  },
  { deep: true }
)

/** 全局 Shift+Tab 切换 plan mode —— 无论焦点在聊天区哪个元素上都能触发 */
function handleShiftTabPlanMode(e: KeyboardEvent) {
  if (!(e.shiftKey && e.key === 'Tab')) return
  e.preventDefault()
  handleTogglePlanMode()
}

/** 同时按下 U+I+O 切换所有思考过程展开/折叠 */
const CHORD_KEYS = ['u', 'i', 'o'] as const
const _heldChordKeys = new Set<string>()
let _chordFired = false  // 防止按住不放时重复触发

function handleChordKeyDown(e: KeyboardEvent) {
  const key = e.key.toLowerCase()
  if (!(CHORD_KEYS as readonly string[]).includes(key)) return
  // 输入框内不拦截，避免影响正常打字
  const target = e.target as HTMLElement
  if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA')) return

  _heldChordKeys.add(key)
  if (_heldChordKeys.size === CHORD_KEYS.length && !_chordFired) {
    _chordFired = true
    e.preventDefault()
    toggleAllThinkingSteps()
  }
}

function handleChordKeyUp(e: KeyboardEvent) {
  _heldChordKeys.delete(e.key.toLowerCase())
  if (_heldChordKeys.size === 0) _chordFired = false
}

/** 窗口失焦时重置按键状态（防止 keyup 丢失导致状态卡住） */
function handleChordReset() {
  _heldChordKeys.clear()
  _chordFired = false
}

function toggleAllThinkingSteps() {
  // 确定作用于哪个 expandedSteps 集合（chat 或 cron）
  const isCron = activeTab.value === 'cron' && cronAgentSessionId.value
  const stepsSet = isCron ? cronExpandedSteps.value : expandedSteps.value

  // 收集当前有思考过程的消息
  const messagesWithSteps = chat.messages.value.filter(m => hasIntermediateSteps(m))

  if (messagesWithSteps.length === 0) {
    ElMessage.info('没有可展开的思考过程')
    return
  }

  // 如果当前有任意一条展开 → 全部折叠；否则 → 全部展开
  const hasAnyExpanded = messagesWithSteps.some(m => stepsSet.has(m.id))
  if (hasAnyExpanded) {
    stepsSet.clear()
    ElMessage.success('已折叠全部思考过程')
  } else {
    for (const m of messagesWithSteps) {
      stepsSet.add(m.id)
    }
    ElMessage.success(`已展开 ${messagesWithSteps.length} 条思考过程`)
  }
}

function handleSwitchSession(sessionId: string) {
  chat.switchSession(sessionId)
}

function handleAnswerQuestion(answer: string, requestId?: string) {
  const trimmed = answer.trim()
  if (!trimmed) return

  // 先找到索引（在 answerQuestion 修改数组之前）
  let idx = -1
  if (requestId) {
    idx = chat.pendingQuestion.value.findIndex(q => q.requestId === requestId)
  }
  // 先清空该位置的输入（防止 splice 后文字错位到下一个问题）
  if (idx >= 0) askAnswerTexts[idx] = ''

  chat.answerQuestion(trimmed, requestId)
}

// 保持 askAnswerTexts 与 pendingQuestion 数组长度同步
// （session 切换、session 删除、中断等场景的安全网）
watch(
  () => chat.pendingQuestion.value.length,
  (newLen) => {
    if (askAnswerTexts.length !== newLen) {
      askAnswerTexts.length = newLen
      for (let i = 0; i < newLen; i++) {
        if (!askAnswerTexts[i]) askAnswerTexts[i] = ''
      }
    }
  },
  { immediate: true },
)

let scrollRafId: number | null = null

function scrollToBottom() {
  if (scrollRafId !== null) return
  scrollRafId = requestAnimationFrame(() => {
    scrollRafId = null
    if (chatScrollRef.value) {
      chatScrollRef.value.scrollTop = chatScrollRef.value.scrollHeight
    }
  })
}

function toggleSteps(messageId: string) {
  if (expandedSteps.value.has(messageId)) {
    expandedSteps.value.delete(messageId)
  } else {
    expandedSteps.value.add(messageId)
  }
}

// 清空展开状态（切换会话时调用）
function clearExpandedSteps() {
  expandedSteps.value.clear()
}

watch(() => chat.messages.value.length, () => nextTick(scrollToBottom))

// 切换 tab 按钮 → 通过路由导航（route watcher 同步 activeTab）
function navigateToTab(tab: 'chat' | 'cron') {
  if (tab === activeTab.value) return  // 已在当前 tab，不导航
  if (tab === 'cron') {
    // 切到 cron 前记住当前 chat 会话
    const sid = chat.currentSessionId.value
    if (sid && sid !== cronAgentSessionId.value) {
      lastChatSessionId.value = sid
    }
    router.push({ name: 'agent-cron' })
  } else {
    // 切到 chat → 导航到 /agent，由 route watcher 恢复会话
    router.push({ name: 'agent' })
  }
}

// 路由 → tab 同步（唯一权威）
watch(
  () => route.name,
  (name) => {
    const shouldBeCron = name === 'agent-cron'
    const isCron = activeTab.value === 'cron'
    if (shouldBeCron !== isCron) {
      activeTab.value = shouldBeCron ? 'cron' : 'chat'
    }
  },
)

// 切换 tab 时处理会话状态（由 route watcher 触发）
watch(activeTab, (newTab, oldTab) => {
  if (oldTab === undefined) return

  if (newTab === 'chat') {
    // 清除 cron 详情状态
    cronSelectedJob.value = null
    cronSelectedRunId.value = null
    cronAgentSessionId.value = null
    cronRuns.value = []
    // 恢复之前在看 chat 会话
    if (lastChatSessionId.value) {
      chat.switchSession(lastChatSessionId.value)
    } else {
      // 没有之前的 chat 会话 → 清空当前会话引用
      chat.currentSessionId.value = null
    }
  }
})

// ============ 会话管理 ============

const renamingSessionId = ref<string | null>(null)
const renameInput = ref('')

function handleDeleteSession(sessionId: string) {
  const session = chat.sessions.value.find(s => s.id === sessionId)
  const title = session?.title || '新对话'
  ElMessageBox.confirm(
    `确定要删除对话「${title}」吗？删除后不可恢复。`,
    '删除对话',
    { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' },
  ).then(async () => {
    try {
      await chat.deleteSession(sessionId)
      ElMessage.success('对话已删除')
    } catch (err) {
      showApiError(err, '删除失败')
    }
  }).catch(() => {})
}

function startRename(sessionId: string) {
  const session = chat.sessions.value.find(s => s.id === sessionId)
  renamingSessionId.value = sessionId
  renameInput.value = session?.title || ''
  nextTick(() => {
    const input = document.querySelector('.rename-input') as HTMLInputElement
    if (input) input.focus()
  })
}

async function confirmRename() {
  const sid = renamingSessionId.value
  if (!sid) return
  const title = renameInput.value.trim()
  if (!title) {
    ElMessage.warning('标题不能为空')
    return
  }
  try {
    await chat.renameSession(sid, title)
    ElMessage.success('已重命名')
  } catch (err) {
    showApiError(err, '重命名失败')
  }
  renamingSessionId.value = null
}

function cancelRename() {
  renamingSessionId.value = null
}

// 监听 cron WebSocket 事件，转发给 CronPanel + 刷新运行记录
watch(() => chat.cronEvents.value.length, (newLen) => {
  if (newLen > 0 && cronPanelRef.value) {
    const latest = chat.cronEvents.value[newLen - 1]
    if (!latest) return
    cronPanelRef.value.handleCronEvent(latest.event, latest.data as Record<string, unknown>)
    // 如果当前查看的任务有运行事件，刷新运行列表
    const jobId = (latest.data as Record<string, unknown>)?.job_id as string
    if (cronSelectedJob.value && jobId === cronSelectedJob.value.id) {
      const evt = latest.event
      if (['cron_run_completed', 'cron_run_failed', 'cron_run_started'].includes(evt)) {
        cronApi.listRuns(cronSelectedJob.value.id).then(({ data }) => {
          cronRuns.value = data.runs
        }).catch(() => {})
      }
    }
  }
})

// ── Cron detail handlers ──

async function handleCronJobSelect(job: CronJob) {
  cronSelectedJob.value = job
  cronSelectedRunId.value = null
  cronAgentSessionId.value = null
  cronExpandedSteps.value = new Set()
  try {
    const { data } = await cronApi.listRuns(job.id)
    cronRuns.value = data.runs
  } catch {
    cronRuns.value = []
  }
}

/** 获取已缓存的 run→session 映射 */
function getCronRunSessionMap(): Record<string, string> {
  try {
    const raw = sessionStorage.getItem('cron_run_session_map')
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

/** 缓存 run→session 映射 */
function setCronRunSession(runId: string, sessionId: string) {
  const map = getCronRunSessionMap()
  map[runId] = sessionId
  sessionStorage.setItem('cron_run_session_map', JSON.stringify(map))
}

async function handleCronRunSelect(run: CronJobRun) {
  cronSelectedRunId.value = run.id
  cronExpandedSteps.value = new Set()
  cronAgentSessionId.value = null
  cronSessionLoading.value = true
  try {
    // 检查是否已有此 run 对应的会话（避免重复创建、丢弃继续的对话）
    const existingMap = getCronRunSessionMap()
    const existingSessionId = existingMap[run.id]
    let sessionId: string
    if (existingSessionId) {
      // 复用已有会话（保留继续对话的消息）
      sessionId = existingSessionId
    } else {
      // 后端：从 cron 运行上下文创建 Agent 会话
      const { data } = await cronApi.createSessionFromRun(run.id)
      sessionId = data.session_id
      setCronRunSession(run.id, sessionId)
    }
    cronAgentSessionId.value = sessionId
    // 保存 cron 状态到 sessionStorage（页面刷新后可恢复）
    sessionStorage.setItem('cron_active_session', JSON.stringify({
      sessionId,
      runId: run.id,
      jobId: cronSelectedJob.value?.id || '',
      jobName: cronSelectedJob.value?.name || '',
    }))
    // 通过 WebSocket 加载会话消息
    // URL 会由 watch(currentSessionId) 自动更新为 /agent/cron
    chat.switchSession(sessionId)
  } catch {
    cronAgentSessionId.value = null
  } finally {
    cronSessionLoading.value = false
  }
}

function sendCronMessage() {
  const text = cronInputText.value.trim()
  if (!text || !cronAgentSessionId.value) return
  // 确保当前会话是 cron 会话
  if (chat.currentSessionId.value !== cronAgentSessionId.value) {
    chat.switchSession(cronAgentSessionId.value)
  }
  chat.sendMessage(text)
  cronInputText.value = ''
  nextTick(() => cronScrollToBottom())
}

function cronScrollToBottom() {
  requestAnimationFrame(() => {
    if (cronScrollRef.value) {
      cronScrollRef.value.scrollTop = cronScrollRef.value.scrollHeight
    }
  })
}

// cron 消息更新时自动滚动
watch(() => chat.messages.value.length, () => {
  if (activeTab.value === 'cron' && cronAgentSessionId.value) {
    nextTick(cronScrollToBottom)
  }
})

function cronBackToList() {
  cronSelectedJob.value = null
  cronSelectedRunId.value = null
  cronAgentSessionId.value = null
  cronRuns.value = []
  sessionStorage.removeItem('cron_active_session')
  // 切回 chat tab，恢复到之前看的会话
  activeTab.value = 'chat'
  if (lastChatSessionId.value) {
    chat.switchSession(lastChatSessionId.value)
  }
}

function cronToggleSteps(messageId: string) {
  if (cronExpandedSteps.value.has(messageId)) {
    cronExpandedSteps.value.delete(messageId)
  } else {
    cronExpandedSteps.value.add(messageId)
  }
}

function handleImageClick(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (target.tagName === 'IMG') {
    const src = target.getAttribute('src')
    if (src) {
      lightboxSrc.value = src
    }
  }
}

function closeLightbox() {
  lightboxSrc.value = null
}

onMounted(() => {
  console.log('[AgentView][onMounted] route=%s, name=%s, params=%o',
    route.fullPath, route.name, route.params)
  chat.connect()
  window.addEventListener('keydown', handleEscInterrupt)
  window.addEventListener('keydown', handleShiftTabPlanMode)
  window.addEventListener('keydown', handleChordKeyDown)
  window.addEventListener('keyup', handleChordKeyUp)
  window.addEventListener('blur', handleChordReset)

  // 如果有 initialMessage，立即清理 URL query 参数
  if (_initialMsg) {
    router.replace({ name: 'agent' })
  }

  // 等待 WebSocket 连接好后加载会话列表（仅首次）
  let loadStarted = false
  const waitAndLoad = () => {
    if (loadStarted) return
    if (!chat.connected.value) {
      setTimeout(waitAndLoad, 200)
      return
    }
    loadStarted = true
    chat.loadSessions()
    dataLoaded = true

    // 根据 URL 路由名决定初始 tab
    if (route.name === 'agent-cron') {
      activeTab.value = 'cron'
      // 从 sessionStorage 恢复 cron 视图状态
      const saved = sessionStorage.getItem('cron_active_session')
      if (saved) {
        try {
          const { sessionId, jobId, jobName } = JSON.parse(saved)
          cronAgentSessionId.value = sessionId
          cronSelectedJob.value = { id: jobId, name: jobName } as CronJob
          cronSelectedRunId.value = 'restored'
          chat.switchSession(sessionId)
        } catch {
          sessionStorage.removeItem('cron_active_session')
        }
      }
      return
    }

    // chat 模式：如果 URL 中有 sessionId，恢复该会话
    const routeSessionId = route.params.sessionId as string | undefined
    if (routeSessionId && !_initialMsg) {
      console.log('[AgentView][onMounted] 恢复会话 → %s', routeSessionId)
      chat.switchSession(routeSessionId)
      lastChatSessionId.value = routeSessionId
    }
  }
  setTimeout(waitAndLoad, 100)
})

// <keep-alive> 重新激活时：检查 URL 是否变了
onActivated(() => {
  console.log('[AgentView][onActivated] route=%s, name=%s, activeTab=%s, currentSessionId=%s',
    route.fullPath, route.name, activeTab.value, chat.currentSessionId.value)

  // 根据路由名同步 tab 状态
  if (route.name === 'agent-cron' && activeTab.value !== 'cron') {
    activeTab.value = 'cron'
    return
  }
  if (route.name !== 'agent-cron' && activeTab.value === 'cron') {
    activeTab.value = 'chat'
    return
  }

  // cron 模式下不恢复 chat 会话（避免干扰 cron 视图）
  if (activeTab.value === 'cron' && cronAgentSessionId.value) {
    console.log('[AgentView][onActivated] cron 模式，跳过会话恢复')
    return
  }

  // initialMessage 优先级最高——让 watch 处理新消息预填，不要抢先导航到旧会话
  if (route.query.initialMessage) {
    return
  }

  const routeSessionId = route.params.sessionId as string | undefined
  const currentId = chat.currentSessionId.value

  if (routeSessionId && routeSessionId !== currentId) {
    console.log('[AgentView][onActivated] switchSession → %s', routeSessionId)
    chat.switchSession(routeSessionId)
  } else if (!routeSessionId && currentId && activeTab.value === 'chat') {
    // 仅在 chat 模式下同步 URL
    if (route.name !== 'agent-session') {
      router.replace({ name: 'agent-session', params: { sessionId: currentId } })
    }
  }
})

// 监听会话切换 → 更新 URL + 记住 chat 会话
watch(
  () => chat.currentSessionId.value,
  (newId) => {
    console.log('[AgentView][watch:currentSessionId] newId=%s, route=%s, activeTab=%s',
      newId, route.fullPath, activeTab.value)

    // 在 chat 模式下，记住当前会话（用于切回 chat 时恢复）
    if (activeTab.value === 'chat' && newId && newId !== cronAgentSessionId.value) {
      lastChatSessionId.value = newId
    }

    // 有 initialMessage 时，强制留在 /agent 空页面
    if (route.query.initialMessage) {
      if (route.params.sessionId) {
        router.replace({ name: 'agent' })
      }
      clearExpandedSteps()
      return
    }

    // cron 会话 → /agent/cron
    if (newId === cronAgentSessionId.value && activeTab.value === 'cron') {
      if (route.name !== 'agent-cron') {
        router.replace({ name: 'agent-cron' })
      }
      return
    }

    // chat 会话 → /agent 或 /agent/:sessionId
    const routeSessionId = route.params.sessionId as string | undefined
    if (newId) {
      if (newId !== routeSessionId) {
        console.log('[AgentView][watch:currentSessionId] router.replace → agent-session, id=%s', newId)
        router.replace({ name: 'agent-session', params: { sessionId: newId } })
      }
    } else {
      // currentSessionId 变为 null → 导航到空 chat 页面
      if (route.name === 'agent-cron' || routeSessionId) {
        console.log('[AgentView][watch:currentSessionId] router.replace → agent (清空会话)')
        router.replace({ name: 'agent' })
      }
    }
    // 清空中间步骤的展开状态
    clearExpandedSteps()
  },
)

onUnmounted(() => {
  chat.disconnect()
  window.removeEventListener('keydown', handleEscInterrupt)
  window.removeEventListener('keydown', handleShiftTabPlanMode)
  window.removeEventListener('keydown', handleChordKeyDown)
  window.removeEventListener('keyup', handleChordKeyUp)
  window.removeEventListener('blur', handleChordReset)
})
</script>

<style scoped>
.agent-page {
  display: flex;
  height: calc(100dvh - 108px);
  background: var(--color-surface);
  border-radius: var(--radius-lg);
  overflow: hidden;
  border: 1px solid var(--border-subtle);
}

.no-permission-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
}

/* ═══ 侧边栏 ═══ */
.sidebar {
  width: 260px;
  background: var(--color-surface-alt);
  border-right: 1px solid var(--border-subtle);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

@media (max-width: 768px) {
  .sidebar { display: none; }
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 18px;
  border-bottom: 1px solid var(--border-subtle);
}

.sidebar-header h3 {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
  font-family: var(--font-display);
}

.new-chat-btn {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  border: 1px solid var(--border-subtle);
  background: var(--color-surface);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
  transition: all 0.15s;
}

.new-chat-btn:hover {
  background: var(--color-accent);
  color: white;
  border-color: var(--color-accent);
}

.session-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.session-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s;
  margin-bottom: 2px;
}

.session-item:hover {
  background: rgba(0, 0, 0, 0.03);
}

.session-item.active {
  background: var(--color-accent-subtle);
}

.session-icon {
  color: var(--text-muted);
  font-size: 16px;
  flex-shrink: 0;
}

.session-item.active .session-icon {
  color: var(--color-accent);
}

.session-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1;
  gap: 2px;
}

.session-title-row {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.session-plan-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--color-accent);
  flex-shrink: 0;
  box-shadow: 0 0 4px rgba(176, 141, 71, 0.5);
}

.session-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-meta {
  font-size: 11px;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-top: 2px;
}

/* ─── 会话菜单（三点按钮 + 下拉） ─── */
.session-menu {
  position: relative;
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.15s;
}

.session-item:hover .session-menu {
  opacity: 1;
}

.menu-trigger {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  border: none;
  background: transparent;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  font-size: 14px;
  transition: all 0.15s;
}

.menu-trigger:hover {
  background: rgba(0, 0, 0, 0.08);
  color: var(--text-primary);
}

.menu-dropdown {
  display: none;
  position: absolute;
  top: 100%;
  right: 0;
  z-index: 100;
  min-width: 120px;
  background: var(--color-surface);
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  border: 1px solid var(--border-subtle);
  padding: 4px;
  animation: fadeIn 0.12s ease;
}

.session-menu:focus-within .menu-dropdown,
.session-menu:hover .menu-dropdown {
  display: block;
}

.menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 12px;
  border-radius: 6px;
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 13px;
  color: var(--text-primary);
  transition: all 0.12s;
  text-align: left;
}

.menu-item:hover {
  background: rgba(0, 0, 0, 0.04);
}

.menu-item.danger {
  color: #e74c3c;
}

.menu-item.danger:hover {
  background: rgba(232, 84, 84, 0.06);
}

/* ─── 重命名输入行 ─── */
.rename-row {
  display: flex;
  align-items: center;
  gap: 4px;
  flex: 1;
  min-width: 0;
}

.rename-input {
  flex: 1;
  min-width: 0;
  height: 28px;
  padding: 0 8px;
  border: 1px solid var(--color-accent);
  border-radius: 6px;
  font-size: 13px;
  outline: none;
  background: var(--color-surface);
  color: var(--text-primary);
}

.rename-confirm-btn,
.rename-cancel-btn {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  transition: all 0.12s;
  flex-shrink: 0;
}

.rename-confirm-btn {
  background: var(--color-accent);
  color: white;
}

.rename-confirm-btn:hover {
  opacity: 0.85;
}

.rename-cancel-btn {
  background: var(--color-surface-muted);
  color: var(--text-muted);
}

.rename-cancel-btn:hover {
  background: var(--color-surface-muted);
}

.no-sessions {
  text-align: center;
  padding: 24px 16px;
  color: var(--text-muted);
  font-size: 13px;
}

/* ═══ 对话主区域 ═══ */
/* ═══ Tab 切换 ═══ */
.sidebar-tabs {
  display: flex;
  gap: 4px;
  padding: 10px 12px 12px;
  border-bottom: 1px solid var(--border-subtle);
}

.tab-btn {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 10px 4px;
  border: none;
  border-radius: 10px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
  position: relative;
}

.tab-btn::after {
  content: '';
  position: absolute;
  bottom: -13px;
  left: 50%;
  transform: translateX(-50%) scaleX(0);
  width: 24px;
  height: 2px;
  border-radius: 1px;
  background: var(--color-accent, #b08d47);
  transition: transform 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}

.tab-btn:hover {
  background: rgba(0, 0, 0, 0.03);
  color: var(--text-secondary);
}

.tab-btn.active {
  background: var(--color-accent-subtle, rgba(176, 141, 71, 0.06));
  color: var(--color-accent, #b08d47);
}

.tab-btn.active::after {
  transform: translateX(-50%) scaleX(1);
}

.tab-icon {
  width: 32px;
  height: 32px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.03);
  transition: all 0.2s ease;
  color: var(--text-muted);
}

.tab-btn.active .tab-icon {
  background: rgba(176, 141, 71, 0.12);
  color: var(--color-accent, #b08d47);
}

.tab-label {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.02em;
  font-family: var(--font-display);
}

.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: var(--color-surface);
}

/* ─── 空状态 ─── */
.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px;
}

.restoring-state .empty-icon {
  opacity: 0.7;
}

.empty-icon {
  color: var(--color-accent);
  opacity: 0.4;
  margin-bottom: 16px;
}

.empty-state h2 {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 8px;
  font-family: var(--font-display);
}

.empty-desc {
  font-size: 14px;
  color: var(--text-muted);
  margin: 0 0 28px;
}

.empty-input {
  width: 100%;
  max-width: 560px;
}

.quick-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
  justify-content: center;
}

.quick-btn {
  padding: 5px 14px;
  border-radius: 16px;
  border: 1px solid var(--border-subtle);
  background: var(--color-surface);
  font-size: 12px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s;
  font-family: var(--font-mono);
}

.quick-btn:hover {
  border-color: var(--color-accent);
  color: var(--color-accent);
  background: var(--color-accent-subtle);
}

/* ─── 消息列表 ─── */
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 24px 32px;
}

@media (max-width: 768px) {
  .chat-messages { padding: 16px; }
}

.message {
  display: flex;
  gap: 14px;
  margin-bottom: 24px;
  animation: fadeIn 0.25s ease;
}

.message.user {
  flex-direction: row-reverse;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.message-avatar {
  flex-shrink: 0;
}

.avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
}

.user-avatar {
  background: var(--color-accent);
  color: white;
}

.ai-avatar {
  background: var(--color-border-default, #f0eee9);
  color: var(--text-secondary);
}

.message-body {
  max-width: 72%;
  min-width: 0;
}

@media (max-width: 768px) {
  .message-body { max-width: 85%; }
}

.message.user .message-body {
  text-align: right;
}

.message-content {
  display: inline-block;
  padding: 10px 16px;
  border-radius: 16px;
  font-size: 14px;
  line-height: 1.65;
  text-align: left;
  word-break: break-word;
}

.message-content :deep(p:first-child) {
  margin-top: 0;
}

.message-content :deep(p:last-child) {
  margin-bottom: 0;
}

.message.user .message-content {
  background: var(--color-accent);
  color: white;
  border-radius: 16px 16px 4px 16px;
}

.message.assistant .message-content {
  background: var(--color-surface);
  color: var(--text-primary);
  border: 1px solid var(--border-subtle);
  border-radius: 16px 16px 16px 4px;
}

/* ─── 思考动画 ─── */
.thinking-dots {
  display: flex;
  gap: 5px;
  padding: 8px 0;
}

.thinking-dots span {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--color-accent);
  opacity: 0.35;
  animation: bounce 1.4s infinite ease-in-out;
}

.thinking-dots span:nth-child(2) { animation-delay: 0.16s; }
.thinking-dots span:nth-child(3) { animation-delay: 0.32s; }

@keyframes bounce {
  0%, 80%, 100% { transform: translateY(0); }
  40% { transform: translateY(-8px); }
}

.typing-indicator {
  display: flex;
  gap: 5px;
  padding: 8px 0;
}

.typing-indicator .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-accent);
  opacity: 0.4;
  animation: bounce 1.4s infinite ease-in-out;
}

.typing-indicator .dot:nth-child(2) { animation-delay: 0.2s; }
.typing-indicator .dot:nth-child(3) { animation-delay: 0.4s; }

/* ─── 工具调用 ─── */
.tool-calls {
  margin-top: 8px;
}

/* ─── 输入区域 ─── */
.chat-input-area {
  padding: 16px 32px;
  border-top: 1px solid var(--border-subtle);
  background: var(--color-surface);
  flex-shrink: 0;
}

@media (max-width: 768px) {
  .chat-input-area { padding: 12px 16px; }
}

.input-wrapper {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: flex-end;
  max-width: 800px;
  margin: 0 auto;
}

.input-wrapper :deep(.el-textarea__inner) {
  border-radius: 12px !important;
  padding: 10px 16px;
  font-size: 14px;
  box-shadow: none;
  border: 1px solid var(--border-subtle);
  resize: none;
}

/* textarea 占满剩余宽度 */
.chat-input {
  flex: 1;
  min-width: 0;
}

.input-wrapper :deep(.el-textarea__inner:focus) {
  border-color: var(--color-accent);
}

.send-btn {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: none;
  background: var(--color-accent);
  color: white;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  transition: all 0.15s;
  flex-shrink: 0;
}

.send-btn:hover:not(:disabled) {
  transform: scale(1.05);
  box-shadow: 0 2px 8px rgba(176, 141, 71, 0.3);
}

.send-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* ─── 图片上传按钮 ─── */
.attach-btn {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: 1px solid var(--border-subtle);
  background: var(--color-surface);
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  transition: all 0.15s;
  flex-shrink: 0;
}

.attach-btn:hover:not(:disabled) {
  border-color: var(--color-accent);
  color: var(--color-accent);
  background: var(--color-surface-hover);
}

.attach-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* ─── 图片预览条 ─── */
.pending-images-preview {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  width: 100%;
  max-width: 800px;
  margin: 0 auto 4px;
  padding: 0 4px;
}

.pending-image-thumb {
  position: relative;
  width: 72px;
  height: 72px;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  background: var(--color-surface-hover);
}

.pending-image-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.upload-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.45);
  color: white;
  font-size: 10px;
  text-align: center;
  padding: 2px;
}

.upload-overlay.upload-error {
  background: rgba(231, 76, 60, 0.7);
  flex-direction: column;
  gap: 4px;
}

.error-text {
  font-size: 10px;
}

.retry-btn {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: none;
  background: var(--color-surface);
  color: var(--color-accent);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  transition: transform 0.15s;
}

.retry-btn:hover {
  transform: scale(1.15);
}

.remove-image-btn {
  position: absolute;
  top: 2px;
  right: 2px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  border: none;
  background: rgba(0, 0, 0, 0.5);
  color: white;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  transition: background 0.15s;
}

.remove-image-btn:hover {
  background: rgba(231, 76, 60, 0.8);
}

/* ─── 用户消息中的图片（横向排列） ─── */
.user-images-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 6px;
}

.msg-image {
  max-width: 320px;
  max-height: 240px;
  border-radius: 12px;
  cursor: pointer;
  transition: opacity 0.15s;
  border: 1px solid var(--border-subtle);
}

.msg-image:hover {
  opacity: 0.85;
}

@media (max-width: 768px) {
  .msg-image {
    max-width: 240px;
    max-height: 180px;
  }
}

/* ═══ AskUserQuestion 内联卡片 ═══ */
.ask-card {
  margin: 0 32px 12px;
  padding: 20px 24px;
  background: rgba(212, 179, 106, 0.06);
  border: 1px solid #f0e6c8;
  border-left: 4px solid var(--color-accent);
  border-radius: 12px;
  max-width: 800px;
  width: calc(100% - 64px);
  align-self: center;
  flex-shrink: 0;
  animation: slideUp 0.25s ease;
}

@media (max-width: 768px) {
  .ask-card { margin: 0 16px 12px; width: calc(100% - 32px); }
}

@keyframes slideUp {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.ask-card .ask-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.ask-card .ask-icon {
  color: var(--color-accent);
  font-size: 20px;
}

.ask-card .ask-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
  font-family: var(--font-display);
}

.ask-card .ask-index {
  margin-left: auto;
  font-size: 12px;
  color: var(--text-tertiary);
  background: var(--bg-secondary);
  padding: 2px 8px;
  border-radius: 10px;
}

.ask-card .ask-question {
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin: 0 0 16px;
}

.ask-card .ask-options {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 14px;
}

.ask-card .ask-option-btn {
  padding: 10px 16px;
  border-radius: 10px;
  border: 1px solid var(--border-subtle);
  background: var(--color-surface);
  font-size: 14px;
  color: var(--text-primary);
  cursor: pointer;
  text-align: left;
  transition: all 0.15s;
}

.ask-card .ask-option-btn:hover {
  border-color: var(--color-accent);
  background: var(--color-accent-subtle);
  color: var(--color-accent);
}

.ask-card .ask-input-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.ask-card .ask-input {
  flex: 1;
}

.ask-send-btn {
  width: 36px !important;
  height: 36px !important;
  font-size: 14px !important;
}

/* ═══ 思考过程 ═══ */
.thinking-process {
  margin: 12px 0;
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  background: var(--color-surface-hover);
  overflow: hidden;
  transition: all 0.2s ease;
}

.thinking-process.expanded {
  background: var(--color-surface-muted);
}

/* 正在思考时给 header 加一个动态指示条 */
.thinking-process.thinking-active {
  border-color: var(--color-accent);
  box-shadow: 0 0 0 1px rgba(25, 118, 210, 0.1);
}

.thinking-process.thinking-active .thinking-header {
  background: linear-gradient(90deg, rgba(25, 118, 210, 0.06) 0%, transparent 100%);
}

.thinking-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  cursor: pointer;
  user-select: none;
  transition: background 0.15s;
}

.thinking-header:hover {
  background: rgba(0, 0, 0, 0.04);
}

.thinking-icon {
  color: var(--text-muted);
  font-size: 14px;
  transition: transform 0.2s ease;
}

.thinking-icon.rotated {
  transform: rotate(90deg);
}

.thinking-title {
  flex: 1;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.thinking-hint {
  font-size: 12px;
  color: var(--text-muted);
}

.thinking-content {
  padding: 0 16px 16px;
}

/* 步骤项 */
.step-item {
  margin-bottom: 12px;
  background: var(--color-surface);
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  transition: all 0.2s ease;
}

.step-item:last-child {
  margin-bottom: 0;
}

.step-item:hover {
  border-color: var(--color-accent);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.step-item.sub-agent-step {
  cursor: pointer;
}

/* 工具调用步骤：按状态区分左边框颜色 */
.step-item.tool-step {
  border-left: 3px solid #1976d2;
}

.step-item.tool-step.status-done {
  border-left-color: #388e3c;
}

.step-item.tool-step.status-completed {
  border-left-color: #388e3c;
}

.step-item.tool-step.status-running {
  border-left-color: #1976d2;
}

.step-item.tool-step.status-running .tool-icon {
  animation: pulse-icon 1.5s ease-in-out infinite;
}

.step-item.tool-step.status-error {
  border-left-color: #d32f2f;
  background: rgba(232, 84, 84, 0.05);
}

.step-item.tool-step.status-error .tool-icon {
  color: #d32f2f;
}

.step-item.tool-step.status-interrupted {
  border-left-color: #e65100;
  background: rgba(212, 179, 106, 0.06);
}

.step-item.tool-step.status-interrupted .tool-icon {
  color: #e65100;
}

@keyframes pulse-icon {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* 中间文本步骤 */
.step-item.text-step {
  border-left: 3px solid #1976d2;
}

.text-step-label {
  color: #1976d2 !important;
  font-size: 12px !important;
  font-family: var(--font-display) !important;
}

.intermediate-text {
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary);
  padding: 4px 0;
  word-break: break-word;
}

.intermediate-text :deep(p:first-child) {
  margin-top: 0;
}

.intermediate-text :deep(p:last-child) {
  margin-bottom: 0;
}

.intermediate-text :deep(pre) {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 10px 14px;
  border-radius: 6px;
  overflow-x: auto;
  font-size: 12px;
  margin: 6px 0;
}

.intermediate-text :deep(code) {
  font-family: var(--font-mono);
  background: var(--color-surface-code);
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 12px;
}

.step-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  background: var(--color-surface-hover);
}

.step-name {
  flex: 1;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  font-family: var(--font-mono);
}

.step-status {
  font-size: 12px;
  padding: 3px 8px;
  border-radius: 12px;
  font-weight: 500;
}

.step-status.running {
  background: rgba(91, 141, 239, 0.1);
  color: #1976d2;
}

.step-status.done,
.step-status.completed {
  background: rgba(62, 186, 111, 0.1);
  color: #388e3c;
}

.step-status.error {
  background: rgba(232, 84, 84, 0.08);
  color: #d32f2f;
}

.step-status.interrupted {
  background: rgba(232, 168, 64, 0.06);
  color: #e65100;
}

.expand-hint {
  color: var(--text-muted);
  font-size: 14px;
}

/* 步骤详情 */
.step-details {
  padding: 12px 14px;
  border-top: 1px solid var(--border-subtle);
}

.detail-section {
  margin-bottom: 12px;
}

.detail-section:last-child {
  margin-bottom: 0;
}

.detail-label {
  display: block;
  font-size: 11px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-weight: 600;
  margin-bottom: 6px;
}

.detail-content {
  font-size: 12px;
  background: var(--color-surface-muted);
  padding: 10px 12px;
  border-radius: 6px;
  overflow-x: auto;
  max-height: 200px;
  margin: 0;
  font-family: var(--font-mono);
  color: var(--text-primary);
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  border: 1px solid var(--border-subtle);
}

/* 工具图标 */
.tool-icon {
  color: #1976d2;
  font-size: 16px;
}

.sub-agent-icon {
  color: #7b1fa2;
  font-size: 16px;
}

/* 最终回复 */
.final-response {
  margin-top: 12px;
  padding: 12px 16px;
  background: var(--color-surface);
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.65;
  color: var(--text-primary);
  word-break: break-word;
}

.final-response :deep(h1),
.final-response :deep(h2),
.final-response :deep(h3),
.final-response :deep(h4) {
  margin: 16px 0 8px;
  font-weight: 700;
  line-height: 1.3;
  color: var(--text-primary);
}

.final-response :deep(h1) { font-size: 20px; }
.final-response :deep(h2) { font-size: 17px; }
.final-response :deep(h3) { font-size: 15px; }
.final-response :deep(h4) { font-size: 14px; }

.final-response :deep(p) {
  margin: 6px 0;
}

.final-response :deep(p:first-child) {
  margin-top: 0;
}

.final-response :deep(p:last-child) {
  margin-bottom: 0;
}

.final-response :deep(pre) {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 14px 16px;
  border-radius: 8px;
  overflow-x: auto;
  margin: 10px 0;
  font-size: 12px;
  line-height: 1.55;
}

.final-response :deep(pre code) {
  background: none;
  padding: 0;
  border-radius: 0;
  font-size: inherit;
  color: inherit;
}

.final-response :deep(code) {
  font-family: var(--font-mono);
  background: var(--color-surface-code);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 13px;
  color: #c0392b;
}

.final-response :deep(ul),
.final-response :deep(ol) {
  padding-left: 22px;
  margin: 8px 0;
}

.final-response :deep(li) {
  margin: 3px 0;
  line-height: 1.6;
}

.final-response :deep(blockquote) {
  border-left: 3px solid var(--color-accent);
  margin: 10px 0;
  padding: 6px 14px;
  color: var(--text-secondary);
  background: var(--color-surface-alt);
  border-radius: 0 6px 6px 0;
}

.final-response :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 10px 0;
  font-size: 13px;
}

.final-response :deep(th),
.final-response :deep(td) {
  border: 1px solid var(--border-subtle);
  padding: 8px 12px;
  text-align: left;
}

.final-response :deep(th) {
  background: var(--color-surface-hover);
  font-weight: 600;
}

.final-response :deep(tr:nth-child(even)) {
  background: var(--color-surface-alt);
}

.final-response :deep(hr) {
  border: none;
  border-top: 1px solid var(--border-subtle);
  margin: 16px 0;
}

.final-response :deep(a) {
  color: var(--color-accent);
  text-decoration: none;
}

.final-response :deep(a:hover) {
  text-decoration: underline;
}

.final-response :deep(img) {
  max-width: 100%;
  border-radius: 8px;
  margin: 8px 0;
}

/* 用户消息中的 markdown 也增强一下 */
.message-content :deep(pre) {
  background: rgba(255, 255, 255, 0.15);
  color: white;
  padding: 10px 14px;
  border-radius: 8px;
  overflow-x: auto;
  margin: 6px 0;
  font-size: 12px;
  line-height: 1.5;
}

.message-content :deep(code) {
  font-family: var(--font-mono);
  background: rgba(255, 255, 255, 0.15);
  padding: 1px 4px;
  border-radius: 3px;
}

/* ═══ 子 Agent 详情抽屉 ═══ */
.sub-agent-drawer-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.3);
  display: flex;
  justify-content: flex-end;
  z-index: 2000;
  animation: fadeIn 0.2s ease;
}

.sub-agent-drawer {
  width: 480px;
  max-width: 80vw;
  height: 100%;
  background: var(--color-surface);
  box-shadow: -4px 0 20px rgba(0, 0, 0, 0.15);
  display: flex;
  flex-direction: column;
  animation: slideInRight 0.3s ease;
}

@keyframes slideInRight {
  from {
    transform: translateX(100%);
  }
  to {
    transform: translateX(0);
  }
}

.drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-subtle);
  background: var(--color-surface-hover);
}

.drawer-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
}

.drawer-close {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  border: none;
  background: transparent;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  transition: all 0.15s;
}

.drawer-close:hover {
  background: rgba(0, 0, 0, 0.05);
  color: var(--text-primary);
}

.drawer-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.drawer-section {
  margin-bottom: 20px;
}

.drawer-section:last-child {
  margin-bottom: 0;
}

.section-title {
  font-size: 12px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-weight: 600;
  margin-bottom: 8px;
}

.section-content {
  font-size: 14px;
  color: var(--text-primary);
  line-height: 1.5;
}

.status-badge {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
}

.status-badge.running {
  background: rgba(91, 141, 239, 0.1);
  color: #1976d2;
}

.status-badge.completed,
.status-badge.done {
  background: rgba(62, 186, 111, 0.1);
  color: #388e3c;
}

.status-badge.error {
  background: rgba(232, 84, 84, 0.08);
  color: #d32f2f;
}

.output-content {
  background: var(--color-surface-muted);
  padding: 12px 14px;
  border-radius: 8px;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: var(--font-mono);
  font-size: 13px;
  line-height: 1.5;
  border: 1px solid var(--border-subtle);
}

/* 工具调用列表（抽屉内） */
.tool-call-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.tool-call-item {
  background: var(--color-surface-hover);
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  border-left: 3px solid #388e3c;
}

.tool-call-item.status-done,
.tool-call-item.status-completed {
  border-left-color: #388e3c;
}

.tool-call-item.status-running {
  border-left-color: #1976d2;
}

.tool-call-item.status-error {
  border-left-color: #d32f2f;
  background: rgba(232, 84, 84, 0.05);
}

.tool-call-item.status-interrupted {
  border-left-color: #e65100;
  background: rgba(212, 179, 106, 0.06);
}

.tool-call-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: var(--color-surface-muted);
}

.tool-name {
  flex: 1;
  font-size: 13px;
  font-weight: 600;
  font-family: var(--font-mono);
  color: var(--text-primary);
}

.tool-call-details {
  padding: 12px 14px;
}

/* 动画 */
@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

/* ==========================================================================
   Image Lightbox
   ========================================================================== */

.image-lightbox {
  position: fixed;
  inset: 0;
  z-index: 3000;
  display: flex;
  align-items: center;
  justify-content: center;
  animation: fadeIn 0.2s ease;
}

.lightbox-backdrop {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.85);
  backdrop-filter: blur(8px);
}

.lightbox-container {
  position: relative;
  max-width: 90vw;
  max-height: 90vh;
  display: flex;
  align-items: center;
  justify-content: center;
  animation: scaleIn 0.25s cubic-bezier(0.16, 1, 0.3, 1);
}

@keyframes scaleIn {
  from { opacity: 0; transform: scale(0.92); }
  to { opacity: 1; transform: scale(1); }
}

.lightbox-close {
  position: absolute;
  top: -44px;
  right: 0;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: none;
  background: rgba(255, 255, 255, 0.15);
  color: white;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  transition: background 0.15s;
}

.lightbox-close:hover {
  background: rgba(255, 255, 255, 0.25);
}

.lightbox-image {
  max-width: 90vw;
  max-height: 85vh;
  border-radius: 8px;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.4);
  object-fit: contain;
}

/* ─── Hover cursor for clickable images ─── */
.final-response :deep(img),
.intermediate-text :deep(img),
.message-content :deep(img) {
  cursor: pointer;
  transition: opacity 0.15s ease;
}

.final-response :deep(img):hover,
.intermediate-text :deep(img):hover,
.message-content :deep(img):hover {
  opacity: 0.85;
}

/* ═══ Chat Inner (wrapper) ═══ */
.chat-inner {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

/* ═══ Cron Detail Main Area ═══ */
.cron-detail-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.cron-detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 24px;
  border-bottom: 1px solid var(--border-subtle);
  flex-shrink: 0;
}

.cron-back-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: 8px;
  border: 1px solid var(--border-subtle);
  background: var(--color-surface);
  cursor: pointer;
  font-size: 13px;
  color: var(--text-secondary);
  transition: all 0.12s;
}

.cron-back-btn:hover {
  background: rgba(0, 0, 0, 0.03);
  color: var(--text-primary);
}

.cron-header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.cron-next-run {
  font-size: 12px;
  color: var(--text-muted);
}

/* ── Detail Body: Runs Sidebar + Conversation ── */
.cron-detail-body {
  flex: 1;
  display: flex;
  min-height: 0;
}

.cron-runs-sidebar {
  width: 200px;
  flex-shrink: 0;
  border-right: 1px solid var(--border-subtle);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.cron-runs-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  border-bottom: 1px solid var(--border-subtle);
}

.cron-refresh-btn {
  width: 22px;
  height: 22px;
  border-radius: 4px;
  border: none;
  background: transparent;
  cursor: pointer;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.12s;
}

.cron-refresh-btn:hover {
  background: rgba(0, 0, 0, 0.04);
  color: var(--text-primary);
}

.cron-no-runs {
  padding: 24px 14px;
  font-size: 13px;
  color: var(--text-muted);
  text-align: center;
}

.cron-run-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  cursor: pointer;
  border-bottom: 1px solid var(--border-subtle);
  transition: all 0.12s;
}

.cron-run-item:hover {
  background: rgba(0, 0, 0, 0.02);
}

.cron-run-item.selected {
  background: var(--color-accent-subtle);
  border-left: 3px solid var(--color-accent);
}

.cron-run-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.cron-run-dot.completed { background: var(--color-success); }
.cron-run-dot.failed { background: #e74c3c; }
.cron-run-dot.running { background: #1976d2; }

.cron-run-info {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.cron-run-time {
  font-size: 12px;
  color: var(--text-primary);
}

.cron-run-status {
  font-size: 11px;
  color: var(--text-muted);
}

.cron-run-status.completed { color: var(--color-success); }
.cron-run-status.failed { color: #e74c3c; }
.cron-run-status.running { color: #1976d2; }

/* ── Conversation Area ── */
.cron-conversation {
  flex: 1;
  overflow: hidden;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.cron-empty-hint {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: var(--text-muted);
  font-size: 14px;
}

/* ── Cron Messages (reuses agent .message classes, only layout overrides) ── */
.cron-messages {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
  padding: 20px 28px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 确保 cron 区域内的 agent 消息样式正确适配 */
.cron-conversation .message-body {
  max-width: 85%;
}

.cron-conversation .final-response {
  margin-top: 8px;
}

/* ── Cron Input Area ── */
.cron-input-area {
  padding: 12px 20px;
  border-top: 1px solid var(--border-subtle);
  background: var(--color-surface);
  flex-shrink: 0;
}

.cron-input-area .input-wrapper {
  display: flex;
  gap: 10px;
  align-items: flex-end;
}

.cron-input-area .input-wrapper :deep(.el-textarea__inner) {
  border-radius: 12px !important;
  padding: 10px 16px;
  font-size: 14px;
  box-shadow: none;
  border: 1px solid var(--border-subtle);
  resize: none;
}

/* textarea 占满剩余宽度 */
.chat-input {
  flex: 1;
  min-width: 0;
}

.cron-input-area .input-wrapper :deep(.el-textarea__inner:focus) {
  border-color: var(--color-accent);
}

/* ═══ Plan mode 顶部状态横幅 ═══ */
.plan-mode-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 20px;
  background: linear-gradient(135deg, rgba(176, 141, 71, 0.12) 0%, rgba(176, 141, 71, 0.05) 100%);
  border-bottom: 1px solid rgba(176, 141, 71, 0.25);
  flex-shrink: 0;
  position: sticky;
  top: 0;
  z-index: 10;
  backdrop-filter: blur(8px);
}

.plan-banner-left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.plan-banner-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: rgba(176, 141, 71, 0.15);
  color: var(--color-accent);
  flex-shrink: 0;
}

.plan-banner-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.plan-banner-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-accent);
  font-family: var(--font-display);
  line-height: 1.3;
}

.plan-banner-desc {
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.3;
}

.plan-banner-close {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 5px 12px;
  border-radius: 7px;
  border: 1px solid rgba(176, 141, 71, 0.30);
  background: transparent;
  color: var(--color-accent);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  flex-shrink: 0;
  transition: all 0.15s ease;
  white-space: nowrap;
}

.plan-banner-close:hover {
  background: rgba(176, 141, 71, 0.15);
  border-color: var(--color-accent);
}

/* 横幅进入/离开动画 */
.plan-banner-enter-active,
.plan-banner-leave-active {
  transition: all 0.25s ease;
}

.plan-banner-enter-from,
.plan-banner-leave-to {
  opacity: 0;
  transform: translateY(-8px);
  max-height: 0;
  padding-top: 0;
  padding-bottom: 0;
  overflow: hidden;
}

.plan-banner-enter-to,
.plan-banner-leave-from {
  opacity: 1;
  transform: translateY(0);
  max-height: 80px;
}

/* ═══ Plan mode 整体视觉变化 ═══ */
.chat-main.is-plan-mode {
  box-shadow: -2px 0 0 0 rgba(176, 141, 71, 0.4) inset;
}
</style>
