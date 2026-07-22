/*
 * Big-screen layout enhancement (v5)
 *
 * The production big screen is a standalone compiled React application.  This
 * small companion script changes only the lower-screen presentation without
 * changing its dashboard data contract:
 *   - hides the retired "latest welding history" panel;
 *   - lets the NDT NG panel use the full row;
 *   - adds an NG total and a client-side search box.
 */
(() => {
  'use strict'

const MAIN_TITLE = '焊接质量与进度驾驶舱联动平台'

const state = {
    query: '',
    scheduled: false,
    auditPipeline: '',
    auditIssue: '',
    auditIssues: [],
    auditCheckedAt: 0,
    auditRequest: 0,
    sheetTitle: '',
    sheetTitleCheckedAt: 0,
    activePage: 'home',
    qualityData: null,
    qualityCheckedAt: 0,
    qualityPending: false,
    qualityRequest: 0,
    qualityError: '',
    qualityRevision: 0,
    qualityRenderKey: '',
    pipelineDailyData: null,
    pipelineDailyCheckedAt: 0,
    pipelineDailyPending: false,
    pipelineDailyRequest: 0,
    pipelineDailyError: '',
    pipelineDailyRevision: 0,
    pipelineDailyDates: { welding: '', ndt: '' },
    heatTreatmentData: null,
    heatTreatmentCheckedAt: 0,
    heatTreatmentPending: false,
    heatTreatmentRequest: 0,
    heatTreatmentError: '',
    heatTreatmentRevision: 0,
    heatTreatmentQueries: { complete: '', pending: '' },
    manualSyncing: false,
    manualSyncStatus: 'idle',
    manualSyncResetTimer: 0,
  }
  const normalize = (value) => String(value || '').trim().toLocaleLowerCase('zh-CN')

  function showManualSyncMessage(type, message) {
    let notice = document.querySelector('[data-manual-sync-notice]')
    if (!notice) {
      notice = document.createElement('div')
      notice.dataset.manualSyncNotice = 'true'
      document.body.appendChild(notice)
    }
    notice.className = `manual-sync-notice is-${type}`
    notice.textContent = message
    notice.hidden = false
    window.clearTimeout(Number(notice.dataset.hideTimer || 0))
    const hideTimer = window.setTimeout(() => {
      notice.hidden = true
    }, type === 'success' ? 5000 : 8000)
    notice.dataset.hideTimer = String(hideTimer)
  }

  function setManualSyncStatus(status) {
    state.manualSyncStatus = status
    window.clearTimeout(state.manualSyncResetTimer)
    if (status === 'success' || status === 'error') {
      state.manualSyncResetTimer = window.setTimeout(() => {
        state.manualSyncStatus = 'idle'
        scheduleRefresh()
      }, 3000)
    }
    scheduleRefresh()
  }

  async function runManualTencentSync(button) {
    if (state.manualSyncing) return
    state.manualSyncing = true
    setManualSyncStatus('syncing')

    try {
      // Do not reimplement this request here.  Invoke the very same React
      // handler wired to the Settings panel's “立即同步” button, so both
      // controls use identical book-id resolution, request code and follow-up
      // behaviour.
      const settingsImmediateSync = window.__weldingSettingsImmediateSync
      if (typeof settingsImmediateSync !== 'function') {
        throw new Error('\u8bbe\u7f6e\u540c\u6b65\u6a21\u5757\u8fd8\u672a\u5c31\u7eea\uff0c\u8bf7\u7a0d\u540e\u518d\u8bd5')
      }
      await settingsImmediateSync()
      setManualSyncStatus('idle')
    } catch (error) {
      setManualSyncStatus('error')
      showManualSyncMessage(
        'error',
        `\u817e\u8baf\u6587\u6863\u540c\u6b65\u5931\u8d25\uff1a${error instanceof Error ? error.message : '\u672a\u77e5\u9519\u8bef'}`,
      )
    } finally {
      state.manualSyncing = false
      scheduleRefresh()
    }
  }

  function syncManualSyncButton() {
    const header = document.querySelector('.header-right')
    const button = header?.querySelector('button:first-of-type')
    if (!button) return

    button.classList.add('tencent-manual-sync')
    button.classList.toggle('is-syncing', state.manualSyncing)
    button.classList.toggle('is-success', state.manualSyncStatus === 'success')
    button.classList.toggle('is-error', state.manualSyncStatus === 'error')
    button.disabled = state.manualSyncing
    button.title = '\u7acb\u5373\u540c\u6b65\u817e\u8baf\u5728\u7ebf\u6587\u6863\u6570\u636e'

    // Keep the header exactly as compact as the original dashboard: the
    // original refresh glyph is now the Tencent-sync trigger, with its state
    // communicated by rotation, colour and the transient notice only.
    button.querySelector('[data-manual-sync-label]')?.remove()

    // The compiled screen dispatches this event from the refresh glyph.  Do
    // not attach another native click handler here: React's original handler
    // used to fetch the old local dashboard in parallel with Tencent sync,
    // allowing that stale response to overwrite the new one.
    if (window.__weldingTencentSyncListenerBound !== true) {
      window.__weldingTencentSyncListenerBound = true
      window.addEventListener('welding-tencent-sync', () => {
        const currentButton = document.querySelector('.header-right button:first-of-type')
        if (currentButton) void runManualTencentSync(currentButton)
      })
    }
  }

function syncSheetTitle() {
  const mainTitle = document.querySelector('.header-title')
  if (!mainTitle) return

  if (mainTitle.textContent !== MAIN_TITLE) mainTitle.textContent = MAIN_TITLE

  let sheetTitle = document.querySelector('[data-sheet-title]')
    if (!sheetTitle) {
      sheetTitle = document.createElement('span')
      sheetTitle.dataset.sheetTitle = 'true'
      sheetTitle.className = 'sheet-source-title'
    }
    if (mainTitle.nextElementSibling !== sheetTitle) mainTitle.after(sheetTitle)
    sheetTitle.textContent = state.sheetTitle
    sheetTitle.hidden = !state.sheetTitle
    const positionSheetTitle = () => {
      if (!state.sheetTitle) return
      sheetTitle.style.left = `${mainTitle.offsetLeft + mainTitle.offsetWidth + 14}px`
      sheetTitle.style.top = `${mainTitle.offsetTop + Math.max(0, (mainTitle.offsetHeight - sheetTitle.offsetHeight) / 2)}px`
    }
    positionSheetTitle()

    const now = Date.now()
    if (now - state.sheetTitleCheckedAt < 300000) return
    state.sheetTitleCheckedAt = now
    fetch('/api/tencent/config')
      .then((response) => (response.ok ? response.json() : null))
      .then((config) => {
        state.sheetTitle = String(config?.sheet_title || '').trim()
        sheetTitle.textContent = state.sheetTitle
        sheetTitle.hidden = !state.sheetTitle
        positionSheetTitle()
      })
      .catch(() => {})
  }

  function syncDailyApiUsage() {
    const usageNode = Array.from(document.querySelectorAll('.header-left span')).find((node) =>
      node.textContent?.includes('API 调用'),
    )
    if (usageNode) usageNode.style.removeProperty('display')
    document.querySelector('[data-daily-api-usage]')?.remove()
  }

  function syncHomeTabLayout() {
    const shell = getScreenShell()
    const nav = shell?.querySelector('[data-quality-page-tabs]')
    if (!nav) return

    // Keep the tab bar in the exact same full-width position on the home
    // screen and every analysis page.  Analysis content is then anchored below
    // the measured bottom edge of this shared bar.
    nav.classList.add('is-home-layout')
    nav.classList.remove('is-analysis-layout')

    const pipelineLabel = Array.from(document.querySelectorAll('.kpi-container span')).find((node) =>
      node.textContent?.trim() === '管线总数量',
    )
    const kpiRegion = pipelineLabel?.closest('.kpi-card-item')?.parentElement?.parentElement
    const content = kpiRegion?.parentElement
    if (!kpiRegion || !content) return

    let spacer = content.querySelector('[data-quality-page-tabs-spacer]')
    if (!spacer) {
      spacer = createElement('div', 'quality-page-tabs-spacer')
      spacer.dataset.qualityPageTabsSpacer = 'true'
      content.insertBefore(spacer, kpiRegion)
    }

    const isHome = state.activePage === 'home'
    spacer.hidden = false
    if (!isHome) return

    content.style.padding = '8px 20px 12px'
    content.style.gap = '10px'
    kpiRegion.style.height = '78px'
    const bottomRow = content.lastElementChild
    if (bottomRow && bottomRow !== spacer) bottomRow.style.height = '196px'
  }

  function syncAnalysisPageLayout(page) {
    const shell = getScreenShell()
    const nav = shell?.querySelector('[data-quality-page-tabs]')
    if (!shell || !nav || !page) return

    // Anchor every analysis page to the exact point where the overview's KPI
    // region begins. This preserves the same nav/content relationship as 首页总览.
    const navBottom = nav.offsetTop + nav.offsetHeight
    const overviewKpiRegion = shell.querySelector('.kpi-container')?.parentElement
    const overviewContentTop = overviewKpiRegion?.offsetTop
    page.style.top = `${Math.max(navBottom + 14, overviewContentTop || 0)}px`
    page.style.bottom = '14px'
  }

  function findPanel(title) {
    return Array.from(document.querySelectorAll('.datav-panel')).find((panel) =>
      Array.from(panel.querySelectorAll('.panel-title')).some((node) => node.textContent?.includes(title)),
    )
  }

  function getRows(panel) {
    const root = panel?.querySelector('.panel-content > div')
    const viewport = root?.children?.[1]
    const rowList = viewport?.firstElementChild
    if (!rowList) return { viewport: null, rowList: null, rows: [] }

    return {
      viewport,
      rowList,
      rows: Array.from(rowList.children).filter((row) => row.children.length >= 2),
    }
  }

  function uniqueJointCount(rows) {
    const keys = new Set()
    rows.forEach((row) => {
      const pipeline = row.children[0]?.textContent?.trim()
      const joint = row.children[1]?.textContent?.trim()
      if (pipeline && joint) keys.add(`${pipeline}\u0000${joint}`)
    })
    return keys.size
  }

  function applySearch(panel) {
    const { viewport, rowList, rows } = getRows(panel)
    const query = normalize(state.query)
    const matchedJoints = new Set()

    rows.forEach((row) => {
      const pipeline = row.children[0]?.textContent?.trim() || ''
      const joint = row.children[1]?.textContent?.trim() || ''
      const key = `${pipeline}\u0000${joint}`
      const matches = !query || normalize(row.textContent).includes(query)
      const duplicate = Boolean(query && matches && matchedJoints.has(key))
      const visible = matches && !duplicate
      if (query && visible) matchedJoints.add(key)
      if (row.hidden !== !visible) row.hidden = !visible
    })

    // The original table auto-scrolls.  While searching, hold it still and
    // allow a scrollbar so each matched result can be checked comfortably.
    if (viewport && rowList) {
      if (query) {
        if (!rowList.dataset.originalTransform) rowList.dataset.originalTransform = rowList.style.transform || ''
        if (rowList.style.transform !== 'none') rowList.style.transform = 'none'
        if (viewport.style.overflowY !== 'auto') viewport.style.overflowY = 'auto'
      } else {
        if (rowList.dataset.originalTransform !== undefined) {
          rowList.style.transform = rowList.dataset.originalTransform
          delete rowList.dataset.originalTransform
        }
        if (viewport.style.overflowY) viewport.style.overflowY = ''
      }
    }

    return uniqueJointCount(rows)
  }

  function findDetailLabel(panel, labels) {
    return Array.from(panel.querySelectorAll('span')).find((node) =>
      labels.includes(node.textContent?.trim()),
    )
  }

  function updateDetailUnit(panel, oldLabel, newLabel) {
    const label = findDetailLabel(panel, [oldLabel, newLabel])
    const row = label?.parentElement
    const value = row?.lastElementChild
    if (!label || !value || value === label) return

    label.textContent = newLabel
    const original = value.textContent?.trim() || ''
    if (original) value.textContent = original.replace(/\s*[张道]$/, ' 道')
  }

  function auditRows() {
    if (state.auditIssues.length) return state.auditIssues
    return state.auditIssue
      ? state.auditIssue.split('\n').filter(Boolean).map((issue) => ({
          pipeline_no: state.auditPipeline,
          joint_no: '',
          issue,
        }))
      : []
  }

  function createAuditIssueGroup(items) {
    const group = document.createElement('div')
    group.className = 'pipeline-audit-issue-group'
    group.dataset.auditOriginal = 'true'
    items.forEach((item) => {
      const issueRow = document.createElement('div')
      issueRow.className = 'pipeline-audit-issue-row'
      const pipeline = document.createElement('span')
      const joint = document.createElement('span')
      const issue = document.createElement('span')
      pipeline.textContent = item.pipeline_no || ''
      joint.textContent = item.joint_no || ''
      issue.textContent = item.issue || ''
      issueRow.append(pipeline, joint, issue)
      group.appendChild(issueRow)
    })
    return group
  }

  // Keep all generated audit lists on the same continuous, pixel-based scroll
  // as the source NG panel (1px / 50ms).  CSS percentage keyframes pause at
  // both ends and can reveal a seam when a duplicated list restarts.
  const CONTINUOUS_SCROLL_SPEED = 20

  function stopContinuousScroll(track) {
    const stop = track?._stopContinuousScroll
    if (typeof stop === 'function') stop()
    if (!track) return
    delete track._stopContinuousScroll
    delete track._continuousScrollActive
    delete track.dataset.continuousScroller
    track.style.removeProperty('transform')
  }

  function syncContinuousScroll({ hoverTarget, viewport, track, original, activeClass }) {
    if (!hoverTarget || !viewport || !track || !original) return

    const shouldScroll = viewport.clientHeight > 0 && original.scrollHeight > viewport.clientHeight + 1
    let clone = Array.from(track.children).find(
      (child) => child !== original && child.dataset.continuousClone === 'true',
    )
    if (!shouldScroll) {
      clone?.remove()
      hoverTarget.classList.remove(activeClass)
      stopContinuousScroll(track)
      return
    }

    if (!clone) {
      clone = original.cloneNode(true)
      ;['auditOriginal', 'auditIssueOriginal', 'unreviewedFilmOriginal', 'closureOriginal', 'qualityScanOriginal', 'heatTreatmentOriginal'].forEach((key) => {
        delete clone.dataset[key]
      })
      clone.dataset.continuousClone = 'true'
      clone.setAttribute('aria-hidden', 'true')
      track.appendChild(clone)
    }
    hoverTarget.classList.add(activeClass)
    if (track._continuousScrollActive) return

    track._continuousScrollActive = true
    track.dataset.continuousScroller = 'true'
    let offset = 0
    let previousFrame = performance.now()
    let frame = 0
    const tick = (now) => {
      if (!hoverTarget.isConnected || !viewport.isConnected || !track.isConnected || !original.isConnected) {
        stopContinuousScroll(track)
        return
      }

      const distance = original.getBoundingClientRect().height
      const elapsed = Math.min(100, Math.max(0, now - previousFrame))
      previousFrame = now
      if (distance > 0 && !hoverTarget.matches(':hover')) {
        offset = (offset + (elapsed * CONTINUOUS_SCROLL_SPEED) / 1000) % distance
        track.style.transform = `translate3d(0, -${offset.toFixed(3)}px, 0)`
      }
      frame = requestAnimationFrame(tick)
    }
    track._stopContinuousScroll = () => window.cancelAnimationFrame(frame)
    frame = requestAnimationFrame(tick)
  }

  function updateAuditScroll(value) {
    const viewport = value.querySelector('.pipeline-audit-issue-viewport')
    const track = value.querySelector('.pipeline-audit-issue-track')
    const original = track?.querySelector('[data-audit-original]')
    if (!viewport || !track || !original) return
    syncContinuousScroll({
      hoverTarget: value.closest('.datav-panel') || value,
      viewport,
      track,
      original,
      activeClass: 'is-scrolling',
    })
  }

  function renderAuditIssue(panel) {
    const label = findDetailLabel(panel, ['最近焊接日期:', '审核问题:'])
    const row = label?.parentElement
    const value = row?.lastElementChild
    if (!label || !row || !value || value === label) return

    const auditInner = row.parentElement
    const auditCard = auditInner?.parentElement
    label.textContent = '审核问题:'
    row.style.flex = '1 1 0'
    row.style.minHeight = '0'
    row.style.flexDirection = 'column'
    row.style.alignItems = 'stretch'
    row.style.gap = '8px'
    if (auditInner) {
      auditInner.style.height = '100%'
      auditInner.style.minHeight = '0'
    }
    if (auditCard) {
      auditCard.style.flex = '1 1 0'
      auditCard.style.minHeight = '0'
      auditCard.style.overflow = 'hidden'
    }

    value.classList.add('pipeline-audit-issue')
    value.style.width = '100%'
    value.style.maxWidth = 'none'
    value.style.flex = '1 1 0'
    value.style.minHeight = '0'
    value.style.overflow = 'hidden'
    value.style.position = 'relative'
    value.style.textAlign = 'left'

    const items = auditRows()
    const signature = JSON.stringify(items)
    if (value.dataset.auditContent !== signature || !value.querySelector('.pipeline-audit-issue-viewport')) {
      value.dataset.auditContent = signature
      value.replaceChildren()
      const header = document.createElement('div')
      header.className = 'pipeline-audit-issue-header'
      header.innerHTML = '<span>管线号</span><span>焊口号</span><span>审核问题</span>'
      const viewport = document.createElement('div')
      viewport.className = 'pipeline-audit-issue-viewport'
      const track = document.createElement('div')
      track.className = 'pipeline-audit-issue-track'
      track.appendChild(createAuditIssueGroup(items))
      viewport.appendChild(track)
      value.append(header, viewport)
    }
    requestAnimationFrame(() => updateAuditScroll(value))

    const ndtLabel = findDetailLabel(panel, ['最近探伤日期:'])
    if (ndtLabel?.parentElement) ndtLabel.parentElement.style.display = 'none'
  }

  function applyDetailLayout(ngPanel) {
    const detailPanel = findPanel('管线综合监控看板')
    const detailRow = detailPanel?.parentElement
    if (!detailPanel || !detailRow || !ngPanel) return

    // The right-side detail panel spans the former bottom-right space.  The
    // NG table keeps the remaining width, so the two panels never overlap.
    detailRow.style.overflow = 'visible'
    detailPanel.style.position = 'relative'
    detailPanel.style.zIndex = '3'
    detailPanel.style.height = 'calc(100% + 240px)'
    ngPanel.style.flex = '0 0 calc(100% - 480px)'
    ngPanel.style.maxWidth = 'calc(100% - 480px)'
  }

  function syncPipelineAudit() {
    const panel = findPanel('管线综合监控看板')
    if (!panel) return

    updateDetailUnit(panel, '拍片总张数:', '拍片总道数:')
    updateDetailUnit(panel, '已审核张数:', '已审核道数:')

    const pipeline = panel.querySelector('.panel-content h3')?.textContent?.trim() || ''
    if (!pipeline) return

    if (pipeline !== state.auditPipeline) {
      state.auditPipeline = pipeline
      state.auditIssue = ''
      state.auditIssues = []
      state.auditCheckedAt = 0
    }
    renderAuditIssue(panel)

    const now = Date.now()
    if (now - state.auditCheckedAt < 15000) return
    state.auditCheckedAt = now
    const requestId = ++state.auditRequest
    fetch(`/api/pipeline/${encodeURIComponent(pipeline)}`)
      .then((response) => (response.ok ? response.json() : null))
      .then((detail) => {
        if (requestId !== state.auditRequest || state.auditPipeline !== pipeline) return
        state.auditIssues = Array.isArray(detail?.audit_issues)
          ? detail.audit_issues.filter((item) => item?.issue)
          : []
        state.auditIssue = String(detail?.audit_issue || '').trim()
        renderAuditIssue(panel)
      })
      .catch(() => {})
  }

  function ensureControls(panel) {
    const header = panel.querySelector('.panel-header')
    if (!header) return null

    let controls = header.querySelector('[data-ng-search-controls]')
    if (controls) return controls

    controls = document.createElement('div')
    controls.dataset.ngSearchControls = 'true'
    controls.className = 'ng-search-controls'
    controls.innerHTML = [
      '<span class="status-tag danger ng-total" data-ng-total>不合格焊口总量：0 道</span>',
      '<label class="ng-search-label" title="按管线号、焊口号、探伤结果或返修状态检索">',
      '<span>检索</span>',
      '<input data-ng-search type="search" autocomplete="off" placeholder="管线号 / 焊口号 / 结果" />',
      '</label>',
    ].join('')

    const input = controls.querySelector('[data-ng-search]')
    input.value = state.query
    input.addEventListener('input', () => {
      state.query = input.value
      refresh()
    })
    header.appendChild(controls)
    return controls
  }

  const pageTabs = [
    { key: 'home', label: '首页总览' },
    { key: 'welder', label: '焊工质量' },
    { key: 'pipeline', label: '焊接进度' },
    { key: 'audit', label: '检测审核' },
    { key: 'heat-treatment', label: '焊接热处理' },
  ]
  const MIN_QUALITY_RANK_INSPECTED = 10

  const createElement = (tag, className, text) => {
    const node = document.createElement(tag)
    if (className) node.className = className
    if (text !== undefined && text !== null) node.textContent = String(text)
    return node
  }

  const number = (value) => Number(value || 0)
  const percent = (value) => `${(number(value) * 100).toFixed(1)}%`
  const samePayload = (left, right) => JSON.stringify(left) === JSON.stringify(right)

  function getScreenShell() {
    return document.querySelector('.screen-wrapper')
  }

  function ensurePageTabs() {
    const shell = getScreenShell()
    if (!shell) return null
    shell.style.position = 'relative'

    let nav = shell.querySelector('[data-quality-page-tabs]')
    if (!nav) {
      nav = createElement('nav', 'quality-page-tabs')
      nav.dataset.qualityPageTabs = 'true'
      nav.setAttribute('aria-label', '大屏分析页')
      pageTabs.forEach((item) => {
        const button = createElement('button', 'quality-page-tab', item.label)
        button.type = 'button'
        button.dataset.page = item.key
        button.addEventListener('click', () => selectPage(item.key))
        nav.appendChild(button)
      })
      shell.appendChild(nav)
    }
    nav.querySelectorAll('[data-page]').forEach((button) => {
      const active = button.dataset.page === state.activePage
      button.classList.toggle('is-active', active)
      button.setAttribute('aria-current', active ? 'page' : 'false')
    })
    return nav
  }

  function getHomeContent(shell) {
    return Array.from(shell.children).find((node) =>
      node !== shell.querySelector('.screen-header')
      && !node.matches?.('[data-quality-page-tabs], [data-quality-analysis-page]'),
    )
  }

  function ensureAnalysisPage() {
    const shell = getScreenShell()
    if (!shell) return null
    let page = shell.querySelector('[data-quality-analysis-page]')
    if (!page) {
      page = createElement('section', 'quality-analysis-page')
      page.dataset.qualityAnalysisPage = 'true'
      page.hidden = true
      shell.appendChild(page)
    }
    return page
  }

  function selectPage(page) {
    if (!pageTabs.some((item) => item.key === page)) return
    if (state.activePage === page) return
    state.activePage = page
    state.qualityRenderKey = ''
    ensurePageTabs()
    renderQualityPage()
    if (page === 'pipeline') requestPipelineDailyData()
    else if (page === 'heat-treatment') requestHeatTreatmentData()
    else if (page !== 'home') requestQualityData()
  }

  function buildAnalysisHeader(title, subtitle) {
    const header = createElement('div', 'quality-analysis-header')
    const text = createElement('div', 'quality-analysis-heading')
    text.appendChild(createElement('h2', '', title))
    if (subtitle) text.appendChild(createElement('p', '', subtitle))
    const tag = createElement('span', 'quality-live-tag', '数据随大屏实时刷新')
    header.append(text, tag)
    return header
  }

  function buildKpi(label, value, detail, tone = '') {
    const card = createElement('div', `quality-kpi ${tone}`.trim())
    card.append(
      createElement('span', 'quality-kpi-label', label),
      createElement('strong', 'quality-kpi-value', value),
      createElement('small', 'quality-kpi-detail', detail),
    )
    return card
  }

  function buildCard(title, subtitle = '') {
    const card = createElement('section', 'quality-card')
    const header = createElement('div', 'quality-card-header')
    const heading = createElement('div', '')
    heading.append(createElement('h3', '', title))
    if (subtitle) heading.append(createElement('span', '', subtitle))
    header.appendChild(heading)
    const body = createElement('div', 'quality-card-body')
    card.append(header, body)
    return { card, header, body }
  }

  function buildQualityScan(item, tone) {
    const rate = Math.max(0, Math.min(1, number(item.once_pass_rate)))
    const scan = createElement('div', `quality-scan-row is-${tone}`)
    const label = createElement('div', 'quality-scan-label')
    label.append(
      createElement('strong', '', item.welder || '-'),
      createElement('small', '', `${number(item.inspected_joints)} 道有效探伤`),
    )
    const meter = createElement('div', 'quality-scan-meter')
    const fill = createElement('i', '')
    fill.style.width = `${rate * 100}%`
    meter.appendChild(fill)
    const value = createElement('strong', 'quality-scan-value', percent(rate))
    scan.append(label, meter, value)
    return scan
  }

  function buildQualityScanCard(title, subtitle, welders, tone, emptyText) {
    const chart = buildCard(title, subtitle)
    chart.card.classList.add('quality-scan-card')
    const count = createElement('span', `quality-scan-count is-${tone}`, `${welders.length} 人`)
    chart.header.appendChild(count)
    if (welders.length) {
      const viewport = createElement('div', 'quality-scan-viewport')
      const track = createElement('div', 'quality-scan-track')
      const list = createElement('div', 'quality-scan-list')
      list.dataset.qualityScanOriginal = 'true'
      welders.forEach((item) => list.appendChild(buildQualityScan(item, tone)))
      track.appendChild(list)
      viewport.appendChild(track)
      chart.body.appendChild(viewport)
      requestAnimationFrame(() => {
        const willScroll = list.scrollHeight > viewport.clientHeight + 1
        if (willScroll) count.title = '自动循环滚动；鼠标悬停可暂停'
        syncContinuousScroll({
          hoverTarget: chart.card,
          viewport,
          track,
          original: list,
          activeClass: 'is-scrolling',
        })
      })
    } else {
      chart.body.appendChild(createElement('div', 'quality-empty', emptyText))
    }
    return chart.card
  }

  function buildTable(columns, rows) {
    const wrap = createElement('div', 'quality-table-wrap')
    const table = createElement('table', 'quality-table')
    const head = createElement('thead', '')
    const headRow = createElement('tr', '')
    columns.forEach((column) => headRow.appendChild(createElement('th', '', column.label)))
    head.appendChild(headRow)
    const body = createElement('tbody', '')
    rows.forEach((row) => {
      const tr = createElement('tr', '')
      columns.forEach((column) => {
        const value = typeof column.value === 'function' ? column.value(row) : row[column.value]
        const cell = createElement('td', column.tone ? column.tone(row) : '', value ?? '-')
        tr.appendChild(cell)
      })
      body.appendChild(tr)
    })
    table.append(head, body)
    wrap.appendChild(table)
    return wrap
  }

  function buildAuditIssueScroller(issues, card) {
    const scroller = createElement('div', 'quality-audit-issue-scroller')
    const header = createElement('div', 'quality-audit-issue-row is-header')
    ;['管线号', '焊口号', '审核问题', '审核状态'].forEach((label) => header.appendChild(createElement('span', '', label)))
    const viewport = createElement('div', 'quality-audit-issue-viewport')
    const track = createElement('div', 'quality-audit-issue-track')
    const list = createElement('div', 'quality-audit-issue-list')
    list.dataset.auditIssueOriginal = 'true'
    issues.forEach((item) => {
      const row = createElement('div', 'quality-audit-issue-row')
      row.append(
        createElement('span', '', item.pipeline_no || '-'),
        createElement('span', '', item.joint_no || '-'),
        createElement('span', 'quality-audit-issue-text', item.issue || '-'),
        createElement('span', item.audit_status === '已审' ? 'quality-rate-ok' : 'quality-rate-warn', item.audit_status || '待处理'),
      )
      list.appendChild(row)
    })
    track.appendChild(list)
    viewport.appendChild(track)
    scroller.append(header, viewport)
    requestAnimationFrame(() => syncContinuousScroll({
      hoverTarget: card,
      viewport,
      track,
      original: list,
      activeClass: 'is-scrolling',
    }))
    return scroller
  }

  function buildUnreviewedFilmScroller(rows, card) {
    const scroller = createElement('div', 'quality-unreviewed-film-scroller')
    const header = createElement('div', 'quality-unreviewed-film-row is-header')
    ;['管线号', '焊口号', 'AH 审核状态'].forEach((label) => header.appendChild(createElement('span', '', label)))
    const viewport = createElement('div', 'quality-unreviewed-film-viewport')
    const track = createElement('div', 'quality-unreviewed-film-track')
    const list = createElement('div', 'quality-unreviewed-film-list')
    list.dataset.unreviewedFilmOriginal = 'true'
    rows.forEach((item) => {
      const row = createElement('div', 'quality-unreviewed-film-row is-risk-row')
      row.append(
        createElement('span', '', item.pipeline_no || '-'),
        createElement('span', '', item.joint_no || '-'),
        createElement('span', 'quality-rate-warn', item.audit_status || '未审核'),
      )
      list.appendChild(row)
    })
    track.appendChild(list)
    viewport.appendChild(track)
    scroller.append(header, viewport)
    requestAnimationFrame(() => syncContinuousScroll({
      hoverTarget: card,
      viewport,
      track,
      original: list,
      activeClass: 'is-unreviewed-scrolling',
    }))
    return scroller
  }

  function buildClosureScroller(cases, card) {
    const scroller = createElement('div', 'quality-closure-scroller')
    const summary = createElement('div', 'quality-closure-summary')
    summary.append(
      createElement('span', '', '待处理 / 未闭环'),
      createElement('strong', '', `${number(cases.length)} 道`),
    )
    const header = createElement('div', 'quality-closure-row is-header')
    ;['管线号', '焊口号', '二次 / Y', '三次 / AA', '状态'].forEach((label, index) => {
      header.appendChild(createElement('span', index === 4 ? 'quality-closure-status-heading' : '', label))
    })
    const viewport = createElement('div', 'quality-closure-viewport')
    const track = createElement('div', 'quality-closure-track')
    const list = createElement('div', 'quality-closure-list')
    list.dataset.closureOriginal = 'true'
    cases.forEach((item) => {
      const row = createElement('div', 'quality-closure-row is-risk-row')
      row.append(
        createElement('span', '', item.pipeline_no || '-'),
        createElement('span', '', item.joint_no || '-'),
        createElement('span', item.second_result === '不合格' ? 'quality-rate-warn' : '', item.second_result || '未探'),
        createElement('span', item.third_result === '不合格' ? 'quality-rate-warn' : '', item.third_result || '未探'),
        createElement('span', 'quality-closure-status', item.closure_status || '待处理 / 未闭环'),
      )
      list.appendChild(row)
    })
    track.appendChild(list)
    viewport.appendChild(track)
    scroller.append(summary, header, viewport)
    requestAnimationFrame(() => syncContinuousScroll({
      hoverTarget: card,
      viewport,
      track,
      original: list,
      activeClass: 'is-closure-scrolling',
    }))
    return scroller
  }

  function buildHeatTreatmentScroller(joints, card, status) {
    const scroller = createElement('div', 'heat-treatment-scroller')
    const header = createElement('div', 'heat-treatment-row is-header')
    ;['管线号', '焊口号', '日期', '焊缝硬度值', '母材硬度值', '热影响区硬度值', '热处理操作人'].forEach((label) => {
      header.appendChild(createElement('span', '', label))
    })
    const viewport = createElement('div', 'heat-treatment-viewport')
    const track = createElement('div', 'heat-treatment-track')
    const list = createElement('div', 'heat-treatment-list')
    list.dataset.heatTreatmentOriginal = 'true'
    let previousPipeline = ''
    joints.forEach((item) => {
      const pipelineNo = item.pipeline_no || '-'
      const displayPipeline = pipelineNo === previousPipeline ? '' : pipelineNo
      previousPipeline = pipelineNo
      const row = createElement('div', `heat-treatment-row is-${status}`)
      const values = [
        displayPipeline,
        item.joint_no || '-',
        item.heat_treatment_date || '—',
        item.heat_treatment_am || '—',
        item.heat_treatment_an || '—',
        item.heat_treatment_ao || '—',
        item.heat_treatment_ap || '—',
      ]
      const classes = [
        'heat-treatment-pipeline',
        'heat-treatment-joint',
        'heat-treatment-date',
        'heat-treatment-extra',
        'heat-treatment-extra',
        'heat-treatment-extra',
        'heat-treatment-extra',
      ]
      values.forEach((value, index) => {
        const cell = createElement('span', classes[index], value)
        cell.title = value === '—' ? '' : value
        row.appendChild(cell)
      })
      list.appendChild(row)
    })
    track.appendChild(list)
    viewport.appendChild(track)
    scroller.append(header, viewport)
    requestAnimationFrame(() => syncContinuousScroll({
      hoverTarget: card,
      viewport,
      track,
      original: list,
      activeClass: 'is-heat-treatment-scrolling',
    }))
    return scroller
  }

  function buildHeatTreatmentSearch(card, status) {
    const search = createElement('label', 'heat-treatment-search')
    search.dataset.heatTreatmentSearch = status
    search.setAttribute('aria-label', status === 'complete' ? '搜索已热处理焊口' : '搜索未热处理焊口')
    const input = document.createElement('input')
    input.type = 'search'
    input.placeholder = '搜索管线号 / 焊口号'
    input.value = state.heatTreatmentQueries[status] || ''
    input.setAttribute('aria-label', status === 'complete' ? '搜索已热处理焊口的管线号或焊口号' : '搜索未热处理焊口的管线号或焊口号')
    input.addEventListener('input', () => {
      const cursor = input.selectionStart
      state.heatTreatmentQueries[status] = input.value
      state.qualityRenderKey = ''
      renderQualityPage()
      requestAnimationFrame(() => {
        const nextInput = card.ownerDocument.querySelector(`[data-heat-treatment-search="${status}"] input`)
        if (!nextInput) return
        nextInput.focus({ preventScroll: true })
        const position = Math.min(Number(cursor || 0), nextInput.value.length)
        nextInput.setSelectionRange(position, position)
      })
    })
    search.appendChild(input)
    return search
  }

  function appendQualityPage(page, title, subtitle, kpis, body) {
    page.replaceChildren()
    page.appendChild(buildAnalysisHeader(title, subtitle))
    const kpiGrid = createElement('div', 'quality-kpi-grid')
    kpis.forEach((kpi) => kpiGrid.appendChild(buildKpi(...kpi)))
    page.append(kpiGrid, body)
  }

  function renderWelderPage(page, data) {
    const summary = data.summary || {}
    const welders = Array.isArray(data.welders) ? data.welders : []
    const orderedWelders = [...welders]
      .sort((left, right) => number(left.once_pass_rate) - number(right.once_pass_rate) || number(right.inspected_joints) - number(left.inspected_joints) || String(left.welder || '').localeCompare(String(right.welder || '')))
    const rankEligibleWelders = orderedWelders.filter(
      (item) => number(item.inspected_joints) >= MIN_QUALITY_RANK_INSPECTED,
    )
    const highPassWelders = [...rankEligibleWelders]
      .filter((item) => number(item.once_pass_rate) >= 0.9)
      .sort((left, right) => number(right.once_pass_rate) - number(left.once_pass_rate) || number(right.inspected_joints) - number(left.inspected_joints))
    const lowPassWelders = [...rankEligibleWelders]
      .filter((item) => number(item.once_pass_rate) < 0.8)
      .sort((left, right) => number(left.once_pass_rate) - number(right.once_pass_rate) || number(right.inspected_joints) - number(left.inspected_joints))
    const body = createElement('div', 'quality-layout quality-layout-welder')
    const detail = buildCard('焊工一次探伤明细', 'X 列为空不参与统计')
    const search = createElement('label', 'quality-table-search')
    const searchInput = document.createElement('input')
    searchInput.type = 'search'
    searchInput.placeholder = '搜索焊工号'
    searchInput.setAttribute('aria-label', '搜索焊工号')
    search.append(createElement('span', '', '⌕'), searchInput)
    detail.header.appendChild(search)
    const columns = [
      { label: '焊工号', value: 'welder' },
      { label: '有效探伤', value: 'inspected_joints' },
      { label: '合格', value: 'passed_joints' },
      { label: '不合格', value: 'failed_joints' },
      { label: '一次合格率', value: (row) => percent(row.once_pass_rate), tone: (row) => number(row.once_pass_rate) < 0.9 ? 'quality-rate-warn' : 'quality-rate-ok' },
      { label: '覆盖管线', value: (row) => `${number(row.pipeline_count)} 条` },
    ]
    const tableHost = createElement('div', 'quality-welder-table-host')
    const renderTable = (query = '') => {
      const normalizedQuery = normalize(query)
      const rows = normalizedQuery
        ? orderedWelders.filter((row) => normalize(row.welder).includes(normalizedQuery))
        : orderedWelders
      tableHost.replaceChildren(buildTable(columns, rows))
      if (!rows.length) tableHost.appendChild(createElement('div', 'quality-table-no-match', '未找到匹配的焊工号'))
    }
    searchInput.addEventListener('input', () => renderTable(searchInput.value))
    renderTable()
    detail.body.appendChild(tableHost)

    const charts = createElement('div', 'quality-welder-charts')
    charts.append(
      buildQualityScanCard('一次探伤优质焊工', '有效一次探伤 ≥ 10 道；一次合格率 ≥ 90%', highPassWelders, 'success', '暂无满足 10 道有效探伤且合格率 90% 及以上的焊工'),
      buildQualityScanCard('一次探伤风险焊工', '有效一次探伤 ≥ 10 道；一次合格率 < 80%', lowPassWelders, 'danger', '暂无满足 10 道有效探伤且合格率低于 80% 的焊工'),
    )
    body.append(charts, detail.card)
    appendQualityPage(page, '焊工质量分析', '', [
      ['有效一次探伤', `${number(summary.inspected_joints)} 道`, 'X 列空白不计入'],
      ['一次探伤合格', `${number(summary.passed_joints)} 道`, '参与合格率计算', 'is-success'],
      ['一次探伤不合格', `${number(summary.failed_joints)} 道`, '需持续跟踪', 'is-danger'],
      ['整体一次合格率', percent(summary.once_pass_rate), '合格 ÷ 有效一次探伤', 'is-primary'],
      ['参与统计焊工', `${number(summary.welder_count)} 人`, `另有 ${number(summary.unassigned_inspected)} 道未填焊工号`],
    ], body)
  }

  function formatDailyDate(value) {
    if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return '暂无日期数据'
    const [year, month, day] = value.split('-')
    return `${year} 年 ${month} 月 ${day} 日`
  }

  function buildPipelineCompletionRows(activity, tone) {
    const rows = Array.isArray(activity?.pipelines) ? activity.pipelines : []
    const list = createElement('div', 'pipeline-day-list')
    if (!rows.length) {
      list.appendChild(createElement('div', 'pipeline-day-empty', '该日期暂无完成记录'))
      return list
    }
    const max = Math.max(...rows.map((item) => number(item.completed_joints)), 1)
    rows.forEach((item, index) => {
      const row = createElement('div', `pipeline-day-row is-${tone}`)
      const lead = createElement('div', 'pipeline-day-row-lead')
      lead.append(
        createElement('span', 'pipeline-day-rank', String(index + 1).padStart(2, '0')),
        createElement('strong', '', item.pipeline_no || '未填写管线号'),
      )
      const meter = createElement('div', 'pipeline-day-meter')
      const fill = createElement('i', '')
      fill.style.width = `${Math.max(6, number(item.completed_joints) / max * 100)}%`
      meter.appendChild(fill)
      row.append(
        lead,
        meter,
        createElement('strong', 'pipeline-day-row-value', `${number(item.completed_joints)} 道`),
      )
      list.appendChild(row)
    })
    return list
  }

  function buildDailyTrendChart(activity, tone) {
    const trend = Array.isArray(activity?.trend) ? activity.trend : []
    const chart = createElement('div', `pipeline-trend-chart is-${tone}`)
    if (!trend.length) {
      chart.appendChild(createElement('div', 'pipeline-trend-empty', '暂无趋势数据'))
      return chart
    }
    const max = Math.max(...trend.map((item) => number(item.count)), 1)
    trend.forEach((item, index) => {
      const column = createElement('div', 'pipeline-trend-column')
      const active = item.date === activity.selected_date
      if (active) column.classList.add('is-selected')
      column.title = `${item.date}：${number(item.count)} 道`
      const value = createElement('strong', 'pipeline-trend-value', String(number(item.count)))
      const rail = createElement('div', 'pipeline-trend-rail')
      const bar = createElement('i', '')
      bar.style.height = `${Math.max(number(item.count) ? 8 : 2, number(item.count) / max * 100)}%`
      rail.appendChild(bar)
      const label = createElement('span', 'pipeline-trend-label', index % 2 || active ? item.date.slice(5) : '')
      column.append(value, rail, label)
      chart.appendChild(column)
    })
    return chart
  }

  function buildDailyActivityCard({ title, subtitle, activity, tone, onDateChange }) {
    const card = buildCard(title, subtitle)
    card.card.classList.add('pipeline-day-card', `is-${tone}`)
    const dateControl = createElement('label', 'pipeline-date-control')
    dateControl.appendChild(createElement('span', '', '▣ 日期'))
    const input = document.createElement('input')
    input.type = 'date'
    input.value = activity?.selected_date || ''
    const range = activity?.available_date_range || {}
    if (range.min) input.min = range.min
    if (range.max) input.max = range.max
    input.setAttribute('aria-label', `${title}日期`)
    input.addEventListener('change', () => onDateChange(input.value))
    dateControl.appendChild(input)
    card.header.appendChild(dateControl)

    const hero = createElement('div', 'pipeline-day-hero')
    const meta = createElement('div', 'pipeline-day-meta')
    meta.append(
      createElement('span', 'pipeline-day-code', tone === 'welding' ? 'WELD / DAY' : 'NDT / DAY'),
      createElement('small', '', formatDailyDate(activity?.selected_date)),
    )
    const metric = createElement('div', 'pipeline-day-metric')
    metric.append(
      createElement('strong', '', String(number(activity?.total_joints))),
      createElement('span', '', '道'),
    )
    const pipelineCount = createElement('div', 'pipeline-day-pipelines')
    pipelineCount.append(
      createElement('span', '', '覆盖管线'),
      createElement('strong', '', `${number(activity?.pipeline_count)} 条`),
    )
    hero.append(meta, metric, pipelineCount)
    const listTitle = createElement('div', 'pipeline-day-list-title')
    listTitle.append(
      createElement('span', '', '管线完成分布'),
      createElement('span', '', '完成量'),
    )
    card.body.append(hero, listTitle, buildPipelineCompletionRows(activity, tone))
    return card.card
  }

  function buildDailyTrendCard({ title, subtitle, activity, tone }) {
    const card = buildCard(title, subtitle)
    card.card.classList.add('pipeline-trend-card', `is-${tone}`)
    const selected = createElement('div', 'pipeline-trend-selected')
    selected.append(
      createElement('span', '', 'SELECTED DAY'),
      createElement('strong', '', activity?.selected_date || '--'),
    )
    card.header.appendChild(selected)
    const summary = createElement('div', 'pipeline-trend-summary')
    summary.append(
      createElement('span', '', '当日完成'),
      createElement('strong', '', `${number(activity?.total_joints)} 道`),
      createElement('small', '', `按 ${formatDailyDate(activity?.selected_date)} 高亮`),
    )
    card.body.append(summary, buildDailyTrendChart(activity, tone))
    return card.card
  }

  function renderPipelineDailyPage(page, data) {
    const welding = data?.welding || {}
    const ndt = data?.ndt || {}
    const body = createElement('div', 'pipeline-command-grid')
    body.append(
      buildDailyActivityCard({
        title: '每日焊接完成量',
        subtitle: '按 R 列焊接日期统计 · 管线分布',
        activity: welding,
        tone: 'welding',
        onDateChange: (value) => {
          state.pipelineDailyDates.welding = value
          requestPipelineDailyData(true)
        },
      }),
      buildDailyActivityCard({
        title: '每日探伤完成量',
        subtitle: '按 V 列探伤日期统计 · 管线分布',
        activity: ndt,
        tone: 'ndt',
        onDateChange: (value) => {
          state.pipelineDailyDates.ndt = value
          requestPipelineDailyData(true)
        },
      }),
      buildDailyTrendCard({
        title: '焊接完成量趋势',
        subtitle: '连续 14 日焊接完成态势',
        activity: welding,
        tone: 'welding',
      }),
      buildDailyTrendCard({
        title: '探伤完成量趋势',
        subtitle: '连续 14 日探伤完成态势',
        activity: ndt,
        tone: 'ndt',
      }),
    )
    page.replaceChildren(
      buildAnalysisHeader('焊接进度 · 日完成态势', ''),
      body,
    )
  }

  function renderPipelinePage(page, data) {
    return renderPipelineDailyPage(page, data)
  }

  function renderAuditPage(page, data) {
    const repair = data.repair || {}
    const audit = data.audit || {}
    const issues = Array.isArray(audit.issues) ? audit.issues : []
    const unreviewedFilms = Array.isArray(audit.unreviewed_films) ? audit.unreviewed_films : []
    const unresolvedCases = Array.isArray(repair.unresolved_cases) ? repair.unresolved_cases : []
    const body = createElement('div', 'quality-layout quality-layout-audit')
    const closure = buildCard('探伤不合格闭环', `X 不合格 · Y / AA 未通过 · 共 ${number(repair.unresolved_failures)} 道`)
    closure.card.classList.add('quality-closure-card')
    if (unresolvedCases.length) {
      closure.body.appendChild(buildClosureScroller(unresolvedCases, closure.card))
    } else {
      closure.body.appendChild(createElement('div', 'quality-empty', '暂无待处理 / 未闭环焊口'))
    }

    const issueCard = buildCard('审核问题清单', `共 ${number(audit.issue_count)} 条，全部展示`)
    issueCard.card.classList.add('quality-audit-issue-card')
    if (issues.length) {
      issueCard.body.appendChild(buildAuditIssueScroller(issues, issueCard.card))
    } else {
      issueCard.body.appendChild(createElement('div', 'quality-empty', '暂无审核问题记录'))
    }
    const unreviewedCard = buildCard('未审核底片清单', `AH 列为空 · 共 ${number(audit.unreviewed_count)} 道`)
    unreviewedCard.card.classList.add('quality-unreviewed-film-card')
    if (unreviewedFilms.length) {
      unreviewedCard.body.appendChild(buildUnreviewedFilmScroller(unreviewedFilms, unreviewedCard.card))
    } else {
      unreviewedCard.body.appendChild(createElement('div', 'quality-empty', '暂无未审核底片'))
    }
    body.append(issueCard.card, closure.card, unreviewedCard.card)
    appendQualityPage(page, '无损检测与审核分析', '', [
      ['一次探伤不合格', `${number(repair.first_failures)} 道`, 'X 列为“不合格”', 'is-danger'],
      ['返修复探合格', `${number(repair.repaired_after_failure)} 道`, '二次或三次探伤合格', 'is-success'],
      ['待处理 / 未闭环', `${number(repair.unresolved_failures)} 道`, '需要重点跟踪', 'is-warning'],
      ['已审核道数', `${number(audit.audited_joints)} 道`, `待审核 ${number(audit.pending_joints)} 道`, 'is-primary'],
      ['审核问题', `${number(audit.issue_count)} 条`, '来自 AI 列审核问题'],
    ], body)
  }

  function renderHeatTreatmentPage(page, data) {
    const summary = data?.summary || {}
    const joints = Array.isArray(data?.joints) ? data.joints : []
    const matchesHeatTreatmentQuery = (item, query) => !query
      || normalize(item.pipeline_no).includes(query)
      || normalize(item.joint_no).includes(query)
    const allCompletedJoints = joints.filter((item) => item.heat_treatment_completed)
    const allPendingJoints = joints.filter((item) => !item.heat_treatment_completed)
    const completeQuery = normalize(state.heatTreatmentQueries.complete)
    const pendingQuery = normalize(state.heatTreatmentQueries.pending)
    const completedJoints = allCompletedJoints.filter((item) => matchesHeatTreatmentQuery(item, completeQuery))
    const pendingJoints = allPendingJoints.filter((item) => matchesHeatTreatmentQuery(item, pendingQuery))
    const header = buildAnalysisHeader(
      '焊接热处理分析',
      '',
    )
    const kpiGrid = createElement('div', 'heat-treatment-kpi-grid')
    kpiGrid.append(
      buildKpi('需热处理焊口总量', `${number(summary.required_joints)} 道`, 'AK 列为“是”的焊口', 'is-warning'),
      buildKpi('已完成热处理', `${number(summary.completed_joints)} 道`, `待处理 ${Math.max(0, number(summary.required_joints) - number(summary.completed_joints))} 道`, 'is-success'),
      buildKpi('热处理完成率', percent(summary.completion_rate), '已完成焊口 / 需热处理焊口', 'is-primary'),
    )

    const listOverview = createElement('div', 'heat-treatment-list-overview')
    const overviewText = createElement('div', 'heat-treatment-list-overview-text')
    overviewText.append(
      createElement('strong', '', '热处理清单明细'),
      createElement('span', '', `共 ${joints.length} 道需热处理焊口`),
    )
    listOverview.appendChild(overviewText)

    const listGrid = createElement('div', 'heat-treatment-lists')
    const completedCard = buildCard('已热处理焊口', `共 ${completedJoints.length} 道`)
    completedCard.card.classList.add('heat-treatment-list-card', 'heat-treatment-completed-card')
    completedCard.header.appendChild(buildHeatTreatmentSearch(completedCard.card, 'complete'))
    if (completedJoints.length) {
      completedCard.body.appendChild(buildHeatTreatmentScroller(completedJoints, completedCard.card, 'complete'))
    } else {
      completedCard.body.appendChild(createElement('div', 'heat-treatment-empty', completeQuery ? '未找到匹配的已热处理焊口' : '暂无已热处理焊口'))
    }
    const pendingCard = buildCard('未热处理焊口', `共 ${pendingJoints.length} 道`)
    pendingCard.card.classList.add('heat-treatment-list-card', 'heat-treatment-pending-card')
    pendingCard.header.appendChild(buildHeatTreatmentSearch(pendingCard.card, 'pending'))
    if (pendingJoints.length) {
      pendingCard.body.appendChild(buildHeatTreatmentScroller(pendingJoints, pendingCard.card, 'pending'))
    } else {
      pendingCard.body.appendChild(createElement('div', 'heat-treatment-empty', pendingQuery ? '未找到匹配的未热处理焊口' : '暂无未热处理焊口'))
    }
    listGrid.append(completedCard.card, pendingCard.card)
    page.replaceChildren(header, kpiGrid, listOverview, listGrid)
  }

  function renderQualityPage() {
    const shell = getScreenShell()
    const page = ensureAnalysisPage()
    if (!shell || !page) return
    const homeContent = getHomeContent(shell)
    const isHome = state.activePage === 'home'
    page.hidden = isHome
    if (homeContent) homeContent.style.visibility = isHome ? '' : 'hidden'
    ensurePageTabs()
    syncHomeTabLayout()
    syncAnalysisPageLayout(page)
    if (isHome) return

    const isPipeline = state.activePage === 'pipeline'
    const isAudit = state.activePage === 'audit'
    const isHeatTreatment = state.activePage === 'heat-treatment'
    page.classList.toggle('is-pipeline-dashboard', isPipeline)
    page.classList.toggle('is-audit-dashboard', isAudit)
    page.classList.toggle('is-heat-treatment-dashboard', isHeatTreatment)
    if (isPipeline) {
      const pipelineKey = `pipeline:${state.pipelineDailyRevision}:${state.pipelineDailyData ? '' : state.pipelineDailyError}`
      if (state.qualityRenderKey === pipelineKey) return
      state.qualityRenderKey = pipelineKey
      if (!state.pipelineDailyData) {
        page.replaceChildren(
          buildAnalysisHeader('焊接进度 · 日完成态势', '正在读取 R 列焊接日期与 V 列探伤日期的每日完成量'),
          createElement('div', 'quality-loading', state.pipelineDailyError || '正在汇总每日焊接与探伤完成量…'),
        )
        return
      }
      renderPipelinePage(page, state.pipelineDailyData)
      return
    }

    if (isHeatTreatment) {
      const heatKey = `heat-treatment:${state.heatTreatmentRevision}:${state.heatTreatmentData ? '' : state.heatTreatmentError}:${state.heatTreatmentQueries.complete}:${state.heatTreatmentQueries.pending}`
      if (state.qualityRenderKey === heatKey) return
      state.qualityRenderKey = heatKey
      if (!state.heatTreatmentData) {
        page.replaceChildren(
          buildAnalysisHeader('焊接热处理分析', '正在按 AK / AL 列汇总需热处理管线与完成状态'),
          createElement('div', 'quality-loading', state.heatTreatmentError || '正在汇总热处理清单…'),
        )
        return
      }
      renderHeatTreatmentPage(page, state.heatTreatmentData)
      return
    }

    const key = `${state.activePage}:${state.qualityRevision}:${state.qualityData ? '' : state.qualityError}`
    if (state.qualityRenderKey === key) return
    state.qualityRenderKey = key
    if (!state.qualityData) {
      page.replaceChildren(
        buildAnalysisHeader('数据分析加载中', '正在读取一次探伤、焊工、管线与审核统计数据'),
        createElement('div', 'quality-loading', state.qualityError || '正在汇总最新数据…'),
      )
      return
    }
    if (state.activePage === 'welder') renderWelderPage(page, state.qualityData)
    else renderAuditPage(page, state.qualityData)
  }

  function requestQualityData() {
    const now = Date.now()
    if (state.qualityPending || (state.qualityData && now - state.qualityCheckedAt < 15000)) return
    const hadData = Boolean(state.qualityData)
    let dataChanged = false
    state.qualityPending = true
    state.qualityError = ''
    if (!hadData) {
      state.qualityRenderKey = ''
      renderQualityPage()
    }
    const requestId = ++state.qualityRequest
    fetch('/api/quality-analysis')
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        return response.json()
      })
      .then((data) => {
        if (requestId !== state.qualityRequest) return
        dataChanged = !samePayload(state.qualityData, data)
        state.qualityData = data
        state.qualityCheckedAt = Date.now()
        if (dataChanged) state.qualityRevision += 1
      })
      .catch(() => {
        if (requestId !== state.qualityRequest) return
        state.qualityError = '分析数据暂时无法读取，请稍后重试'
        state.qualityCheckedAt = Date.now()
      })
      .finally(() => {
        if (requestId !== state.qualityRequest) return
        state.qualityPending = false
        if (!hadData || dataChanged) {
          state.qualityRenderKey = ''
          renderQualityPage()
        }
      })
  }

  function requestHeatTreatmentData(force = false) {
    const now = Date.now()
    if (state.heatTreatmentPending && !force) return
    if (!force && state.heatTreatmentData && now - state.heatTreatmentCheckedAt < 15000) return
    const hadData = Boolean(state.heatTreatmentData)
    let dataChanged = false
    state.heatTreatmentPending = true
    state.heatTreatmentError = ''
    if (!hadData) {
      state.qualityRenderKey = ''
      renderQualityPage()
    }
    const requestId = ++state.heatTreatmentRequest
    fetch('/api/heat-treatment-analysis')
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        return response.json()
      })
      .then((data) => {
        if (requestId !== state.heatTreatmentRequest) return
        dataChanged = !samePayload(state.heatTreatmentData, data)
        state.heatTreatmentData = data
        state.heatTreatmentCheckedAt = Date.now()
        if (dataChanged) state.heatTreatmentRevision += 1
      })
      .catch(() => {
        if (requestId !== state.heatTreatmentRequest) return
        state.heatTreatmentError = '热处理分析数据暂时无法读取，请稍后重试'
        state.heatTreatmentCheckedAt = Date.now()
      })
      .finally(() => {
        if (requestId !== state.heatTreatmentRequest) return
        state.heatTreatmentPending = false
        if (!hadData || dataChanged) {
          state.qualityRenderKey = ''
          renderQualityPage()
        }
      })
  }

  function requestPipelineDailyData(force = false) {
    const now = Date.now()
    if (state.pipelineDailyPending && !force) return
    if (!force && state.pipelineDailyData && now - state.pipelineDailyCheckedAt < 15000) return
    const hadData = Boolean(state.pipelineDailyData)
    let dataChanged = false
    state.pipelineDailyPending = true
    state.pipelineDailyError = ''
    if (!hadData) {
      state.qualityRenderKey = ''
      renderQualityPage()
    }
    const requestId = ++state.pipelineDailyRequest
    const params = new URLSearchParams()
    if (state.pipelineDailyDates.welding) params.set('weld_date', state.pipelineDailyDates.welding)
    if (state.pipelineDailyDates.ndt) params.set('ndt_date', state.pipelineDailyDates.ndt)
    const suffix = params.size ? `?${params.toString()}` : ''
    fetch(`/api/pipeline-quality-daily${suffix}`)
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        return response.json()
      })
      .then((data) => {
        if (requestId !== state.pipelineDailyRequest) return
        dataChanged = !samePayload(state.pipelineDailyData, data)
        state.pipelineDailyData = data
        state.pipelineDailyDates.welding = data?.welding?.selected_date || state.pipelineDailyDates.welding
        state.pipelineDailyDates.ndt = data?.ndt?.selected_date || state.pipelineDailyDates.ndt
        state.pipelineDailyCheckedAt = Date.now()
        if (dataChanged) state.pipelineDailyRevision += 1
      })
      .catch(() => {
        if (requestId !== state.pipelineDailyRequest) return
        state.pipelineDailyError = '每日完成量暂时无法读取，请稍后重试'
        state.pipelineDailyCheckedAt = Date.now()
      })
      .finally(() => {
        if (requestId !== state.pipelineDailyRequest) return
        state.pipelineDailyPending = false
        if (!hadData || dataChanged) {
          state.qualityRenderKey = ''
          renderQualityPage()
        }
      })
  }

  function refresh() {
    state.scheduled = false
    syncSheetTitle()
    syncDailyApiUsage()
    syncManualSyncButton()
    ensurePageTabs()
    syncHomeTabLayout()
    renderQualityPage()
    if (state.activePage === 'pipeline') requestPipelineDailyData()
    else if (state.activePage === 'heat-treatment') requestHeatTreatmentData()
    else if (state.activePage !== 'home') requestQualityData()
    const historyPanel = findPanel('最新焊接数据历史')
    if (historyPanel && historyPanel.style.display !== 'none') historyPanel.style.display = 'none'

    syncPipelineAudit()

    const ngPanel = findPanel('探伤不合格异常清单')
    if (!ngPanel) return

    ngPanel.style.flex = '1 1 100%'
    ngPanel.style.minWidth = '0'
    applyDetailLayout(ngPanel)
    const controls = ensureControls(ngPanel)
    const total = applySearch(ngPanel)
    const totalNode = controls?.querySelector('[data-ng-total]')
    const label = `不合格焊口总量：${total} 道`
    if (totalNode && totalNode.textContent !== label) totalNode.textContent = label
  }

  function scheduleRefresh() {
    if (state.scheduled) return
    state.scheduled = true
    requestAnimationFrame(refresh)
  }

  function addStyles() {
    if (document.getElementById('ng-search-enhancement-style')) return
    const style = document.createElement('style')
    style.id = 'ng-search-enhancement-style'
    style.textContent = `
      .ng-search-controls { margin-left: auto; display: flex; align-items: center; gap: 10px; }
      .ng-total { white-space: nowrap; font-size: 11px !important; }
      .ng-search-label { display: flex; align-items: center; gap: 6px; color: var(--text-muted); font-size: 11px; white-space: nowrap; }
      .ng-search-label input { width: 220px; height: 25px; border: 1px solid rgba(255, 59, 48, .36); border-radius: 3px; outline: none; background: rgba(3, 5, 12, .8); color: #fff; padding: 0 8px; font-size: 11px; }
      .ng-search-label input:focus { border-color: #ff4d4f; box-shadow: 0 0 7px rgba(255, 77, 79, .3); }
      .ng-search-label input::placeholder { color: #64748b; }
      .datav-panel [hidden] { display: none !important; }
      .sheet-source-title { position: absolute; color: #94a3b8; font-size: 15px; font-weight: 500; letter-spacing: .5px; white-space: nowrap; pointer-events: none; }
      .header-right .tencent-manual-sync { margin-left: 0 !important; padding: 4px !important; border: 0 !important; background: none !important; box-shadow: none !important; }
      .header-right .tencent-manual-sync:hover:not(:disabled) { color: var(--primary-color) !important; }
      .header-right .tencent-manual-sync:disabled { cursor: wait !important; opacity: .78; }
      .header-right .tencent-manual-sync svg { flex: 0 0 auto; width: 13px; height: 13px; }
      .header-right .tencent-manual-sync.is-syncing svg { animation: manual-sync-spin .9s linear infinite; }
      .header-right .tencent-manual-sync.is-success { border-color: rgba(41, 247, 203, .7) !important; color: #74fbdc !important; }
      .header-right .tencent-manual-sync.is-error { border-color: rgba(255, 99, 114, .72) !important; color: #ff8d99 !important; }
      .manual-sync-notice { position: fixed; z-index: 2000; top: 68px; right: 22px; max-width: 520px; padding: 9px 14px; border: 1px solid rgba(0, 242, 254, .5); background: rgba(3, 17, 38, .96); color: #dffeff; box-shadow: 0 0 18px rgba(0, 194, 255, .2); font-size: 12px; letter-spacing: .3px; }
      .manual-sync-notice.is-success { border-color: rgba(41, 247, 203, .62); color: #72fbd9; }
      .manual-sync-notice.is-error { border-color: rgba(255, 99, 114, .68); color: #ff929e; }
      @keyframes manual-sync-spin { to { transform: rotate(360deg); } }
      .pipeline-audit-issue { display: flex; flex-direction: column; gap: 6px; color: #fff; overflow-wrap: anywhere; }
      .pipeline-audit-issue-header, .pipeline-audit-issue-row { display: grid; grid-template-columns: 1.35fr .9fr 3.4fr; gap: 8px; align-items: start; }
      .pipeline-audit-issue-header { flex: 0 0 auto; color: var(--text-muted); font-size: 11px; font-weight: 600; border-bottom: 1px solid rgba(236, 72, 153, .2); padding-bottom: 5px; }
      .pipeline-audit-issue-viewport { flex: 1 1 0; min-height: 0; overflow: hidden; }
      .pipeline-audit-issue-track { line-height: 1.7; }
      .pipeline-audit-issue-row { padding: 4px 0; border-bottom: 1px solid rgba(255,255,255,.04); font-size: 12px; }
      .pipeline-audit-issue-row span:first-child { color: var(--secondary-color); font-weight: 600; }
      .pipeline-audit-issue-row span:nth-child(2) { font-family: monospace; font-weight: 600; }
      .pipeline-audit-issue-row span:last-child { white-space: pre-wrap; overflow-wrap: anywhere; }
      .pipeline-audit-issue.is-scrolling .pipeline-audit-issue-track { animation: none !important; }
      .quality-page-tabs { position: absolute; z-index: 40; top: 11px; left: 220px; display: flex; align-items: center; gap: 2px; height: 38px; padding: 3px 5px 3px 3px; border: 1px solid rgba(0, 242, 254, .32); background: linear-gradient(90deg, rgba(2, 21, 42, .95), rgba(4, 13, 30, .8)); box-shadow: inset 0 0 18px rgba(0, 242, 254, .08), 0 0 10px rgba(0, 118, 180, .08); clip-path: polygon(7px 0, 100% 0, calc(100% - 7px) 100%, 0 100%); }
      .quality-page-tabs::before { content: none; display: none; }
      .quality-page-tab { position: relative; height: 30px; border: 1px solid transparent; background: transparent; color: #7398ac; padding: 0 10px 0 20px; min-width: 61px; font-size: 11px; font-weight: 650; letter-spacing: .45px; text-align: left; cursor: pointer; transition: color .2s ease, background .2s ease, border-color .2s ease, box-shadow .2s ease; }
      .quality-page-tab::before { position: absolute; top: 50%; left: 9px; width: 4px; height: 4px; content: ''; background: #477c96; box-shadow: 0 0 5px rgba(77, 188, 221, .35); transform: translateY(-50%) rotate(45deg); transition: background .2s ease, box-shadow .2s ease; }
      .quality-page-tab:hover { color: #d2fbff; border-color: rgba(0, 242, 254, .22); background: rgba(0, 150, 218, .09); }
      .quality-page-tab.is-active { color: #eaffff; border-color: rgba(0, 242, 254, .42); background: linear-gradient(90deg, rgba(0, 242, 254, .09), rgba(28, 122, 210, .36), rgba(0, 242, 254, .08)); box-shadow: inset 0 0 12px rgba(0, 242, 254, .1); text-shadow: 0 0 8px rgba(0, 242, 254, .8); }
      .quality-page-tab.is-active::before { background: #c8ffff; box-shadow: 0 0 8px #00f2fe; }
      .quality-page-tab.is-active::after { content: ''; position: absolute; right: 7px; bottom: -1px; left: 7px; height: 2px; background: #00f2fe; box-shadow: 0 0 9px #00f2fe; }
      .quality-page-tabs-spacer { width: 100%; min-height: 34px; flex: 0 0 34px; }
      .quality-page-tabs.is-home-layout { top: 84px; right: 20px; left: 20px; justify-content: flex-start; height: 32px; padding: 2px 10px; border-color: rgba(0, 242, 254, .3); background: linear-gradient(90deg, rgba(4, 25, 50, .9), rgba(8, 38, 69, .64) 28%, rgba(3, 18, 38, .42)); box-shadow: inset 0 0 15px rgba(0, 242, 254, .06); clip-path: polygon(5px 0, calc(100% - 5px) 0, 100% 50%, calc(100% - 5px) 100%, 5px 100%, 0 50%); }
      .quality-page-tabs.is-home-layout .quality-page-tab { min-width: 116px; height: 26px; margin-right: 4px; padding: 0 17px 0 25px; border-color: rgba(58, 158, 198, .3); background: linear-gradient(110deg, rgba(9, 44, 76, .74), rgba(3, 17, 37, .78)); color: #8fb5c7; font-size: 11px; letter-spacing: .9px; clip-path: polygon(7px 0, 100% 0, calc(100% - 7px) 100%, 0 100%); }
      .quality-page-tabs.is-home-layout .quality-page-tab::before { left: 11px; background: #5089a0; }
      .quality-page-tabs.is-home-layout .quality-page-tab:hover { border-color: rgba(0, 242, 254, .48); background: linear-gradient(110deg, rgba(12, 78, 119, .8), rgba(4, 31, 61, .82)); color: #ddfdff; }
      .quality-page-tabs.is-home-layout .quality-page-tab.is-active { border-color: rgba(103, 246, 255, .76); background: linear-gradient(105deg, rgba(0, 242, 254, .15), rgba(12, 118, 190, .75), rgba(0, 242, 254, .1)); background-size: 220% 100%; box-shadow: inset 0 0 15px rgba(106, 247, 255, .2), 0 0 12px rgba(0, 194, 255, .22); color: #f0ffff; animation: quality-tab-energy 3s linear infinite; }
      .quality-page-tabs.is-home-layout .quality-page-tab.is-active::after { right: 11px; left: 11px; }
      @keyframes quality-tab-energy { 0% { background-position: 0 0; } 100% { background-position: 220% 0; } }
      .kpi-container { gap: 10px !important; }
      .kpi-container > .kpi-card-item { min-height: 0 !important; padding: 9px 12px !important; }
      .kpi-container > .kpi-card-item > div:first-child { gap: 2px !important; }
      .kpi-container > .kpi-card-item > div:first-child > span { line-height: 1.15 !important; }
      .kpi-container > .kpi-card-item > div:first-child > span:first-of-type { font-size: 12px !important; }
      .kpi-container > .kpi-card-item > div:first-child > span:nth-of-type(2) { font-size: 24px !important; }
      .kpi-container > .kpi-card-item > div:first-child > span:last-of-type { font-size: 9px !important; }
      .quality-analysis-page { position: absolute; z-index: 20; inset: 132px 20px 14px; display: flex; flex-direction: column; gap: 8px; min-height: 0; overflow: hidden; color: #e2f6ff; background: radial-gradient(ellipse at 50% 0, rgba(15, 89, 151, .14), transparent 52%), rgba(3, 5, 12, .96); }
      .quality-analysis-page[hidden] { display: none !important; }
      .quality-analysis-header { display: flex; align-items: flex-end; justify-content: space-between; min-height: 40px; padding: 0 8px 6px 12px; border-bottom: 1px solid rgba(0, 242, 254, .28); background: linear-gradient(90deg, rgba(0, 242, 254, .08), transparent 48%); }
      .quality-analysis-heading h2 { margin: 0; color: #ecfeff; font-size: 20px; line-height: 1.05; letter-spacing: 1.6px; text-shadow: 0 0 15px rgba(0, 242, 254, .45); }
      .quality-analysis-heading p { margin: 4px 0 0; color: #6f99af; font-size: 10px; letter-spacing: .35px; }
      .quality-live-tag { color: #29f7cb; font-size: 11px; white-space: nowrap; }
      .quality-live-tag::before { content: '●'; margin-right: 6px; font-size: 8px; animation: quality-live 1.7s ease-in-out infinite; }
      .quality-kpi-grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 8px; flex: 0 0 auto; }
      .quality-kpi { position: relative; min-height: 76px; overflow: hidden; padding: 9px 12px; border: 1px solid rgba(55, 138, 201, .28); background: linear-gradient(135deg, rgba(7, 24, 49, .94), rgba(5, 12, 29, .88)); box-shadow: inset 0 0 24px rgba(0, 112, 190, .05); }
      .quality-kpi::before { content: ''; position: absolute; top: 0; left: 0; width: 26px; height: 2px; background: var(--primary-color, #00f2fe); box-shadow: 0 0 8px currentColor; }
      .quality-kpi-label, .quality-kpi-detail { display: block; color: #7ca0b4; font-size: 10px; }
      .quality-kpi-value { display: block; margin: 5px 0 3px; color: #bffcff; font-size: 22px; line-height: 1; font-family: 'DIN Alternate', 'Arial Narrow', sans-serif; letter-spacing: .5px; }
      .quality-kpi-detail { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .quality-kpi.is-success .quality-kpi-value, .quality-rate-ok { color: #28e7b7 !important; }
      .quality-kpi.is-danger .quality-kpi-value, .quality-rate-warn { color: #ff6b75 !important; }
      .quality-kpi.is-warning .quality-kpi-value { color: #f5bb4a; }
      .quality-kpi.is-primary .quality-kpi-value { color: #00e9ff; }
      .quality-layout { display: grid; min-height: 0; flex: 1 1 auto; gap: 8px; }
      .quality-layout-welder { grid-template-rows: minmax(168px, .72fr) minmax(228px, 1.28fr); }
      .quality-layout-audit { grid-template-columns: repeat(3, minmax(0, 1fr)); }
      .quality-analysis-page.is-audit-dashboard { gap: 5px; }
      .is-audit-dashboard .quality-analysis-header { min-height: 30px; padding: 0 8px 4px 12px; }
      .is-audit-dashboard .quality-analysis-heading h2 { font-size: 17px; }
      .is-audit-dashboard .quality-analysis-heading p { margin-top: 2px; font-size: 8px; }
      .is-audit-dashboard .quality-live-tag { font-size: 8px; }
      .is-audit-dashboard .quality-kpi-grid { gap: 5px; }
      .is-audit-dashboard .quality-kpi { min-height: 59px; padding: 7px 9px; }
      .is-audit-dashboard .quality-kpi-label, .is-audit-dashboard .quality-kpi-detail { font-size: 8px; }
      .is-audit-dashboard .quality-kpi-value { margin: 3px 0 1px; font-size: 19px; }
      .is-audit-dashboard .quality-layout { gap: 5px; }
      .is-audit-dashboard .quality-card-header { min-height: 31px; padding: 0 9px; }
      .is-audit-dashboard .quality-card-header h3 { font-size: 11px; }
      .is-audit-dashboard .quality-card-header span { font-size: 8px; }
      .is-audit-dashboard .quality-card-body { padding: 3px 7px 5px; }
      .quality-analysis-page.is-pipeline-dashboard { gap: 9px; background: radial-gradient(ellipse at 20% 0, rgba(0, 229, 255, .12), transparent 35%), radial-gradient(ellipse at 82% 100%, rgba(117, 73, 255, .1), transparent 42%), #030914; }
      .is-pipeline-dashboard .quality-analysis-header { min-height: 40px; padding: 0 11px 7px 14px; border-bottom-color: rgba(74, 228, 255, .36); background: linear-gradient(90deg, rgba(0, 225, 255, .11), rgba(0, 76, 141, .1) 46%, transparent); }
      .is-pipeline-dashboard .quality-analysis-heading h2 { font-size: 20px; letter-spacing: 2.8px; }
      .is-pipeline-dashboard .quality-analysis-heading p { margin-top: 4px; font-size: 10px; }
      .pipeline-command-grid { position: relative; display: grid; min-height: 0; flex: 1 1 auto; grid-template-columns: repeat(2, minmax(0, 1fr)); grid-template-rows: minmax(0, 1.12fr) minmax(0, .88fr); gap: 10px; }
      .pipeline-command-grid::before { position: absolute; z-index: 0; inset: 0; pointer-events: none; content: ''; opacity: .35; background-image: linear-gradient(rgba(71, 205, 240, .08) 1px, transparent 1px), linear-gradient(90deg, rgba(71, 205, 240, .08) 1px, transparent 1px); background-size: 26px 26px; mask-image: linear-gradient(90deg, transparent, #000 12%, #000 88%, transparent); }
      .pipeline-command-grid > .quality-card { z-index: 1; }
      .pipeline-command-grid .quality-card { position: relative; overflow: hidden; border-color: rgba(65, 166, 213, .4); background: linear-gradient(143deg, rgba(8, 32, 63, .96), rgba(3, 12, 30, .96) 64%, rgba(3, 21, 43, .94)); box-shadow: inset 0 0 32px rgba(18, 155, 221, .07), 0 6px 18px rgba(0, 0, 0, .17); }
      .pipeline-command-grid .quality-card::before { position: absolute; top: 0; left: 0; width: 48px; height: 2px; content: ''; background: #04e7ff; box-shadow: 0 0 13px #04e7ff; }
      .pipeline-command-grid .quality-card::after { position: absolute; right: 9px; bottom: 9px; width: 9px; height: 9px; content: ''; border-right: 1px solid rgba(0, 237, 255, .8); border-bottom: 1px solid rgba(0, 237, 255, .8); }
      .pipeline-command-grid .quality-card.is-ndt::before { background: #9478ff; box-shadow: 0 0 13px #9478ff; }
      .pipeline-command-grid .quality-card-header { position: relative; z-index: 1; min-height: 38px; padding: 0 12px; border-bottom-color: rgba(74, 180, 228, .22); background: linear-gradient(90deg, rgba(0, 232, 255, .11), transparent 70%); }
      .pipeline-command-grid .is-ndt .quality-card-header { background: linear-gradient(90deg, rgba(145, 113, 255, .13), transparent 70%); }
      .pipeline-command-grid .quality-card-header h3 { font-size: 13px; letter-spacing: 1px; }
      .pipeline-command-grid .quality-card-header span { margin-top: 1px; font-size: 9px; letter-spacing: .25px; }
      .pipeline-command-grid .quality-card-body { position: relative; z-index: 1; display: flex; min-height: 0; flex-direction: column; padding: 8px 12px 10px; }
      .pipeline-date-control { display: inline-flex; align-items: center; gap: 5px; margin-left: auto; color: #7cbfd1; font-size: 9px; white-space: nowrap; }
      .pipeline-date-control > span { margin: 0 !important; color: #8cc9db; font-size: 9px !important; }
      .pipeline-date-control input { width: 114px; height: 23px; border: 1px solid rgba(0, 237, 255, .38); border-radius: 0; outline: none; background: rgba(1, 13, 31, .86); color: #bffcff; padding: 0 4px; font-family: 'DIN Alternate', monospace; font-size: 10px; letter-spacing: .3px; color-scheme: dark; box-shadow: inset 0 0 10px rgba(0, 225, 255, .06); }
      .is-ndt .pipeline-date-control input { border-color: rgba(159, 130, 255, .48); color: #d4c9ff; }
      .pipeline-date-control input:focus { border-color: #27f4ff; box-shadow: 0 0 10px rgba(0, 232, 255, .28); }
      .pipeline-day-hero { display: grid; grid-template-columns: 1fr auto 1fr; align-items: end; min-height: 72px; padding: 1px 2px 5px; border-bottom: 1px solid rgba(93, 173, 213, .15); }
      .pipeline-day-meta { align-self: center; min-width: 0; }
      .pipeline-day-code { display: block; color: #09e5f8; font-family: 'DIN Alternate', monospace; font-size: 10px; letter-spacing: 1.2px; }
      .is-ndt .pipeline-day-code { color: #a999ff; }
      .pipeline-day-meta small { display: block; margin-top: 4px; color: #6e9ab0; font-size: 10px; white-space: nowrap; }
      .pipeline-day-metric { display: flex; align-items: baseline; padding: 0 15px; border-right: 1px solid rgba(54, 191, 228, .16); border-left: 1px solid rgba(54, 191, 228, .16); text-shadow: 0 0 14px rgba(0, 234, 255, .38); }
      .is-ndt .pipeline-day-metric { text-shadow: 0 0 14px rgba(144, 119, 255, .46); }
      .pipeline-day-metric strong { color: #4bf5ff; font-family: 'DIN Alternate', 'Arial Narrow', sans-serif; font-size: 42px; line-height: .92; letter-spacing: 1px; }
      .is-ndt .pipeline-day-metric strong { color: #ae9dff; }
      .pipeline-day-metric span { margin-left: 4px; color: #94c8d7; font-size: 12px; }
      .pipeline-day-pipelines { justify-self: end; min-width: 66px; text-align: right; }
      .pipeline-day-pipelines span, .pipeline-day-pipelines strong { display: block; }
      .pipeline-day-pipelines span { color: #6690a7; font-size: 9px; }
      .pipeline-day-pipelines strong { margin-top: 4px; color: #d6f9ff; font-family: 'DIN Alternate', monospace; font-size: 15px; }
      .pipeline-day-list-title { display: flex; justify-content: space-between; padding: 8px 2px 4px; color: #6994a9; font-size: 9px; letter-spacing: .45px; }
      .pipeline-day-list { min-height: 0; flex: 1 1 auto; overflow: auto; padding-right: 3px; scrollbar-color: rgba(0, 240, 255, .4) transparent; }
      .pipeline-day-empty { display: flex; align-items: center; justify-content: center; height: 100%; min-height: 72px; color: #668da3; font-size: 11px; }
      .pipeline-day-row { display: grid; grid-template-columns: minmax(130px, .95fr) minmax(80px, 1.4fr) 48px; align-items: center; min-height: 27px; gap: 9px; border-top: 1px solid rgba(99, 164, 199, .1); }
      .pipeline-day-row-lead { display: flex; min-width: 0; align-items: center; gap: 7px; }
      .pipeline-day-rank { width: 18px; color: #527d95; font-family: monospace; font-size: 10px; }
      .pipeline-day-row-lead strong { overflow: hidden; color: #cceff7; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
      .pipeline-day-meter { height: 5px; overflow: hidden; background: repeating-linear-gradient(90deg, rgba(60, 148, 183, .2) 0 9px, transparent 9px 12px); }
      .pipeline-day-meter i { display: block; height: 100%; transition: width .35s ease; }
      .is-welding .pipeline-day-meter i { background: linear-gradient(90deg, #087fc9, #19eff2); box-shadow: 0 0 9px rgba(25, 239, 242, .75); }
      .is-ndt .pipeline-day-meter i { background: linear-gradient(90deg, #553fc7, #b89fff); box-shadow: 0 0 9px rgba(184, 159, 255, .75); }
      .pipeline-day-row-value { color: #a9eaf1; font-family: 'DIN Alternate', monospace; font-size: 12px; text-align: right; }
      .is-ndt .pipeline-day-row-value { color: #d3c7ff; }
      .pipeline-trend-card .quality-card-body { padding-bottom: 8px; }
      .pipeline-trend-selected { display: grid; min-width: 102px; margin-left: auto; text-align: right; }
      .pipeline-trend-selected span { color: #648aa0 !important; font-family: monospace; font-size: 8px !important; letter-spacing: .65px; }
      .pipeline-trend-selected strong { margin-top: 2px; color: #90dce4; font-family: 'DIN Alternate', monospace; font-size: 10px; }
      .is-ndt .pipeline-trend-selected strong { color: #c1b5ff; }
      .pipeline-trend-summary { display: flex; align-items: baseline; gap: 8px; min-height: 27px; }
      .pipeline-trend-summary > span { color: #729bb0; font-size: 10px; }
      .pipeline-trend-summary strong { color: #29eff6; font-family: 'DIN Alternate', monospace; font-size: 20px; line-height: 1; }
      .is-ndt .pipeline-trend-summary strong { color: #ae9cff; }
      .pipeline-trend-summary small { overflow: hidden; margin-left: auto; color: #56778a; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
      .pipeline-trend-chart { display: grid; min-height: 0; flex: 1 1 auto; grid-template-columns: repeat(14, minmax(0, 1fr)); align-items: end; gap: 5px; padding: 5px 2px 0; }
      .pipeline-trend-column { display: grid; min-width: 0; height: 100%; grid-template-rows: 14px minmax(32px, 1fr) 12px; align-items: end; gap: 3px; text-align: center; }
      .pipeline-trend-value { overflow: hidden; color: #6eabb7; font-family: 'DIN Alternate', monospace; font-size: 9px; font-weight: 500; text-overflow: ellipsis; white-space: nowrap; }
      .pipeline-trend-rail { position: relative; height: 100%; overflow: hidden; border-bottom: 1px solid rgba(50, 175, 204, .27); background: repeating-linear-gradient(0deg, rgba(70, 162, 195, .1) 0 1px, transparent 1px 19px); }
      .pipeline-trend-rail i { position: absolute; right: 17%; bottom: 0; left: 17%; min-height: 2px; background: linear-gradient(#48f3fb, #0879c5); box-shadow: 0 0 11px rgba(47, 239, 248, .57); transition: height .35s ease; }
      .is-ndt .pipeline-trend-rail i { background: linear-gradient(#c3aeff, #5640c9); box-shadow: 0 0 11px rgba(184, 158, 255, .62); }
      .pipeline-trend-column.is-selected .pipeline-trend-rail { background-color: rgba(13, 219, 242, .09); outline: 1px solid rgba(22, 233, 247, .56); outline-offset: -1px; }
      .is-ndt .pipeline-trend-column.is-selected .pipeline-trend-rail { background-color: rgba(164, 131, 255, .12); outline-color: rgba(183, 158, 255, .72); }
      .pipeline-trend-column.is-selected .pipeline-trend-value { color: #e5ffff; text-shadow: 0 0 8px #18eef6; }
      .pipeline-trend-label { overflow: hidden; color: #577b90; font-family: monospace; font-size: 8px; text-overflow: clip; white-space: nowrap; }
      .pipeline-trend-column.is-selected .pipeline-trend-label { color: #aaf5f9; }
      .pipeline-trend-empty { display: flex; align-items: center; justify-content: center; grid-column: 1 / -1; min-height: 80px; color: #668da3; font-size: 11px; }
      .quality-card { display: flex; min-width: 0; min-height: 0; flex-direction: column; border: 1px solid rgba(38, 143, 207, .32); background: linear-gradient(160deg, rgba(8, 27, 54, .92), rgba(3, 9, 22, .93)); box-shadow: inset 0 0 36px rgba(0, 125, 196, .04); }
      .quality-card-header { display: flex; align-items: center; min-height: 36px; padding: 0 12px; border-bottom: 1px solid rgba(46, 148, 214, .2); background: linear-gradient(90deg, rgba(0, 242, 254, .08), transparent 62%); }
      .quality-card-header h3 { margin: 0; color: #d8faff; font-size: 13px; letter-spacing: .5px; }
      .quality-card-header span { display: inline-block; margin-top: 2px; color: #608ca5; font-size: 9px; }
      .quality-card-body { min-height: 0; flex: 1 1 auto; overflow: hidden; padding: 5px 10px 8px; }
      .quality-welder-charts { display: grid; min-height: 0; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
      .quality-welder-charts .quality-card { position: relative; overflow: hidden; }
      .quality-welder-charts .quality-card::before { position: absolute; top: 0; right: 15px; width: 72px; height: 2px; content: ''; background: #00f2fe; box-shadow: 0 0 12px #00f2fe; }
      .quality-scan-count { margin-left: auto; padding: 3px 7px; border: 1px solid currentColor; font-family: 'DIN Alternate', monospace; font-size: 11px !important; letter-spacing: .7px; }
      .quality-scan-count.is-success { color: #29f7cb; background: rgba(41, 247, 203, .06); }
      .quality-scan-count.is-danger { color: #ff6978; background: rgba(255, 86, 103, .07); }
      .quality-scan-viewport { height: 100%; overflow: hidden; }
      .quality-scan-track { height: 100%; will-change: transform; }
      .quality-scan-list { display: grid; height: 100%; grid-template-columns: repeat(2, minmax(0, 1fr)); grid-auto-rows: minmax(34px, 1fr); column-gap: 14px; }
      .quality-scan-card.is-scrolling .quality-scan-track { height: auto; animation: none !important; }
      .quality-scan-card.is-scrolling .quality-scan-list { height: auto; grid-auto-rows: 36px; }
      .quality-scan-row { display: grid; grid-template-columns: minmax(62px, .82fr) minmax(85px, 1.5fr) 51px; align-items: center; gap: 10px; min-width: 0; border-bottom: 1px solid rgba(123, 181, 218, .11); }
      .quality-scan-label { min-width: 0; }
      .quality-scan-label strong, .quality-scan-label small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .quality-scan-label strong { color: #d3f6ff; font-size: 12px; }
      .quality-scan-label small { margin-top: 2px; color: #638aa1; font-size: 9px; }
      .quality-scan-meter { position: relative; height: 6px; overflow: hidden; background: repeating-linear-gradient(90deg, rgba(91, 143, 176, .17) 0 10px, transparent 10px 13px); }
      .quality-scan-meter::after { position: absolute; top: -3px; right: 10%; bottom: -3px; width: 1px; content: ''; background: rgba(227, 252, 255, .36); }
      .quality-scan-meter i { display: block; height: 100%; transition: width .35s ease; }
      .quality-scan-row.is-success .quality-scan-meter i { background: linear-gradient(90deg, #097ad7, #29f7cb); box-shadow: 0 0 10px rgba(41, 247, 203, .9); }
      .quality-scan-row.is-danger .quality-scan-meter i { background: linear-gradient(90deg, #d73658, #ffb54a); box-shadow: 0 0 10px rgba(255, 91, 108, .8); }
      .quality-scan-value { font-family: 'DIN Alternate', monospace; font-size: 14px; text-align: right; }
      .quality-scan-row.is-success .quality-scan-value { color: #29f7cb; }
      .quality-scan-row.is-danger .quality-scan-value { color: #ff717e; }
      .quality-table-wrap { height: 100%; overflow: auto; scrollbar-color: rgba(0, 242, 254, .45) transparent; }
      .quality-welder-table-host { height: 100%; min-height: 0; }
      .quality-welder-table-host .quality-table-wrap { height: 100%; }
      .quality-table-search { display: flex; align-items: center; gap: 6px; margin-left: auto; color: #00f2fe; font-size: 15px; }
      .quality-table-search input { width: 168px; height: 25px; border: 1px solid rgba(0, 242, 254, .28); outline: 0; background: rgba(1, 10, 25, .72); color: #d9fbff; padding: 0 8px; font-size: 11px; transition: border-color .18s ease, box-shadow .18s ease; }
      .quality-table-search input::placeholder { color: #527488; }
      .quality-table-search input:focus { border-color: #00f2fe; box-shadow: 0 0 9px rgba(0, 242, 254, .28); }
      .quality-table-no-match { display: flex; align-items: center; justify-content: center; height: 100%; min-height: 96px; color: #6e9ab0; font-size: 12px; }
      .quality-table { width: 100%; border-collapse: collapse; font-size: 12px; }
      .quality-table th { position: sticky; z-index: 1; top: 0; padding: 9px 8px; color: #76a3ba; background: #081831; font-size: 11px; font-weight: 600; text-align: left; white-space: nowrap; }
      .quality-table td { max-width: 220px; padding: 8px; border-bottom: 1px solid rgba(255, 255, 255, .05); color: #d2ebf5; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .quality-table tbody tr:nth-child(even) { background: rgba(18, 77, 123, .055); }
      .quality-table tbody tr:hover { background: rgba(0, 242, 254, .075); }
      .quality-table td:nth-child(3), .quality-table td:nth-child(4), .quality-table td:nth-child(5) { font-family: 'DIN Alternate', monospace; }
      .quality-closure-card .quality-card-body { display: flex; min-height: 0; }
      .quality-closure-card { border-color: rgba(255, 99, 114, .76) !important; background: linear-gradient(143deg, rgba(66, 14, 27, .56), rgba(11, 13, 27, .96) 66%, rgba(52, 15, 29, .46)) !important; box-shadow: inset 0 0 30px rgba(255, 59, 88, .11), 0 0 18px rgba(255, 59, 88, .08); }
      .quality-closure-card .quality-card-header { border-bottom-color: rgba(255, 99, 114, .36); background: linear-gradient(90deg, rgba(255, 59, 88, .12), transparent 72%); }
      .quality-closure-card .quality-card-header h3 { color: #ffd8dc; text-shadow: 0 0 10px rgba(255, 99, 114, .4); }
      .quality-closure-scroller { display: flex; min-width: 0; min-height: 0; flex: 1 1 auto; flex-direction: column; }
      .quality-closure-summary { display: flex; align-items: baseline; justify-content: space-between; min-height: 31px; padding: 0 2px 5px; border-bottom: 1px solid rgba(245, 187, 74, .18); color: #cf9f44; font-size: 10px; letter-spacing: .35px; }
      .quality-closure-summary strong { color: #ffd36a; font-family: 'DIN Alternate', monospace; font-size: 17px; line-height: 1; text-shadow: 0 0 11px rgba(245, 187, 74, .34); }
      .quality-closure-row { display: grid; min-width: 0; grid-template-columns: minmax(52px, 1fr) minmax(43px, .78fr) 58px 64px minmax(68px, 1.14fr); align-items: center; column-gap: 6px; min-height: 30px; border-bottom: 1px solid rgba(255, 255, 255, .05); color: #d2ebf5; font-size: 10px; }
      .quality-closure-row:nth-child(even) { background: rgba(127, 86, 15, .07); }
      .quality-closure-row > span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .quality-closure-row.is-header { min-height: 31px; color: #caa35d; font-size: 9px; font-weight: 600; }
      .quality-closure-status-heading { justify-self: stretch; text-align: center; }
      .quality-closure-row.is-risk-row { border-left: 2px solid #ff6372; background: linear-gradient(90deg, rgba(255, 59, 88, .18), rgba(255, 59, 88, .045) 65%, transparent) !important; box-shadow: inset 8px 0 15px rgba(255, 59, 88, .07); }
      .quality-closure-row.is-risk-row > span:first-child, .quality-closure-row.is-risk-row > span:nth-child(2) { color: #ffe3e6; font-weight: 700; }
      .quality-closure-status { justify-self: stretch; color: #f6bf4d; font-size: 9px; text-align: center; }
      .quality-closure-row.is-risk-row .quality-closure-status { padding: 3px 5px; border: 1px solid rgba(255, 99, 114, .5); background: rgba(255, 59, 88, .16); color: #ffb5be; font-weight: 700; text-shadow: 0 0 7px rgba(255, 99, 114, .45); }
      .quality-closure-viewport { position: relative; min-height: 0; flex: 1 1 auto; overflow: hidden; }
      .quality-closure-track { will-change: transform; }
      .quality-closure-card.is-closure-scrolling .quality-closure-track { animation: none !important; }
      .quality-unreviewed-film-card { border-color: rgba(255, 188, 75, .76) !important; background: linear-gradient(143deg, rgba(63, 42, 10, .53), rgba(11, 15, 27, .96) 67%, rgba(60, 35, 7, .43)) !important; box-shadow: inset 0 0 30px rgba(255, 181, 57, .11), 0 0 18px rgba(255, 181, 57, .07); }
      .quality-unreviewed-film-card .quality-card-header { border-bottom-color: rgba(255, 188, 75, .36); background: linear-gradient(90deg, rgba(255, 181, 57, .12), transparent 72%); }
      .quality-unreviewed-film-card .quality-card-header h3 { color: #ffe7bd; text-shadow: 0 0 10px rgba(255, 181, 57, .36); }
      .quality-unreviewed-film-scroller { display: flex; min-width: 0; min-height: 0; flex: 1 1 auto; flex-direction: column; padding: 0 10px 8px; }
      .quality-unreviewed-film-row { display: grid; min-width: 0; grid-template-columns: minmax(60px, 1fr) minmax(48px, .82fr) 62px; align-items: center; column-gap: 7px; min-height: 30px; border-bottom: 1px solid rgba(255, 255, 255, .05); color: #d2ebf5; font-size: 10px; }
      .quality-unreviewed-film-row:nth-child(even) { background: rgba(18, 77, 123, .055); }
      .quality-unreviewed-film-row > span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .quality-unreviewed-film-row > span:last-child { font-family: 'DIN Alternate', monospace; font-size: 10px; text-align: right; }
      .quality-unreviewed-film-row.is-header { min-height: 32px; color: #76a3ba; font-size: 9px; font-weight: 600; }
      .quality-unreviewed-film-row.is-header > span:last-child { font-family: inherit; text-align: right; }
      .quality-unreviewed-film-row.is-risk-row { border-left: 2px solid #ffbd55; background: linear-gradient(90deg, rgba(255, 181, 57, .17), rgba(255, 181, 57, .045) 68%, transparent) !important; box-shadow: inset 8px 0 15px rgba(255, 181, 57, .06); }
      .quality-unreviewed-film-row.is-risk-row > span:first-child, .quality-unreviewed-film-row.is-risk-row > span:nth-child(2) { color: #fff0d1; font-weight: 700; }
      .quality-unreviewed-film-row.is-risk-row > span:last-child { padding: 3px 5px; border: 1px solid rgba(255, 188, 75, .55); background: rgba(255, 181, 57, .16); color: #ffe0a0; font-weight: 700; text-shadow: 0 0 7px rgba(255, 181, 57, .42); }
      .quality-unreviewed-film-viewport { position: relative; min-height: 0; flex: 1 1 auto; overflow: hidden; }
      .quality-unreviewed-film-track { will-change: transform; }
      .quality-unreviewed-film-card .quality-card-body { display: flex; min-height: 0; }
      .quality-unreviewed-film-empty { display: flex; align-items: center; justify-content: center; min-height: 84px; color: #6e9ab0; font-size: 11px; }
      .quality-unreviewed-film-card.is-unreviewed-scrolling .quality-unreviewed-film-track { animation: none !important; }
      .quality-audit-issue-card .quality-card-body { display: flex; min-height: 0; }
      .quality-audit-issue-scroller { display: flex; min-width: 0; min-height: 0; flex: 1 1 auto; flex-direction: column; }
      .quality-audit-issue-row { display: grid; min-width: 0; grid-template-columns: minmax(58px, .95fr) minmax(44px, .72fr) minmax(96px, 1.9fr) 54px; align-items: center; column-gap: 7px; min-height: 31px; border-bottom: 1px solid rgba(255, 255, 255, .05); color: #d2ebf5; font-size: 10px; }
      .quality-audit-issue-row:nth-child(even) { background: rgba(18, 77, 123, .055); }
      .quality-audit-issue-row > span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .quality-audit-issue-row:not(.is-header) > span:nth-child(3) { min-width: 0; overflow: visible; overflow-wrap: anywhere; white-space: normal; line-height: 1.35; padding: 5px 0; }
      .quality-audit-issue-row > span:last-child { font-family: 'DIN Alternate', monospace; font-size: 10px; text-align: right; }
      .quality-audit-issue-row.is-header { min-height: 33px; padding: 0 1px; border-bottom-color: rgba(58, 144, 200, .28); background: #081831; color: #76a3ba; font-size: 10px; font-weight: 600; }
      .quality-audit-issue-row.is-header > span:last-child { font-family: inherit; text-align: right; }
      .quality-audit-issue-viewport { position: relative; min-height: 0; flex: 1 1 auto; overflow: hidden; }
      .quality-audit-issue-track { will-change: transform; }
      .quality-audit-issue-list { min-width: 0; }
      .quality-audit-issue-card.is-scrolling .quality-audit-issue-track { animation: none !important; }
      .quality-analysis-page.is-heat-treatment-dashboard { gap: 10px; background: radial-gradient(ellipse at 16% 0, rgba(255, 164, 51, .12), transparent 32%), radial-gradient(ellipse at 84% 100%, rgba(0, 229, 255, .1), transparent 40%), #030914; }
      .is-heat-treatment-dashboard .quality-analysis-header { min-height: 42px; padding: 0 12px 7px 14px; border-bottom-color: rgba(255, 178, 55, .38); background: linear-gradient(90deg, rgba(255, 174, 52, .1), rgba(0, 177, 221, .08) 49%, transparent); }
      .is-heat-treatment-dashboard .quality-analysis-heading h2 { color: #fff4de; letter-spacing: 2.7px; text-shadow: 0 0 16px rgba(255, 174, 52, .38); }
      .is-heat-treatment-dashboard .quality-live-tag { color: #ffd783; border-color: rgba(255, 186, 70, .28); background: rgba(114, 72, 11, .22); }
      .heat-treatment-kpi-grid { display: grid; flex: 0 0 auto; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 11px; }
      .is-heat-treatment-dashboard .quality-kpi { position: relative; overflow: hidden; min-height: 72px; border-color: rgba(38, 148, 196, .4); background: linear-gradient(120deg, rgba(9, 32, 55, .96), rgba(4, 14, 28, .94)); }
      .is-heat-treatment-dashboard .quality-kpi::before { position: absolute; top: 0; left: 0; width: 42%; height: 1px; content: ''; background: linear-gradient(90deg, #ffb13d, #1deaf4, transparent); box-shadow: 0 0 10px rgba(255, 185, 67, .6); }
      .heat-treatment-list-overview { display: flex; align-items: center; min-height: 32px; flex: 0 0 auto; padding: 0 4px 0 8px; border-left: 2px solid #ffbd4d; background: linear-gradient(90deg, rgba(255, 180, 55, .1), rgba(0, 224, 244, .05) 45%, transparent); }
      .heat-treatment-list-overview-text { display: flex; align-items: baseline; gap: 10px; min-width: 0; }
      .heat-treatment-list-overview-text strong { color: #e9fbff; font-size: 13px; letter-spacing: .8px; text-shadow: 0 0 9px rgba(45, 235, 245, .35); }
      .heat-treatment-list-overview-text span { overflow: hidden; color: #739aad; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
      .heat-treatment-lists { display: grid; min-height: 0; flex: 1 1 auto; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
      .heat-treatment-list-card { position: relative; min-height: 0; overflow: hidden; border-color: rgba(39, 168, 197, .48); background: linear-gradient(150deg, rgba(7, 31, 54, .95), rgba(3, 10, 22, .96) 68%, rgba(61, 38, 8, .22)); }
      .heat-treatment-list-card::before { position: absolute; z-index: 1; top: 0; right: 14px; width: 110px; height: 2px; content: ''; background: linear-gradient(90deg, transparent, #ffbd4d, #31eefa); box-shadow: 0 0 14px rgba(255, 188, 75, .72); }
      .heat-treatment-list-card .quality-card-header { min-height: 42px; border-bottom-color: rgba(58, 174, 206, .28); background: linear-gradient(90deg, rgba(0, 225, 242, .085), rgba(255, 169, 45, .065) 52%, transparent); }
      .heat-treatment-list-card .quality-card-header h3 { color: #e8fbff; letter-spacing: .85px; }
      .heat-treatment-list-card .quality-card-body { display: flex; min-height: 0; padding: 0 13px 10px; }
      .heat-treatment-completed-card { border-color: rgba(45, 232, 190, .48); background: linear-gradient(150deg, rgba(5, 43, 52, .9), rgba(3, 13, 25, .97) 70%); }
      .heat-treatment-completed-card .quality-card-header { border-bottom-color: rgba(45, 232, 190, .32); background: linear-gradient(90deg, rgba(45, 232, 190, .11), transparent 68%); }
      .heat-treatment-completed-card .quality-card-header h3 { color: #c9fff0; }
      .heat-treatment-pending-card { border-color: rgba(255, 91, 105, .74); background: linear-gradient(150deg, rgba(64, 13, 28, .7), rgba(14, 10, 24, .98) 70%, rgba(67, 35, 7, .35)); box-shadow: inset 0 0 28px rgba(255, 61, 90, .1), 0 0 16px rgba(255, 61, 90, .07); }
      .heat-treatment-pending-card .quality-card-header { border-bottom-color: rgba(255, 98, 112, .42); background: linear-gradient(90deg, rgba(255, 61, 90, .17), rgba(255, 183, 62, .07) 58%, transparent); }
      .heat-treatment-pending-card .quality-card-header h3 { color: #ffe0e4; text-shadow: 0 0 10px rgba(255, 91, 105, .4); }
      .heat-treatment-search { display: flex; align-items: center; margin-left: auto; }
      .heat-treatment-search::before { margin-right: 7px; color: #34eefa; content: '⌕'; font-size: 17px; line-height: 1; text-shadow: 0 0 9px rgba(45, 238, 250, .7); }
      .heat-treatment-search input { width: 172px; height: 25px; border: 1px solid rgba(38, 224, 239, .35); outline: 0; background: rgba(1, 13, 28, .76); color: #e2fbff; padding: 0 9px; font-size: 11px; letter-spacing: .25px; transition: border-color .18s ease, box-shadow .18s ease, background .18s ease; }
      .heat-treatment-search input::placeholder { color: #55788d; }
      .heat-treatment-search input:focus { border-color: #ffbd4d; background: rgba(17, 22, 25, .86); box-shadow: 0 0 10px rgba(255, 189, 77, .28), inset 0 0 9px rgba(22, 232, 245, .08); }
      .heat-treatment-scroller { display: flex; min-width: 0; min-height: 0; flex: 1 1 auto; flex-direction: column; padding-top: 4px; }
      .heat-treatment-row { display: grid; min-width: 0; grid-template-columns: minmax(58px, .95fr) minmax(48px, .72fr) minmax(72px, 1fr) repeat(4, minmax(50px, .92fr)); align-items: center; column-gap: 7px; min-height: 32px; border-bottom: 1px solid rgba(117, 184, 208, .1); color: #cfeaf5; font-size: 10px; }
      .heat-treatment-row:nth-child(even) { background: rgba(18, 76, 111, .075); }
      .heat-treatment-row > span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .heat-treatment-row.is-header { min-height: 33px; padding: 0 3px; border-bottom-color: rgba(47, 170, 205, .31); background: rgba(7, 30, 52, .9); color: #78b6c8; font-size: 10px; font-weight: 600; letter-spacing: .35px; }
      .heat-treatment-row.is-pending { border-left: 2px solid #ff6574; background: linear-gradient(90deg, rgba(255, 57, 84, .22), rgba(124, 42, 19, .1) 65%, transparent); box-shadow: inset 8px 0 14px rgba(255, 57, 84, .06); }
      .heat-treatment-row.is-complete { border-left: 2px solid rgba(43, 238, 193, .58); }
      .heat-treatment-pipeline, .heat-treatment-joint { color: #e2faff; font-family: 'DIN Alternate', monospace; font-size: 10px; font-weight: 700; letter-spacing: .32px; }
      .heat-treatment-joint { color: #bce8f2; font-weight: 600; }
      .heat-treatment-date { color: #a9dce9; font-family: 'DIN Alternate', monospace; font-size: 9px; }
      .heat-treatment-extra { overflow: hidden; color: #9ecbd8; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
      .heat-treatment-pending-card .heat-treatment-row:not(.is-header) > span { color: #ffd2d7; font-weight: 600; text-shadow: 0 0 7px rgba(255, 91, 105, .18); }
      .heat-treatment-pending-card .heat-treatment-row:not(.is-header) .heat-treatment-date { color: #ffb7c0; }
      .heat-treatment-viewport { position: relative; min-height: 0; flex: 1 1 auto; overflow: hidden; }
      .heat-treatment-track { will-change: transform; }
      .heat-treatment-list-card.is-heat-treatment-scrolling .heat-treatment-track { animation: none !important; }
      .heat-treatment-empty { display: flex; align-items: center; justify-content: center; min-height: 96px; flex: 1 1 auto; color: #6e9ab0; font-size: 12px; }
      .quality-empty, .quality-loading { display: flex; align-items: center; justify-content: center; min-height: 96px; color: #6e9ab0; font-size: 13px; }
      .quality-loading { flex: 1 1 auto; border: 1px dashed rgba(0, 242, 254, .25); background: rgba(0, 92, 151, .05); }
      @keyframes quality-live { 50% { opacity: .25; text-shadow: 0 0 8px #29f7cb; } }
      @media (max-width: 1180px) {
        .quality-layout-welder { grid-template-rows: minmax(220px, .8fr) minmax(250px, 1.2fr); }
        .quality-scan-list { grid-template-columns: 1fr; }
        .quality-scan-row { grid-template-columns: minmax(56px, .8fr) minmax(60px, 1fr) 48px; gap: 6px; }
      }
    `
    document.head.appendChild(style)
  }

  function start() {
    addStyles()
    scheduleRefresh()
    // React updates the auto-scroll offset by changing an inline `style`
    // attribute.  Watching only inserted rows lets that later write resume the
    // animation after a search; observe style changes too and immediately
    // restore the paused state while a query is active.
    new MutationObserver((mutations) => {
      // Restore the stop synchronously.  The dashboard writes its offset from
      // a timer, so waiting for the next animation frame leaves a visible
      // opportunity for the list to move.
      if (state.query && mutations.some((mutation) => {
        const element = mutation.target.nodeType === 1 ? mutation.target : mutation.target.parentElement
        return mutation.type === 'attributes'
          && mutation.attributeName === 'style'
          && !element?.closest('[data-continuous-scroller]')
      })) {
        const ngPanel = findPanel('探伤不合格异常清单')
        if (ngPanel) applySearch(ngPanel)
      }
      // The source dashboard updates its clock every second.  Those mutations
      // are limited to the header and do not change dashboard data; scheduling
      // the full enhancement pass for them causes needless visual redraws.
      const hasContentMutation = mutations.some((mutation) => {
        const target = mutation.target
        const element = target.nodeType === 1 ? target : target.parentElement
        return !element?.closest('.screen-header') && !element?.closest('[data-continuous-scroller]')
      })
      if (hasContentMutation) scheduleRefresh()
    }).observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['style'],
    })
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true })
  else start()
})()
