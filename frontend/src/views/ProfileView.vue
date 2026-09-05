<template>
  <div class="profile-page">
    <!-- ════════════ Hero Banner ════════════ -->
    <div class="profile-banner">
      <div class="banner-pattern"></div>
      <div class="banner-content">
        <div class="initial-circle">
          {{ displayName.charAt(0)?.toUpperCase() || '?' }}
        </div>
        <div class="banner-text">
          <h1 class="banner-name">{{ displayName }}</h1>
          <div class="banner-meta">
            <span class="meta-badge" :class="profile?.role || 'viewer'">{{ roleLabel }}</span>
            <span class="meta-sep">·</span>
            <span class="meta-item">
              <el-icon :size="13"><User /></el-icon>
              @{{ profile?.username }}
            </span>
            <span class="meta-sep">·</span>
            <span class="meta-item">
              <el-icon :size="13"><Calendar /></el-icon>
              加入 {{ accountAgeDays }} 天
            </span>
          </div>
          <p v-if="profile?.bio" class="banner-bio">{{ profile.bio }}</p>
        </div>
      </div>
    </div>

    <!-- ════════════ Tab 导航 ════════════ -->
    <nav class="tab-nav">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        :class="['tab-btn', { active: activeTab === tab.key }]"
        @click="activeTab = tab.key"
      >
        <el-icon :size="15"><component :is="tab.icon" /></el-icon>
        <span>{{ tab.label }}</span>
      </button>
    </nav>

    <!-- ════════════ Tab 内容 ════════════ -->
    <div class="tab-content">

      <!-- ──── 投资统计 ──── -->
      <div v-if="activeTab === 'stats'" v-loading="statsLoading">
        <div class="stat-grid stagger-children">
          <StatCard
            label="策略数量"
            :value="stats?.total_strategies ?? 0"
            :icon="Briefcase"
            icon-color="#b08d47"
            suffix="个策略"
          />
          <StatCard
            label="成交笔数"
            :value="stats?.total_trades ?? 0"
            :icon="Document"
            icon-color="#2563eb"
            suffix="笔成交"
          />
          <StatCard
            label="总已实现盈亏"
            :value="formatMoney(stats?.total_realized_pnl ?? 0)"
            :icon="TrendCharts"
            :icon-color="pnlColor(stats?.total_realized_pnl ?? 0)"
            :value-color="pnlColor(stats?.total_realized_pnl ?? 0)"
          />
          <StatCard
            label="账户年龄"
            :value="accountAgeDays"
            :icon="Calendar"
            icon-color="#7c3aed"
            suffix="天"
          />
        </div>

        <div class="highlight-row stagger-children">
          <div class="highlight-card best">
            <div class="highlight-indicator"></div>
            <div class="highlight-body">
              <div class="highlight-label">
                <el-icon :size="14"><TrophyBase /></el-icon>
                最佳策略
              </div>
              <div v-if="stats?.best_strategy" class="highlight-data">
                <span class="highlight-name">{{ stats.best_strategy.name }}</span>
                <span class="highlight-value profit">
                  {{ formatMoney(stats.best_strategy.value) }}
                </span>
              </div>
              <div v-else class="highlight-empty">暂无数据</div>
            </div>
          </div>

          <div class="highlight-card best">
            <div class="highlight-indicator"></div>
            <div class="highlight-body">
              <div class="highlight-label">
                <el-icon :size="14"><TopRight /></el-icon>
                涨幅最好
              </div>
              <div v-if="stats?.best_stock" class="highlight-data">
                <span class="highlight-name">{{ stats.best_stock.name }}</span>
                <span class="highlight-value profit">
                  +{{ formatMoney(stats.best_stock.value) }}
                </span>
              </div>
              <div v-else class="highlight-empty">暂无数据</div>
            </div>
          </div>

          <div class="highlight-card worst">
            <div class="highlight-indicator"></div>
            <div class="highlight-body">
              <div class="highlight-label">
                <el-icon :size="14"><BottomRight /></el-icon>
                亏损最大
              </div>
              <div v-if="stats?.worst_stock" class="highlight-data">
                <span class="highlight-name">{{ stats.worst_stock.name }}</span>
                <span class="highlight-value loss">
                  {{ formatMoney(stats.worst_stock.value) }}
                </span>
              </div>
              <div v-else class="highlight-empty">暂无数据</div>
            </div>
          </div>
        </div>

        <div v-if="profile?.bio" class="bio-showcase">
          <div class="bio-showcase-header">
            <el-icon :size="16"><EditPen /></el-icon>
            <span>投资经验</span>
          </div>
          <p class="bio-showcase-text">{{ profile.bio }}</p>
        </div>
      </div>

      <!-- ──── 个人信息 ──── -->
      <div v-if="activeTab === 'info'" class="info-sections">
        <!-- 基本信息 -->
        <section class="info-card">
          <div class="card-header">
            <div class="card-title">
              <div class="card-icon" style="--icon-bg: rgba(176,141,71,0.1); --icon-color: #b08d47">
                <el-icon :size="17"><User /></el-icon>
              </div>
              <h3>基本信息</h3>
            </div>
          </div>
          <div class="card-body">
            <div class="field-grid three-col">
              <div class="field">
                <label class="field-label">昵称</label>
                <div class="input-wrap">
                  <el-icon class="input-icon"><User /></el-icon>
                  <input
                    v-model="profileForm.nickname"
                    class="custom-input"
                    placeholder="给自己取个名字"
                    maxlength="50"
                  />
                </div>
              </div>
              <div class="field">
                <label class="field-label">邮箱</label>
                <div class="input-wrap">
                  <el-icon class="input-icon"><Message /></el-icon>
                  <input
                    v-model="profileForm.email"
                    class="custom-input"
                    placeholder="your@email.com"
                    maxlength="100"
                  />
                </div>
                <span v-if="fieldErrors.email" class="field-error">{{ fieldErrors.email }}</span>
              </div>
              <div class="field">
                <label class="field-label">手机号</label>
                <div class="input-wrap">
                  <el-icon class="input-icon"><Phone /></el-icon>
                  <input
                    v-model="profileForm.phone"
                    class="custom-input"
                    placeholder="联系电话"
                    maxlength="20"
                  />
                </div>
                <span v-if="fieldErrors.phone" class="field-error">{{ fieldErrors.phone }}</span>
              </div>
            </div>
          </div>
        </section>

        <!-- 交易画像 -->
        <section class="info-card">
          <div class="card-header">
            <div class="card-title">
              <div class="card-icon" style="--icon-bg: rgba(37,99,235,0.08); --icon-color: #2563eb">
                <el-icon :size="17"><TrendCharts /></el-icon>
              </div>
              <h3>交易画像</h3>
            </div>
          </div>
          <div class="card-body">
            <div class="field-grid two-col">
              <div class="field">
                <label class="field-label">投资风格</label>
                <div class="input-wrap select-wrap">
                  <el-icon class="input-icon"><Compass /></el-icon>
                  <select v-model="profileForm.investment_style" class="custom-input custom-select">
                    <option value="">未设置</option>
                    <option value="价值投资">价值投资</option>
                    <option value="短线交易">短线交易</option>
                    <option value="量化对冲">量化对冲</option>
                    <option value="趋势跟踪">趋势跟踪</option>
                    <option value="其他">其他</option>
                  </select>
                </div>
              </div>
              <div class="field">
                <label class="field-label">风险偏好</label>
                <div class="input-wrap select-wrap">
                  <el-icon class="input-icon"><Aim /></el-icon>
                  <select v-model="profileForm.risk_level" class="custom-input custom-select">
                    <option value="">未设置</option>
                    <option value="conservative">🛡️ 稳健型</option>
                    <option value="moderate">⚖️ 平衡型</option>
                    <option value="aggressive">🔥 激进型</option>
                  </select>
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- 个人简介 -->
        <section class="info-card">
          <div class="card-header">
            <div class="card-title">
              <div class="card-icon" style="--icon-bg: rgba(124,58,237,0.08); --icon-color: #7c3aed">
                <el-icon :size="17"><EditPen /></el-icon>
              </div>
              <h3>个人简介</h3>
            </div>
            <span class="char-count" :class="{ warn: profileForm.bio.length > 1800 }">
              {{ profileForm.bio.length }} / 2000
            </span>
          </div>
          <div class="card-body">
            <textarea
              v-model="profileForm.bio"
              class="custom-textarea"
              placeholder="分享你的投资心得、策略经验、市场感悟..."
              maxlength="2000"
              rows="5"
            ></textarea>
          </div>
        </section>

        <!-- 操作栏 -->
        <div class="form-actions">
          <button class="btn btn-ghost" @click="resetProfileForm" :disabled="saving">
            重置
          </button>
          <button class="btn btn-primary" @click="saveProfile" :disabled="saving">
            <el-icon v-if="saving" class="is-loading"><Loading /></el-icon>
            {{ saving ? '保存中...' : '保存修改' }}
          </button>
        </div>
      </div>

      <!-- ──── AI 记忆 ──── -->
      <div v-if="activeTab === 'memory'" class="info-sections">
        <!-- 交易画像（AI 自动学习） -->
        <section class="info-card">
          <div class="card-header">
            <div class="card-title">
              <div class="card-icon" style="--icon-bg: rgba(230,162,60,0.1); --icon-color: #e6a23c">
                <el-icon :size="17"><MagicStick /></el-icon>
              </div>
              <h3>AI 了解的我</h3>
            </div>
            <span class="memory-hint">AI 从你的对话中自动学习，也可以手动编辑</span>
          </div>
          <div class="card-body">
            <!-- 交易风格 -->
            <div class="memory-field">
              <label class="memory-label">交易风格</label>
              <div class="memory-tag-group">
                <button
                  v-for="opt in TRADING_STYLE_OPTIONS"
                  :key="opt.value"
                  :class="['memory-tag', { active: memProfile?.trading_style === opt.value }]"
                  @click="toggleProfileField('trading_style', opt.value)"
                >
                  {{ opt.label }}
                </button>
                <span v-if="!memProfile?.trading_style" class="memory-empty">未设置</span>
              </div>
            </div>
            <!-- 风险偏好 -->
            <div class="memory-field">
              <label class="memory-label">风险偏好</label>
              <div class="memory-tag-group">
                <button
                  v-for="opt in RISK_LEVEL_OPTIONS"
                  :key="opt.value"
                  :class="['memory-tag', { active: memProfile?.risk_level === opt.value }]"
                  @click="toggleProfileField('risk_level', opt.value)"
                >
                  {{ opt.label }}
                </button>
                <span v-if="!memProfile?.risk_level" class="memory-empty">未设置</span>
              </div>
            </div>
            <!-- 关注板块 -->
            <div class="memory-field">
              <label class="memory-label">关注板块</label>
              <div class="memory-tag-group">
                <span
                  v-for="sector in (memProfile?.focus_sectors || [])"
                  :key="sector"
                  class="memory-tag active"
                >
                  {{ sector }}
                  <el-icon class="tag-close" @click="removeFromArray('focus_sectors', sector)"><CircleClose /></el-icon>
                </span>
                <input
                  v-model="newSector"
                  class="memory-tag-input"
                  placeholder="+ 添加"
                  @keydown.enter="addToArray('focus_sectors', newSector); newSector = ''"
                />
              </div>
            </div>
            <!-- 关注个股 -->
            <div class="memory-field">
              <label class="memory-label">关注个股</label>
              <div class="memory-tag-group">
                <span
                  v-for="stock in (memProfile?.focus_stocks || [])"
                  :key="stock"
                  class="memory-tag active"
                >
                  {{ stock }}
                  <el-icon class="tag-close" @click="removeFromArray('focus_stocks', stock)"><CircleClose /></el-icon>
                </span>
                <input
                  v-model="newStock"
                  class="memory-tag-input"
                  placeholder="+ 添加（如 002594.SZ）"
                  @keydown.enter="addToArray('focus_stocks', newStock); newStock = ''"
                />
              </div>
            </div>
            <!-- 偏好指标 -->
            <div class="memory-field">
              <label class="memory-label">常用指标</label>
              <div class="memory-tag-group">
                <span
                  v-for="ind in (memProfile?.indicators || [])"
                  :key="ind"
                  class="memory-tag active"
                >
                  {{ ind }}
                  <el-icon class="tag-close" @click="removeFromArray('indicators', ind)"><CircleClose /></el-icon>
                </span>
                <input
                  v-model="newIndicator"
                  class="memory-tag-input"
                  placeholder="+ 添加（如 MACD）"
                  @keydown.enter="addToArray('indicators', newIndicator); newIndicator = ''"
                />
              </div>
            </div>
          </div>
        </section>

        <!-- AI 笔记 -->
        <section class="info-card">
          <div class="card-header">
            <div class="card-title">
              <div class="card-icon" style="--icon-bg: rgba(64,158,255,0.08); --icon-color: #409eff">
                <el-icon :size="17"><Document /></el-icon>
              </div>
              <h3>AI 笔记 ({{ memMemories.length }})</h3>
            </div>
            <div class="card-header-actions">
              <!-- 分类过滤 -->
              <select v-model="memFilter" class="memory-filter-select">
                <option value="">全部分类</option>
                <option v-for="cat in CATEGORY_OPTIONS" :key="cat.value" :value="cat.value">
                  {{ cat.label }}
                </option>
              </select>
              <button class="btn btn-small btn-ghost" @click="showAddMemory = true">
                + 添加笔记
              </button>
            </div>
          </div>
          <div class="card-body">
            <div v-if="filteredMemories.length === 0" class="memory-empty-state">
              <el-icon :size="32" color="#c0c4cc"><Document /></el-icon>
              <p>暂无笔记。与 AI 助手交流时，它会自动记录你的偏好和观察。</p>
            </div>
            <div v-else class="memory-list">
              <div v-for="mem in filteredMemories" :key="mem.id" class="memory-item">
                <div class="memory-item-header">
                  <span class="memory-category" :style="{ backgroundColor: categoryMeta(mem.category).color + '18', color: categoryMeta(mem.category).color }">
                    {{ categoryMeta(mem.category).label }}
                  </span>
                  <span class="memory-source">{{ mem.source === 'auto' ? 'AI 提取' : '手动添加' }}</span>
                  <span class="memory-date">{{ formatDate(mem.created_at) }}</span>
                  <button class="memory-delete" @click="deleteMemoryItem(mem.id)">
                    <el-icon :size="14"><CircleClose /></el-icon>
                  </button>
                </div>
                <p class="memory-content">{{ mem.content }}</p>
              </div>
            </div>
          </div>
        </section>

        <!-- 添加记忆对话框 -->
        <Teleport to="body">
          <div v-if="showAddMemory" class="modal-overlay" @click.self="showAddMemory = false">
            <div class="modal-box">
              <h3>添加笔记</h3>
              <div class="modal-field">
                <label>分类</label>
                <select v-model="newMemCategory" class="custom-input custom-select">
                  <option v-for="cat in CATEGORY_OPTIONS" :key="cat.value" :value="cat.value">
                    {{ cat.label }}
                  </option>
                </select>
              </div>
              <div class="modal-field">
                <label>内容</label>
                <textarea
                  v-model="newMemContent"
                  class="custom-textarea"
                  placeholder="例如：回测发现20日均线在创业板效果较好"
                  rows="3"
                ></textarea>
              </div>
              <div class="modal-actions">
                <button class="btn btn-ghost" @click="showAddMemory = false">取消</button>
                <button class="btn btn-primary" @click="addMemoryItem" :disabled="!newMemContent.trim()">
                  添加
                </button>
              </div>
            </div>
          </div>
        </Teleport>
      </div>

      <!-- ──── 我的权限 ──── -->
      <div v-if="activeTab === 'permissions'" class="info-sections">
        <section class="info-card">
          <div class="card-header">
            <div class="card-title">
              <div class="card-icon" style="--icon-bg: rgba(176,141,71,0.1); --icon-color: #b08d47">
                <el-icon :size="17"><Setting /></el-icon>
              </div>
              <h3>功能权限</h3>
            </div>
            <span class="perm-note">如需调整，请联系管理员</span>
          </div>
          <div class="card-body">
            <div class="perm-list">
              <div class="perm-row">
                <div class="perm-info">
                  <el-icon :size="18" class="perm-icon"><ChatDotRound /></el-icon>
                  <div>
                    <div class="perm-name">AI Agent</div>
                    <div class="perm-desc">使用 AI 助手进行对话、分析和任务处理</div>
                  </div>
                </div>
                <span :class="['perm-badge', authStore.canUseAgent ? 'perm-on' : 'perm-off']">
                  <el-icon :size="13"><component :is="authStore.canUseAgent ? CircleCheck : CircleClose" /></el-icon>
                  {{ authStore.canUseAgent ? '已开通' : '未开通' }}
                </span>
              </div>

              <div class="perm-row">
                <div class="perm-info">
                  <el-icon :size="18" class="perm-icon"><TrendCharts /></el-icon>
                  <div>
                    <div class="perm-name">创建实盘策略</div>
                    <div class="perm-desc">创建对接真实券商账户的交易策略</div>
                  </div>
                </div>
                <span :class="['perm-badge', authStore.canCreateReal ? 'perm-on' : 'perm-off']">
                  <el-icon :size="13"><component :is="authStore.canCreateReal ? CircleCheck : CircleClose" /></el-icon>
                  {{ authStore.canCreateReal ? '已开通' : '未开通' }}
                </span>
              </div>

              <div class="perm-row">
                <div class="perm-info">
                  <el-icon :size="18" class="perm-icon"><Briefcase /></el-icon>
                  <div>
                    <div class="perm-name">策略数量上限</div>
                    <div class="perm-desc">可同时持有的策略最大数量</div>
                  </div>
                </div>
                <span class="perm-value">
                  {{ authStore.maxStrategies === -1 ? '无限制' : `${authStore.maxStrategies} 个` }}
                </span>
              </div>

              <div class="perm-row">
                <div class="perm-info">
                  <el-icon :size="18" class="perm-icon"><Clock /></el-icon>
                  <div>
                    <div class="perm-name">定时任务</div>
                    <div class="perm-desc">创建和管理自动执行的定时任务</div>
                  </div>
                </div>
                <span :class="['perm-badge', authStore.canUseCron ? 'perm-on' : 'perm-off']">
                  <el-icon :size="13"><component :is="authStore.canUseCron ? CircleCheck : CircleClose" /></el-icon>
                  {{ authStore.canUseCron ? '已开通' : '未开通' }}
                </span>
              </div>

              <div class="perm-row">
                <div class="perm-info">
                  <el-icon :size="18" class="perm-icon"><MonitorIcon /></el-icon>
                  <div>
                    <div class="perm-name">监控任务</div>
                    <div class="perm-desc">创建和运行行情监控与告警任务</div>
                  </div>
                </div>
                <span :class="['perm-badge', authStore.canUseMonitor ? 'perm-on' : 'perm-off']">
                  <el-icon :size="13"><component :is="authStore.canUseMonitor ? CircleCheck : CircleClose" /></el-icon>
                  {{ authStore.canUseMonitor ? '已开通' : '未开通' }}
                </span>
              </div>
            </div>
          </div>
        </section>
      </div>

      <!-- ──── 我的反馈 ──── -->
      <div v-if="activeTab === 'feedback'" class="info-sections">
        <!-- 提交反馈 -->
        <section class="info-card">
          <div class="card-header">
            <div class="card-title">
              <div class="card-icon" style="--icon-bg: rgba(37,99,235,0.08); --icon-color: #2563eb">
                <el-icon :size="17"><ChatLineSquare /></el-icon>
              </div>
              <h3>提交反馈</h3>
            </div>
          </div>
          <div class="card-body">
            <div class="feedback-form">
              <div class="field">
                <label class="field-label">类型</label>
                <div class="feedback-type-row">
                  <button
                    v-for="ft in feedbackTypes"
                    :key="ft.value"
                    :class="['fb-type-btn', { active: feedbackForm.type === ft.value }]"
                    @click="feedbackForm.type = ft.value"
                  >
                    <el-icon :size="14"><component :is="ft.icon" /></el-icon>
                    {{ ft.label }}
                  </button>
                </div>
              </div>
              <div class="field">
                <label class="field-label">标题</label>
                <div class="input-wrap">
                  <el-icon class="input-icon"><EditPen /></el-icon>
                  <input
                    v-model="feedbackForm.title"
                    class="custom-input"
                    placeholder="简要描述你的问题或建议"
                    maxlength="200"
                  />
                </div>
              </div>
              <div class="field">
                <label class="field-label">详细内容</label>
                <textarea
                  v-model="feedbackForm.content"
                  class="custom-textarea"
                  placeholder="详细描述你遇到的问题、建议或疑问，帮助我们更好地改进..."
                  maxlength="5000"
                  rows="5"
                ></textarea>
                <span class="char-count" :class="{ warn: feedbackForm.content.length > 4500 }">
                  {{ feedbackForm.content.length }} / 5000
                </span>
              </div>
              <div class="form-actions">
                <button class="btn btn-primary" @click="submitFeedback" :disabled="fbSubmitting">
                  <el-icon v-if="fbSubmitting" class="is-loading"><Loading /></el-icon>
                  {{ fbSubmitting ? '提交中...' : '提交反馈' }}
                </button>
              </div>
            </div>
          </div>
        </section>

        <!-- 历史反馈 -->
        <section class="info-card">
          <div class="card-header">
            <div class="card-title">
              <div class="card-icon" style="--icon-bg: rgba(176,141,71,0.1); --icon-color: #b08d47">
                <el-icon :size="17"><Document /></el-icon>
              </div>
              <h3>历史反馈</h3>
            </div>
            <span class="char-count">{{ feedbackList.length }} 条记录</span>
          </div>
          <div class="card-body" v-loading="fbListLoading">
            <div v-if="feedbackList.length === 0 && !fbListLoading" class="fb-empty">
              <el-icon :size="40" color="#c0c4cc"><ChatLineSquare /></el-icon>
              <p>暂无反馈记录</p>
            </div>
            <div
              v-for="fb in feedbackList"
              :key="fb.id"
              :class="['fb-item', { expanded: expandedFbId === fb.id }]"
              @click="toggleFbDetail(fb.id)"
            >
              <div class="fb-item-header">
                <div class="fb-item-left">
                  <span :class="['fb-status-dot', fb.status]"></span>
                  <span class="fb-title">{{ fb.title }}</span>
                </div>
                <div class="fb-item-right">
                  <span :class="['fb-type-tag', fb.type]">{{ fbTypeLabel(fb.type) }}</span>
                  <span :class="['fb-status-tag', fb.status]">{{ fbStatusLabel(fb.status) }}</span>
                  <span class="fb-time">{{ formatTime(fb.created_at) }}</span>
                </div>
              </div>
              <div v-if="expandedFbId === fb.id" class="fb-item-detail">
                <div class="fb-content">{{ fb.content }}</div>
                <div v-if="fb.admin_reply" class="fb-reply">
                  <div class="fb-reply-header">
                    <el-icon :size="14"><ChatDotRound /></el-icon>
                    <span>管理员回复</span>
                    <span v-if="fb.replied_at" class="fb-reply-time">{{ formatTime(fb.replied_at) }}</span>
                  </div>
                  <div class="fb-reply-content">{{ fb.admin_reply }}</div>
                </div>
                <div v-else class="fb-no-reply">
                  <el-icon :size="14"><Clock /></el-icon>
                  <span>等待回复中...</span>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>

      <!-- ──── API Token ──── -->
      <div v-if="activeTab === 'api-tokens'">
        <div class="api-tokens-section">
          <div class="section-header">
            <div>
              <h3>API Token</h3>
              <p class="section-desc">通过 API Token 接入平台，对自己的策略进行查看持仓、下单和撤单操作。可选择全部策略或指定策略。</p>
            </div>
            <el-button type="primary" size="small" @click="showCreateToken = true">
              <el-icon><EditPen /></el-icon>
              创建 Token
            </el-button>
          </div>

          <div v-loading="tokensLoading" class="token-list-profile">
            <div v-if="apiTokens.length === 0 && !tokensLoading" class="token-empty">
              暂无 API Token，点击上方按钮创建
            </div>

            <div v-for="tok in apiTokens" :key="tok.id" class="token-item" :class="{ disabled: !tok.is_active }">
              <div class="token-item-header">
                <span class="token-name">{{ tok.name || '未命名' }}</span>
                <el-tag size="small" :type="tok.is_active ? 'success' : 'danger'">
                  {{ tok.is_active ? '启用' : '已禁用' }}
                </el-tag>
              </div>
              <div class="token-meta">
                <span>范围：{{ tok.scope_type === 'all' ? '全部策略' : `指定策略 (${tok.scope_strategies.length})` }}</span>
                <span v-if="tok.require_confirm">
                  <el-icon :size="11" style="vertical-align: middle;"><Warning /></el-icon>
                  下单需确认
                </span>
                <span>限速：{{ tok.rate_limit === 0 ? '不限' : tok.rate_limit + ' 次/分' }}</span>
                <span>创建：{{ formatDateToken(tok.created_at) }}</span>
                <span v-if="tok.last_used_at">最后使用：{{ formatDateToken(tok.last_used_at) }}</span>
                <span v-if="tok.expires_at">过期：{{ formatDateToken(tok.expires_at) }}</span>
              </div>
              <div class="token-actions">
                <el-button size="small" text @click="toggleTokenActive(tok)">
                  {{ tok.is_active ? '禁用' : '启用' }}
                </el-button>
                <el-popconfirm title="确定删除此 Token？" @confirm="deleteToken(tok.id)">
                  <template #reference>
                    <el-button size="small" text type="danger">删除</el-button>
                  </template>
                </el-popconfirm>
              </div>
            </div>
          </div>
        </div>

        <!-- 创建 Token 弹窗 -->
        <el-dialog v-model="showCreateToken" title="创建 API Token" width="460px">
          <el-form :model="tokenForm" label-width="80px">
            <el-form-item label="名称">
              <el-input v-model="tokenForm.name" placeholder="例如: 我的交易脚本" maxlength="100" />
            </el-form-item>
            <el-form-item label="策略范围">
              <el-radio-group v-model="tokenForm.scope_type">
                <el-radio value="all">全部策略</el-radio>
                <el-radio value="listed">指定策略</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item v-if="tokenForm.scope_type === 'listed'" label="选择策略">
              <el-select
                v-model="tokenForm.scope_strategies"
                multiple
                filterable
                placeholder="选择策略"
                style="width: 100%"
              >
                <el-option
                  v-for="s in myStrategies"
                  :key="s.strategy_id"
                  :label="`${s.name} (${s.strategy_id})`"
                  :value="s.strategy_id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="有效期">
              <el-select v-model="tokenForm.expires_days" style="width: 100%">
                <el-option :value="null" label="永不过期" />
                <el-option :value="30" label="30 天" />
                <el-option :value="90" label="90 天" />
                <el-option :value="365" label="1 年" />
              </el-select>
            </el-form-item>
            <el-form-item label="限速">
              <el-input-number v-model="tokenForm.rate_limit" :min="0" :max="1000" :step="10" />
              <span style="margin-left: 8px; color: rgba(255,255,255,0.4); font-size: 12px">次/分钟，0=不限</span>
            </el-form-item>
            <el-form-item label="下单确认">
              <el-switch v-model="tokenForm.require_confirm" />
              <span style="margin-left: 8px; color: rgba(255,255,255,0.4); font-size: 12px">开启后，该 Token 的下单请求需在前端确认</span>
            </el-form-item>
          </el-form>
          <template #footer>
            <el-button @click="showCreateToken = false">取消</el-button>
            <el-button type="primary" :loading="creatingToken" @click="doCreateToken">创建</el-button>
          </template>
        </el-dialog>

        <!-- Token 创建成功弹窗 -->
        <el-dialog v-model="showTokenResult" title="Token 创建成功" width="460px" :close-on-click-modal="false">
          <el-alert type="warning" :closable="false" show-icon style="margin-bottom: 12px">
            <template #title>请立即复制保存，关闭后无法再次查看！</template>
          </el-alert>
          <div class="token-result-box">
            <code class="token-value">{{ createdTokenValue }}</code>
            <el-button size="small" @click="copyTokenValue">复制</el-button>
          </div>
          <template #footer>
            <el-button type="primary" @click="showTokenResult = false">我已保存</el-button>
          </template>
        </el-dialog>
      </div>

      <!-- ──── 修改密码 ──── -->
      <div v-if="activeTab === 'password'" class="password-section">
        <div class="password-card">
          <div class="password-card-header">
            <h3>修改密码</h3>
            <p>定期修改密码有助于保护账户安全</p>
          </div>
          <div class="password-fields">
            <div class="field">
              <label class="field-label">当前密码</label>
              <div class="input-wrap">
                <el-icon class="input-icon"><Lock /></el-icon>
                <input
                  v-model="passwordForm.old_password"
                  type="password"
                  class="custom-input"
                  placeholder="输入当前密码"
                  maxlength="128"
                />
              </div>
              <span v-if="fieldErrors.old_password" class="field-error">{{ fieldErrors.old_password }}</span>
            </div>
            <div class="field">
              <label class="field-label">新密码</label>
              <div class="input-wrap">
                <el-icon class="input-icon"><Lock /></el-icon>
                <input
                  v-model="passwordForm.new_password"
                  type="password"
                  class="custom-input"
                  placeholder="至少8位，含字母和数字"
                  maxlength="128"
                />
              </div>
              <span v-if="fieldErrors.new_password" class="field-error">{{ fieldErrors.new_password }}</span>
            </div>
            <div class="field">
              <label class="field-label">确认新密码</label>
              <div class="input-wrap">
                <el-icon class="input-icon"><Lock /></el-icon>
                <input
                  v-model="passwordForm.confirm_password"
                  type="password"
                  class="custom-input"
                  placeholder="再次输入新密码"
                  maxlength="128"
                />
              </div>
              <span v-if="fieldErrors.confirm_password" class="field-error">{{ fieldErrors.confirm_password }}</span>
            </div>
          </div>
          <div class="form-actions">
            <button class="btn btn-primary" @click="doChangePassword" :disabled="changingPw">
              <el-icon v-if="changingPw" class="is-loading"><Loading /></el-icon>
              {{ changingPw ? '修改中...' : '修改密码' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch, type Component } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { showApiError } from '@/utils/notify'
import { useAuthStore } from '@/stores/auth'
import * as profileApi from '@/api/profile'
import type { UserProfile, InvestmentStats } from '@/types/auth'
import StatCard from '@/components/common/StatCard.vue'
import {
  User, Message, Phone, Calendar, Lock,
  Briefcase, Document, TrendCharts, EditPen,
  Compass, Aim, Loading,
  TrophyBase, TopRight, BottomRight,
  Setting, ChatDotRound, Clock, Monitor as MonitorIcon,
  CircleCheck, CircleClose, ChatLineSquare,
  MagicStick, Key, Warning,
} from '@element-plus/icons-vue'
import { memoryApi } from '@/api/memory'
import type { UserProfile as MemoryProfile, UserMemory } from '@/types/memory'
import {
  TRADING_STYLE_OPTIONS,
  RISK_LEVEL_OPTIONS,
  CATEGORY_OPTIONS,
  getCategoryMeta,
  type CategoryMeta,
} from '@/types/memory'
import {
  listApiTokens,
  createApiToken,
  updateApiToken,
  deleteApiToken,
  type ApiToken,
} from '@/api/apiTokens'

const authStore = useAuthStore()
const route = useRoute()

// ── Tab 配置 ──
const tabs: { key: string; label: string; icon: Component }[] = [
  { key: 'stats', label: '投资统计', icon: TrendCharts },
  { key: 'info', label: '个人信息', icon: User },
  { key: 'memory', label: 'AI 记忆', icon: MagicStick },
  { key: 'permissions', label: '我的权限', icon: Setting },
  { key: 'api-tokens', label: 'API Token', icon: Key },
  { key: 'feedback', label: '我的反馈', icon: ChatLineSquare },
  { key: 'password', label: '修改密码', icon: Lock },
]

// ── 数据状态 ──
const profile = ref<UserProfile | null>(null)
const stats = ref<InvestmentStats | null>(null)
const activeTab = ref('stats')
const saving = ref(false)
const statsLoading = ref(false)
const changingPw = ref(false)
const fieldErrors = reactive<Record<string, string>>({})

const profileForm = ref({
  nickname: '',
  email: '',
  phone: '',
  bio: '',
  investment_style: '',
  risk_level: '',
})

const passwordForm = ref({
  old_password: '',
  new_password: '',
  confirm_password: '',
})

// ── 计算属性 ──
const displayName = computed(() =>
  profile.value?.nickname || profile.value?.username || authStore.user?.username || '用户',
)

const roleLabel = computed(() => {
  const map: Record<string, string> = { admin: '管理员', trader: '交易员', viewer: '观察者' }
  return map[profile.value?.role || ''] || profile.value?.role || ''
})

const accountAgeDays = computed(() => {
  if (!profile.value?.created_at) return 0
  const created = new Date(profile.value.created_at)
  const now = new Date()
  return Math.floor((now.getTime() - created.getTime()) / (1000 * 60 * 60 * 24))
})

// ── 验证 ──
function validateEmail(v: string): string | null {
  if (v && !v.includes('@')) return '请输入有效的邮箱地址'
  return null
}

function validatePhone(v: string): string | null {
  if (v && !/^[\d\-+() ]{5,20}$/.test(v)) return '手机号格式无效'
  return null
}

function validateProfileFields(): boolean {
  fieldErrors.email = validateEmail(profileForm.value.email) || ''
  fieldErrors.phone = validatePhone(profileForm.value.phone) || ''
  return !fieldErrors.email && !fieldErrors.phone
}

function validatePasswordFields(): boolean {
  fieldErrors.old_password = ''
  fieldErrors.new_password = ''
  fieldErrors.confirm_password = ''
  let ok = true
  if (!passwordForm.value.old_password) {
    fieldErrors.old_password = '请输入当前密码'; ok = false
  }
  if (!passwordForm.value.new_password) {
    fieldErrors.new_password = '请输入新密码'; ok = false
  } else if (passwordForm.value.new_password.length < 8) {
    fieldErrors.new_password = '密码长度不能少于 8 位'; ok = false
  } else if (passwordForm.value.new_password.length > 128) {
    fieldErrors.new_password = '密码长度不能超过 128 位'; ok = false
  } else if (!/[a-zA-Z]/.test(passwordForm.value.new_password)) {
    fieldErrors.new_password = '密码必须包含至少一个字母'; ok = false
  } else if (!/[0-9]/.test(passwordForm.value.new_password)) {
    fieldErrors.new_password = '密码必须包含至少一个数字'; ok = false
  }
  if (!passwordForm.value.confirm_password) {
    fieldErrors.confirm_password = '请确认新密码'; ok = false
  } else if (passwordForm.value.confirm_password !== passwordForm.value.new_password) {
    fieldErrors.confirm_password = '两次输入的密码不一致'; ok = false
  }
  return ok
}

// ── 辅助函数 ──
function formatMoney(v: number): string {
  const sign = v < 0 ? '-' : ''
  const abs = Math.abs(v)
  return sign + '¥' + abs.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function pnlColor(v: number): string {
  if (v > 0) return '#dc2626'
  if (v < 0) return '#16a34a'
  return 'var(--text-primary)'
}

function categoryMeta(category: string): CategoryMeta {
  return getCategoryMeta(category)
}

// ── 数据加载 ──
async function loadProfile() {
  try {
    const res = await profileApi.getProfile()
    profile.value = res.data
    fillFormFromProfile()
  } catch (err) {
    showApiError(err, '加载个人资料失败')
  }
}

async function loadStats() {
  statsLoading.value = true
  try {
    const res = await profileApi.getInvestmentStats()
    stats.value = res.data
  } catch (err) {
    showApiError(err, '加载投资统计失败')
  } finally {
    statsLoading.value = false
  }
}

function fillFormFromProfile() {
  const p = profile.value
  if (!p) return
  profileForm.value = {
    nickname: p.nickname || '',
    email: p.email || '',
    phone: p.phone || '',
    bio: p.bio || '',
    investment_style: p.investment_style || '',
    risk_level: p.risk_level || '',
  }
}

function resetProfileForm() {
  fillFormFromProfile()
  fieldErrors.email = ''
  fieldErrors.phone = ''
}

// ── 操作 ──
async function saveProfile() {
  if (!validateProfileFields()) return

  saving.value = true
  try {
    const payload: Record<string, any> = {}
    for (const [k, v] of Object.entries(profileForm.value)) {
      if (v !== '') payload[k] = v
    }
    const res = await profileApi.updateProfile(payload)
    profile.value = res.data
    ElMessage.success('资料已更新')
  } catch (err: any) {
    showApiError(err, '保存失败')
  } finally {
    saving.value = false
  }
}

async function doChangePassword() {
  if (!validatePasswordFields()) return

  changingPw.value = true
  try {
    await profileApi.changePassword({
      old_password: passwordForm.value.old_password,
      new_password: passwordForm.value.new_password,
    })
    ElMessage.success('密码修改成功')
    passwordForm.value = { old_password: '', new_password: '', confirm_password: '' }
  } catch (err: any) {
    showApiError(err, '修改失败')
  } finally {
    changingPw.value = false
  }
}

// ── 反馈 ──
import * as feedbackApi from '@/api/feedback'
import type { FeedbackDetail } from '@/types/feedback'
import { ChatDotSquare, QuestionFilled, MoreFilled as MoreFilledIcon } from '@element-plus/icons-vue'

const feedbackTypes = [
  { value: 'bug', label: 'Bug', icon: Warning },
  { value: 'feature', label: '功能建议', icon: ChatDotSquare },
  { value: 'question', label: '使用问题', icon: QuestionFilled },
  { value: 'other', label: '其他', icon: MoreFilledIcon },
]

const feedbackForm = reactive({
  type: 'other',
  title: '',
  content: '',
})
const fbSubmitting = ref(false)
const feedbackList = ref<FeedbackDetail[]>([])
const fbListLoading = ref(false)
const expandedFbId = ref<number | null>(null)

function fbTypeLabel(type: string): string {
  const map: Record<string, string> = { bug: 'Bug', feature: '功能建议', question: '使用问题', other: '其他' }
  return map[type] || type
}

function fbStatusLabel(status: string): string {
  const map: Record<string, string> = { pending: '待处理', in_progress: '处理中', resolved: '已解决', closed: '已关闭' }
  return map[status] || status
}

function formatTime(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const diff = Math.max(0, now.getTime() - d.getTime())
  if (diff < 60_000) return '刚刚'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`
  if (diff < 86_400_000 * 7) return `${Math.floor(diff / 86_400_000)} 天前`
  return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

function toggleFbDetail(id: number) {
  expandedFbId.value = expandedFbId.value === id ? null : id
}

async function submitFeedback() {
  if (!feedbackForm.title.trim()) {
    ElMessage.warning('请输入标题')
    return
  }
  if (!feedbackForm.content.trim()) {
    ElMessage.warning('请输入详细内容')
    return
  }
  fbSubmitting.value = true
  try {
    await feedbackApi.submitFeedback({
      type: feedbackForm.type,
      title: feedbackForm.title,
      content: feedbackForm.content,
    })
    ElMessage.success('反馈已提交，感谢你的意见！')
    feedbackForm.title = ''
    feedbackForm.content = ''
    feedbackForm.type = 'other'
    loadFeedbackList()
  } catch (err: any) {
    showApiError(err, '提交失败')
  } finally {
    fbSubmitting.value = false
  }
}

async function loadFeedbackList() {
  fbListLoading.value = true
  try {
    const listRes = await feedbackApi.listMyFeedback()
    // 对每条加载详情（含管理员回复）
    const details = await Promise.all(
      listRes.data.map(fb => feedbackApi.getFeedback(fb.id).then(r => r.data).catch(() => fb as FeedbackDetail)),
    )
    feedbackList.value = details
  } catch {
    // ignore
  } finally {
    fbListLoading.value = false
  }
}

// ── Tab 切换时加载统计 ──
watch(activeTab, (tab) => {
  if (tab === 'stats' && !stats.value) {
    loadStats()
  }
  if (tab === 'feedback' && feedbackList.value.length === 0) {
    loadFeedbackList()
  }
  if (tab === 'memory' && !memProfile.value) {
    loadMemoryData()
  }
})

// ── AI 记忆相关 ──
const memProfile = ref<MemoryProfile | null>(null)
const memMemories = ref<UserMemory[]>([])
const memFilter = ref('')
const memLoading = ref(false)
const showAddMemory = ref(false)
const newMemCategory = ref('observation')
const newMemContent = ref('')
const newSector = ref('')
const newStock = ref('')
const newIndicator = ref('')

const filteredMemories = computed(() => {
  if (!memFilter.value) return memMemories.value
  return memMemories.value.filter(m => m.category === memFilter.value)
})

async function loadMemoryData() {
  memLoading.value = true
  try {
    const [profileRes, memoriesRes] = await Promise.all([
      memoryApi.getProfile(),
      memoryApi.getMemories(),
    ])
    memProfile.value = profileRes.data
    memMemories.value = memoriesRes.data.memories || []
  } catch {
    // 静默失败
  } finally {
    memLoading.value = false
  }
}

async function toggleProfileField(field: string, value: string) {
  if (!memProfile.value) return
  const current = (memProfile.value as Record<string, unknown>)[field]
  const newVal = current === value ? null : value
  try {
    const res = await memoryApi.updateProfile({ [field]: newVal })
    memProfile.value = res.data
  } catch (err) {
    showApiError(err, '更新失败')
  }
}

async function addToArray(field: string, value: string) {
  if (!value.trim() || !memProfile.value) return
  const current = (memProfile.value as unknown as Record<string, string[] | undefined>)[field]
  const arr = [...(current || [])]
  if (arr.includes(value.trim())) return
  arr.push(value.trim())
  try {
    const res = await memoryApi.updateProfile({ [field]: arr })
    memProfile.value = res.data
  } catch (err) {
    showApiError(err, '更新失败')
  }
}

async function removeFromArray(field: string, value: string) {
  if (!memProfile.value) return
  const current = (memProfile.value as unknown as Record<string, string[] | undefined>)[field]
  const arr = (current || []).filter(v => v !== value)
  try {
    const res = await memoryApi.updateProfile({ [field]: arr })
    memProfile.value = res.data
  } catch (err) {
    showApiError(err, '更新失败')
  }
}

async function addMemoryItem() {
  if (!newMemContent.value.trim()) return
  try {
    await memoryApi.addMemory({
      category: newMemCategory.value,
      content: newMemContent.value.trim(),
    })
    showAddMemory.value = false
    newMemContent.value = ''
    // 刷新列表
    const res = await memoryApi.getMemories()
    memMemories.value = res.data.memories || []
    ElMessage.success('笔记已添加')
  } catch (err) {
    showApiError(err, '添加失败')
  }
}

async function deleteMemoryItem(id: number) {
  try {
    await memoryApi.deleteMemory(id)
    memMemories.value = memMemories.value.filter(m => m.id !== id)
    ElMessage.success('笔记已删除')
  } catch (err) {
    showApiError(err, '删除失败')
  }
}

function formatDate(dateStr: string | null) {
  if (!dateStr) return ''
  try {
    const d = new Date(dateStr)
    return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
  } catch {
    return ''
  }
}

// ── API Token ──
const apiTokens = ref<ApiToken[]>([])
const tokensLoading = ref(false)
const showCreateToken = ref(false)
const creatingToken = ref(false)
const showTokenResult = ref(false)
const createdTokenValue = ref('')
const tokenForm = ref({
  name: '',
  scope_type: 'all' as 'all' | 'listed',
  scope_strategies: [] as string[],
  expires_days: null as number | null,
  rate_limit: 60,
  require_confirm: false,
})

const myStrategies = ref<{ strategy_id: string; name: string }[]>([])

async function loadMyStrategies() {
  try {
    const { listStrategies } = await import('@/api/strategies')
    const res = await listStrategies()
    myStrategies.value = res.data.map((s: any) => ({
      strategy_id: s.strategy_id,
      name: s.name,
    }))
  } catch {
    // 静默
  }
}

async function loadApiTokens() {
  tokensLoading.value = true
  try {
    const res = await listApiTokens()
    apiTokens.value = res.data
  } catch (err) {
    showApiError(err, '加载 Token 列表失败')
  } finally {
    tokensLoading.value = false
  }
}

async function doCreateToken() {
  if (tokenForm.value.scope_type === 'listed' && !tokenForm.value.scope_strategies.length) {
    ElMessage.warning('选择「指定策略」时必须选择至少一个策略')
    return
  }
  creatingToken.value = true
  try {
    const res = await createApiToken(tokenForm.value)
    createdTokenValue.value = res.data.token
    showCreateToken.value = false
    showTokenResult.value = true
    tokenForm.value = { name: '', scope_type: 'all', scope_strategies: [], expires_days: null, rate_limit: 60, require_confirm: false }
    await loadApiTokens()
  } catch (err: any) {
    showApiError(err, '创建失败')
  } finally {
    creatingToken.value = false
  }
}

async function toggleTokenActive(tok: ApiToken) {
  try {
    await updateApiToken(tok.id, { is_active: !tok.is_active })
    await loadApiTokens()
  } catch (err: any) {
    showApiError(err, '操作失败')
  }
}

async function deleteToken(id: number) {
  try {
    await deleteApiToken(id)
    ElMessage.success('已删除')
    await loadApiTokens()
  } catch (err: any) {
    showApiError(err, '删除失败')
  }
}

function copyTokenValue() {
  navigator.clipboard.writeText(createdTokenValue.value).then(() => {
    ElMessage.success('已复制')
  }).catch(() => {
    ElMessage.warning('复制失败，请手动选择')
  })
}

function formatDateToken(dateStr: string | null) {
  if (!dateStr) return ''
  try {
    const d = new Date(dateStr)
    return `${d.getFullYear()}/${(d.getMonth() + 1).toString().padStart(2, '0')}/${d.getDate().toString().padStart(2, '0')}`
  } catch {
    return ''
  }
}

// ── 初始化 ──
onMounted(() => {
  loadProfile()
  // 处理侧栏跳转 ?tab=feedback
  const tab = route.query.tab as string
  if (tab && ['info', 'permissions', 'feedback', 'stats', 'password', 'memory', 'api-tokens'].includes(tab)) {
    activeTab.value = tab
  }
})

// 切换到 API Token tab 时加载数据
watch(activeTab, (val) => {
  if (val === 'api-tokens') {
    loadApiTokens()
    loadMyStrategies()
  }
})
</script>

<style scoped>
/* ═══════════════════════════════════════════════
   Profile Page
   ═══════════════════════════════════════════════ */

.profile-page {
  width: 100%;
  max-width: 860px;
  margin: 0 auto;
  padding-bottom: 40px;
}

/* ═══ Banner ═══ */

.profile-banner {
  position: relative;
  border-radius: var(--radius-xl) var(--radius-xl) var(--radius-lg) var(--radius-lg);
  overflow: hidden;
  margin-bottom: 36px;
  background: linear-gradient(135deg, #b08d47 0%, #c9a55a 40%, #d4b96a 70%, #b08d47 100%);
  min-height: 150px;
}

.banner-pattern {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 20% 50%, rgba(255,255,255,0.12) 0%, transparent 50%),
    radial-gradient(circle at 80% 20%, rgba(255,255,255,0.08) 0%, transparent 40%),
    radial-gradient(circle at 60% 80%, rgba(0,0,0,0.06) 0%, transparent 40%);
  pointer-events: none;
}

.banner-content {
  position: relative;
  display: flex;
  align-items: flex-end;
  gap: 20px;
  padding: 28px 32px 24px;
}

.initial-circle {
  width: 68px;
  height: 68px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.2);
  backdrop-filter: blur(8px);
  border: 2.5px solid rgba(255, 255, 255, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: var(--font-display);
  font-size: 28px;
  font-weight: 700;
  color: #fff;
  flex-shrink: 0;
  text-shadow: 0 1px 3px rgba(0,0,0,0.15);
}

.banner-text {
  flex: 1;
  min-width: 0;
  padding-bottom: 2px;
}

.banner-name {
  font-family: var(--font-display);
  font-size: 26px;
  font-weight: 700;
  color: #fff;
  letter-spacing: -0.01em;
  line-height: 1.2;
  margin: 0 0 6px 0;
  text-shadow: 0 1px 4px rgba(0,0,0,0.12);
}

.banner-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.85);
}

.meta-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 10px;
  border-radius: 20px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.02em;
  background: rgba(255, 255, 255, 0.2);
  backdrop-filter: blur(4px);
}

.meta-badge.admin {
  background: rgba(220, 38, 38, 0.25);
}

.meta-sep {
  opacity: 0.5;
  font-size: 11px;
}

.meta-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.banner-bio {
  margin: 8px 0 0;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.7);
  line-height: 1.5;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 500px;
}

/* ═══ Tab Navigation ═══ */

.tab-nav {
  display: flex;
  gap: 4px;
  padding: 4px;
  background: var(--color-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  margin-bottom: 24px;
}

.tab-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  padding: 10px 16px;
  border: none;
  border-radius: var(--radius-md);
  background: transparent;
  font-size: 13.5px;
  font-weight: 500;
  font-family: var(--font-body);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}

.tab-btn:hover {
  color: var(--text-primary);
  background: rgba(0, 0, 0, 0.02);
}

.tab-btn.active {
  color: var(--color-accent);
  background: rgba(176, 141, 71, 0.07);
  font-weight: 600;
  box-shadow: 0 1px 3px rgba(176, 141, 71, 0.08);
}

/* ═══ Info Cards ═══ */

.info-sections {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.info-card {
  background: var(--color-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs);
  transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
  overflow: hidden;
}

.info-card:hover {
  border-color: var(--border-default);
  box-shadow: var(--shadow-sm);
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 22px 0;
}

.card-title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.card-title h3 {
  font-family: var(--font-display);
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.card-icon {
  width: 34px;
  height: 34px;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--icon-bg);
  color: var(--icon-color);
}

.char-count {
  font-size: 12px;
  font-family: var(--font-mono);
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}

.char-count.warn {
  color: var(--color-warning);
}

.card-body {
  padding: 16px 22px 20px;
}

/* ═══ Fields ═══ */

.field-grid {
  display: grid;
  gap: 16px;
}

.field-grid.three-col {
  grid-template-columns: repeat(3, 1fr);
}

.field-grid.two-col {
  grid-template-columns: repeat(2, 1fr);
}

@media (max-width: 700px) {
  .field-grid.three-col { grid-template-columns: 1fr; }
  .field-grid.two-col { grid-template-columns: 1fr; }
}

.field-label {
  display: block;
  font-size: 11.5px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 6px;
}

.input-wrap {
  position: relative;
  display: flex;
  align-items: center;
}

.input-icon {
  position: absolute;
  left: 12px;
  color: var(--text-muted);
  font-size: 15px;
  pointer-events: none;
  transition: color 0.15s;
  z-index: 1;
}

.custom-input {
  width: 100%;
  height: 42px;
  padding: 0 14px 0 38px;
  border: 1.5px solid var(--border-subtle);
  border-radius: var(--radius-md);
  font-size: 14px;
  font-family: var(--font-body);
  color: var(--text-primary);
  background: var(--color-surface);
  transition: all 0.15s ease;
  outline: none;
}

.custom-input::placeholder {
  color: var(--text-muted);
  font-weight: 400;
}

.custom-input:hover {
  border-color: var(--border-default);
}

.custom-input:focus {
  border-color: var(--color-accent);
  box-shadow: 0 0 0 3px rgba(176, 141, 71, 0.08);
}

.custom-input:focus ~ .input-icon,
.input-wrap:focus-within .input-icon {
  color: var(--color-accent);
}

/* Select */
.select-wrap {
  position: relative;
}

.custom-select {
  appearance: none;
  cursor: pointer;
  padding-right: 36px;
}

.select-wrap::after {
  content: '';
  position: absolute;
  right: 14px;
  top: 50%;
  transform: translateY(-50%);
  width: 0;
  height: 0;
  border-left: 4.5px solid transparent;
  border-right: 4.5px solid transparent;
  border-top: 5px solid var(--text-muted);
  pointer-events: none;
  transition: border-color 0.15s;
}

.select-wrap:focus-within::after {
  border-top-color: var(--color-accent);
}

/* Textarea */
.custom-textarea {
  width: 100%;
  padding: 12px 14px;
  border: 1.5px solid var(--border-subtle);
  border-radius: var(--radius-md);
  font-size: 14px;
  font-family: var(--font-body);
  color: var(--text-primary);
  background: var(--color-surface);
  resize: vertical;
  min-height: 120px;
  line-height: 1.65;
  transition: all 0.15s ease;
  outline: none;
}

.custom-textarea::placeholder {
  color: var(--text-muted);
}

.custom-textarea:hover {
  border-color: var(--border-default);
}

.custom-textarea:focus {
  border-color: var(--color-accent);
  box-shadow: 0 0 0 3px rgba(176, 141, 71, 0.08);
}

/* Field error */
.field-error {
  display: block;
  font-size: 12px;
  color: var(--color-danger);
  margin-top: 4px;
  padding-left: 2px;
}

/* ═══ Buttons ═══ */

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding-top: 4px;
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 10px 24px;
  border: none;
  border-radius: var(--radius-md);
  font-size: 14px;
  font-weight: 600;
  font-family: var(--font-body);
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-primary {
  background: linear-gradient(135deg, #b08d47, #c9a55a);
  color: #fff;
  box-shadow: 0 2px 8px rgba(176, 141, 71, 0.25);
}

.btn-primary:hover:not(:disabled) {
  box-shadow: 0 4px 14px rgba(176, 141, 71, 0.35);
  transform: translateY(-1px);
}

.btn-primary:active:not(:disabled) {
  transform: translateY(0);
  box-shadow: 0 1px 4px rgba(176, 141, 71, 0.2);
}

.btn-ghost {
  background: transparent;
  color: var(--text-secondary);
  border: 1.5px solid var(--border-subtle);
}

.btn-ghost:hover:not(:disabled) {
  border-color: var(--border-default);
  color: var(--text-primary);
  background: rgba(0, 0, 0, 0.015);
}

/* ═══ Stats Tab ═══ */

/* ═══ Permissions Tab ═══ */

.perm-note {
  font-size: 12px;
  color: var(--text-muted);
}

.perm-list {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.perm-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 0;
  border-bottom: 1px solid var(--border-subtle);
}

.perm-row:last-child {
  border-bottom: none;
}

.perm-info {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.perm-icon {
  color: var(--text-secondary);
  flex-shrink: 0;
}

.perm-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.3;
}

.perm-desc {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 2px;
}

.perm-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
}

.perm-on {
  color: #16a34a;
  background: rgba(22, 163, 74, 0.08);
}

.perm-off {
  color: var(--text-muted);
  background: rgba(0, 0, 0, 0.04);
}

.perm-value {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-accent);
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}

/* ═══ Stats Tab ═══ */

.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(190px, 100%), 1fr));
  gap: 14px;
  margin-bottom: 18px;
}

.highlight-row {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(240px, 100%), 1fr));
  gap: 14px;
  margin-bottom: 18px;
}

.highlight-card {
  position: relative;
  display: flex;
  background: var(--color-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: var(--shadow-xs);
  transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
}

.highlight-card:hover {
  border-color: var(--border-default);
  box-shadow: var(--shadow-sm);
  transform: translateY(-1px);
}

.highlight-indicator {
  width: 4px;
  flex-shrink: 0;
}

.highlight-card.best .highlight-indicator {
  background: linear-gradient(180deg, #dc2626, #ef4444);
}

.highlight-card.worst .highlight-indicator {
  background: linear-gradient(180deg, #16a34a, #22c55e);
}

.highlight-body {
  flex: 1;
  padding: 16px 18px;
  min-width: 0;
}

.highlight-label {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 10px;
}

.highlight-data {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
}

.highlight-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  font-family: var(--font-display);
}

.highlight-value {
  font-family: var(--font-mono);
  font-size: 18px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.highlight-value.profit { color: #dc2626; }
.highlight-value.loss { color: #16a34a; }

.highlight-empty {
  font-size: 14px;
  color: var(--text-muted);
}

/* Bio showcase */
.bio-showcase {
  background: var(--color-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: 20px 22px;
  box-shadow: var(--shadow-xs);
}

.bio-showcase-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-family: var(--font-display);
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 12px;
}

.bio-showcase-text {
  font-size: 14px;
  line-height: 1.75;
  color: var(--text-secondary);
  white-space: pre-wrap;
  margin: 0;
}

/* ═══ Feedback Tab ═══ */

.feedback-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.feedback-type-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.fb-type-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 6px 14px;
  border: 1.5px solid var(--border-subtle);
  border-radius: var(--radius-md);
  background: transparent;
  font-size: 13px;
  font-family: var(--font-body);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s;
}

.fb-type-btn:hover {
  border-color: var(--border-default);
  color: var(--text-primary);
}

.fb-type-btn.active {
  border-color: var(--color-accent);
  color: var(--color-accent);
  background: rgba(176, 141, 71, 0.06);
  font-weight: 600;
}

.fb-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 32px 0;
  color: var(--text-muted);
  font-size: 14px;
}

.fb-item {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  margin-bottom: 8px;
  cursor: pointer;
  transition: all 0.2s;
  overflow: hidden;
}

.fb-item:hover {
  border-color: var(--border-default);
  box-shadow: var(--shadow-xs);
}

.fb-item.expanded {
  border-color: var(--color-accent);
  box-shadow: 0 0 0 1px rgba(176, 141, 71, 0.1);
}

.fb-item-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  gap: 12px;
}

.fb-item-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1;
}

.fb-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.fb-status-dot.pending { background: #f59e0b; }
.fb-status-dot.in_progress { background: #3b82f6; }
.fb-status-dot.resolved { background: #16a34a; }
.fb-status-dot.closed { background: var(--text-muted); }

.fb-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.fb-item-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.fb-type-tag {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
}

.fb-type-tag.bug { color: #dc2626; background: rgba(220, 38, 38, 0.08); }
.fb-type-tag.feature { color: #2563eb; background: rgba(37, 99, 235, 0.08); }
.fb-type-tag.question { color: #7c3aed; background: rgba(124, 58, 237, 0.08); }
.fb-type-tag.other { color: var(--text-secondary); background: rgba(0, 0, 0, 0.04); }

.fb-status-tag {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
}

.fb-status-tag.pending { color: #f59e0b; background: rgba(245, 158, 11, 0.08); }
.fb-status-tag.in_progress { color: #3b82f6; background: rgba(59, 130, 246, 0.08); }
.fb-status-tag.resolved { color: #16a34a; background: rgba(22, 163, 74, 0.08); }
.fb-status-tag.closed { color: var(--text-muted); background: rgba(0, 0, 0, 0.04); }

.fb-time {
  font-size: 12px;
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}

.fb-item-detail {
  padding: 0 16px 16px;
  border-top: 1px solid var(--border-subtle);
}

.fb-content {
  font-size: 13.5px;
  line-height: 1.7;
  color: var(--text-secondary);
  padding: 12px 0;
  white-space: pre-wrap;
  word-break: break-word;
}

.fb-reply {
  background: rgba(176, 141, 71, 0.04);
  border: 1px solid rgba(176, 141, 71, 0.12);
  border-radius: var(--radius-md);
  padding: 12px 14px;
  margin-top: 4px;
}

.fb-reply-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--color-accent);
  margin-bottom: 6px;
}

.fb-reply-time {
  margin-left: auto;
  color: var(--text-muted);
  font-weight: 400;
  font-family: var(--font-mono);
}

.fb-reply-content {
  font-size: 13.5px;
  line-height: 1.7;
  color: var(--text-primary);
  white-space: pre-wrap;
  word-break: break-word;
}

.fb-no-reply {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--text-muted);
  padding: 8px 0;
}

/* ═══ Password Tab ═══ */

.password-section {
  display: flex;
  justify-content: center;
}

.password-card {
  width: 100%;
  max-width: 460px;
  background: var(--color-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs);
  padding: 28px;
}

.password-card-header {
  margin-bottom: 24px;
}

.password-card-header h3 {
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 4px 0;
}

.password-card-header p {
  font-size: 13px;
  color: var(--text-muted);
  margin: 0;
}

.password-fields {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-bottom: 24px;
}

.password-section .form-actions {
  justify-content: flex-start;
}

/* ═══ Responsive ═══ */

@media (max-width: 600px) {
  .profile-page {
    padding-bottom: 24px;
  }

  .profile-banner {
    border-radius: var(--radius-lg);
    min-height: 120px;
  }

  .banner-content {
    padding: 20px;
    gap: 14px;
  }

  .initial-circle {
    width: 52px;
    height: 52px;
    font-size: 22px;
  }

  .banner-name {
    font-size: 20px;
  }

  .banner-meta {
    font-size: 12px;
  }

  .card-body {
    padding: 14px 16px 18px;
  }

  .card-header {
    padding: 14px 16px 0;
  }

  .tab-btn {
    padding: 8px 10px;
    font-size: 13px;
  }

  .password-card {
    padding: 20px;
  }
}

/* ═══════════════════════════════════════════════
   AI 记忆 Tab
   ═══════════════════════════════════════════════ */

.memory-hint {
  font-size: 12px;
  color: var(--text-tertiary, #909399);
}

.memory-field {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid var(--border-light, #ebeef5);
}
.memory-field:last-child {
  border-bottom: none;
}

.memory-label {
  flex-shrink: 0;
  width: 72px;
  font-size: 13px;
  color: var(--text-secondary, #606266);
  padding-top: 4px;
}

.memory-tag-group {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.memory-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  font-size: 12px;
  border-radius: 14px;
  border: 1px solid var(--border-light, #dcdfe6);
  background: var(--bg-secondary, #f5f7fa);
  color: var(--text-secondary, #606266);
  cursor: pointer;
  transition: all 0.2s;
}
.memory-tag:hover {
  border-color: #409eff;
  color: #409eff;
}
.memory-tag.active {
  background: rgba(64, 158, 255, 0.1);
  border-color: #409eff;
  color: #409eff;
}
.memory-tag .tag-close {
  cursor: pointer;
  opacity: 0.6;
}
.memory-tag .tag-close:hover {
  opacity: 1;
}

.memory-tag-input {
  border: none;
  outline: none;
  background: transparent;
  font-size: 12px;
  padding: 3px 8px;
  width: 140px;
  color: var(--text-primary, #303133);
}
.memory-tag-input::placeholder {
  color: var(--text-placeholder, #c0c4cc);
}

.memory-empty {
  font-size: 12px;
  color: var(--text-placeholder, #c0c4cc);
}

.card-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.memory-filter-select {
  font-size: 12px;
  padding: 3px 8px;
  border: 1px solid var(--border-light, #dcdfe6);
  border-radius: 4px;
  background: var(--bg-primary, #fff);
  color: var(--text-secondary, #606266);
  outline: none;
}

.btn-small {
  padding: 4px 10px;
  font-size: 12px;
}

.memory-empty-state {
  text-align: center;
  padding: 32px 16px;
  color: var(--text-placeholder, #c0c4cc);
}
.memory-empty-state p {
  margin-top: 8px;
  font-size: 13px;
}

.memory-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.memory-item {
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--bg-secondary, #f9fafb);
  border: 1px solid var(--border-light, #ebeef5);
}

.memory-item-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.memory-category {
  font-size: 11px;
  padding: 1px 7px;
  border-radius: 10px;
  font-weight: 500;
}

.memory-source {
  font-size: 11px;
  color: var(--text-tertiary, #909399);
}

.memory-date {
  font-size: 11px;
  color: var(--text-tertiary, #909399);
  margin-left: auto;
}

.memory-delete {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--text-placeholder, #c0c4cc);
  padding: 2px;
  display: flex;
  align-items: center;
}
.memory-delete:hover {
  color: #f56c6c;
}

.memory-content {
  font-size: 13px;
  color: var(--text-primary, #303133);
  line-height: 1.5;
  margin: 0;
}

/* 模态框 */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
}

.modal-box {
  background: var(--bg-primary, #fff);
  border-radius: 12px;
  padding: 24px;
  width: 400px;
  max-width: 90vw;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
}
.modal-box h3 {
  margin: 0 0 16px;
  font-size: 16px;
}

.modal-field {
  margin-bottom: 12px;
}
.modal-field label {
  display: block;
  font-size: 13px;
  color: var(--text-secondary, #606266);
  margin-bottom: 4px;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
}

/* ── API Token Section ── */
.api-tokens-section {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  padding: 20px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 16px;
}

.section-header h3 {
  font-size: 16px;
  font-weight: 600;
  margin: 0 0 4px;
}

.section-desc {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.45);
  margin: 0;
}

.token-list-profile {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.token-empty {
  text-align: center;
  padding: 32px;
  color: rgba(255, 255, 255, 0.35);
  font-size: 13px;
}

.token-item {
  background: rgba(0, 0, 0, 0.2);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 8px;
  padding: 12px 16px;
}

.token-item.disabled {
  opacity: 0.5;
}

.token-item-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.token-name {
  font-weight: 500;
  font-size: 14px;
}

.token-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.4);
  margin-bottom: 8px;
}

.token-actions {
  display: flex;
  gap: 4px;
}

.token-result-box {
  display: flex;
  align-items: center;
  gap: 12px;
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid rgba(201, 165, 90, 0.3);
  border-radius: 8px;
  padding: 12px 16px;
}

.token-value {
  flex: 1;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 14px;
  color: #c9a55a;
  word-break: break-all;
  line-height: 1.5;
}
</style>
