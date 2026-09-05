import { onMounted, onUnmounted, type Ref } from 'vue'

/**
 * 自定义表头列宽拖拽。
 *
 * 交互规则：
 * 拖动两列之间的分隔线时：
 *
 * 1. 左侧列增加多少，右侧列就减少多少。
 * 2. 只有相邻的左右两列宽度发生变化。
 * 3. 表格总宽度保持不变。
 * 4. 其他列的宽度和位置均保持不变。
 *
 * 例如：
 *
 * |---A---|---B---|---C---|---D---|
 *                 ↑ 拖动 B/C 分隔线
 *
 * |---A---|-----B-----|-C-|---D---|
 *
 * 仅 B、C 变化。
 */

function getEl(
  ref: HTMLElement | null | Record<string, unknown>,
): HTMLElement | null {
  if (!ref) return null
  if (ref instanceof HTMLElement) return ref

  return (
    ((ref as Record<string, unknown>).$el as HTMLElement | null) ?? null
  )
}

export function useRealtimeResize(
  tableRef: Ref<HTMLElement | null>,
  options: {
    minWidth?: number
  } = {},
) {
  const minWidth = options.minWidth ?? 30

  let leftColIdx = -1
  let rightColIdx = -1

  let startX = 0
  let leftStartWidth = 0
  let rightStartWidth = 0
  let adjacentTotalWidth = 0

  let resizing = false

  let headerCols: HTMLTableColElement[] = []
  let bodyCols: HTMLTableColElement[] = []

  /* ---------- helpers ---------- */

  function collectCols(wrapper: HTMLElement) {
    const headerTable = wrapper.querySelector(
      '.el-table__header-wrapper table',
    )

    const bodyTable = wrapper.querySelector(
      '.el-table__body-wrapper table',
    )

    const hCols = headerTable
      ? (Array.from(
          headerTable.querySelectorAll(':scope > colgroup > col'),
        ) as HTMLTableColElement[])
      : []

    const bCols = bodyTable
      ? (Array.from(
          bodyTable.querySelectorAll(':scope > colgroup > col'),
        ) as HTMLTableColElement[])
      : []

    return {
      hCols,
      bCols,
    }
  }

  /**
   * 同时修改 header 和 body 对应的 col。
   */
  function setColWidth(index: number, width: number) {
    const value = `${width}px`

    const headerCol = headerCols[index]
    const bodyCol = bodyCols[index]

    if (headerCol) {
      headerCol.style.width = value
    }

    if (bodyCol) {
      bodyCol.style.width = value
    }
  }

  /**
   * 获取某一列当前实际渲染宽度。
   */
  function getColWidth(index: number): number {
    const headerCol = headerCols[index]
    const bodyCol = bodyCols[index]

    const col = headerCol ?? bodyCol
    if (!col) return 0

    return col.getBoundingClientRect().width
  }

  /**
   * 把所有列锁定成当前的像素宽度。
   *
   * 这样拖动相邻两列时，浏览器不会重新按比例分配其他列。
   */
  function lockAllColumnWidths() {
    const count = Math.max(headerCols.length, bodyCols.length)

    for (let index = 0; index < count; index += 1) {
      const width = getColWidth(index)

      if (width > 0) {
        setColWidth(index, width)
      }
    }
  }

  /* ---------- handlers ---------- */

  const onMouseDown = (event: MouseEvent) => {
    if (resizing) return

    // Element Plus 在列边缘设置 col-resize。
    if (document.body.style.cursor !== 'col-resize') return

    const target = event.target as HTMLElement
    const th = target.closest(
      'th.el-table__cell',
    ) as HTMLTableCellElement | null

    const wrapper = getEl(tableRef.value)

    if (!th || !wrapper || !wrapper.contains(th)) return

    const row = th.parentElement
    if (!row) return

    const ths = Array.from(
      row.querySelectorAll<HTMLTableCellElement>(
        'th.el-table__cell',
      ),
    )

    const currentIndex = ths.indexOf(th)
    if (currentIndex < 0) return

    /**
     * Element Plus 的拖动区域位于当前 th 的右边缘。
     *
     * 因此：
     * currentIndex     是分隔线左侧列
     * currentIndex + 1 是分隔线右侧列
     */
    const nextIndex = currentIndex + 1

    // 最后一列右侧不存在相邻列，不能保持总宽度不变。
    if (nextIndex >= ths.length) return

    event.preventDefault()
    event.stopPropagation()
    event.stopImmediatePropagation()

    const { hCols, bCols } = collectCols(wrapper)

    headerCols = hCols
    bodyCols = bCols

    if (
      currentIndex >= Math.max(headerCols.length, bodyCols.length) ||
      nextIndex >= Math.max(headerCols.length, bodyCols.length)
    ) {
      headerCols = []
      bodyCols = []
      return
    }

    lockAllColumnWidths()

    leftColIdx = currentIndex
    rightColIdx = nextIndex

    leftStartWidth = getColWidth(leftColIdx)
    rightStartWidth = getColWidth(rightColIdx)

    if (leftStartWidth <= 0 || rightStartWidth <= 0) {
      leftColIdx = -1
      rightColIdx = -1
      headerCols = []
      bodyCols = []
      return
    }

    adjacentTotalWidth = leftStartWidth + rightStartWidth
    startX = event.clientX
    resizing = true

    document.body.classList.add('el-table-col-dragging')
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
  }

  const onMouseMove = (event: MouseEvent) => {
    if (
      !resizing ||
      leftColIdx < 0 ||
      rightColIdx < 0
    ) {
      return
    }

    event.preventDefault()

    const delta = event.clientX - startX

    /**
     * 左列宽度的合法范围：
     *
     * 左列不能小于 minWidth；
     * 同时必须给右列保留至少 minWidth。
     */
    const maxLeftWidth = adjacentTotalWidth - minWidth

    const newLeftWidth = Math.min(
      maxLeftWidth,
      Math.max(minWidth, leftStartWidth + delta),
    )

    const newRightWidth =
      adjacentTotalWidth - newLeftWidth

    setColWidth(leftColIdx, newLeftWidth)
    setColWidth(rightColIdx, newRightWidth)

    document.body.style.cursor = 'col-resize'
  }

  const onMouseUp = () => {
    if (!resizing) return

    resizing = false

    leftColIdx = -1
    rightColIdx = -1

    startX = 0
    leftStartWidth = 0
    rightStartWidth = 0
    adjacentTotalWidth = 0

    headerCols = []
    bodyCols = []

    document.body.classList.remove(
      'el-table-col-dragging',
    )

    document.body.style.userSelect = ''
    document.body.style.cursor = ''
  }

  /* ---------- lifecycle ---------- */

  onMounted(() => {
    const wrapper = getEl(tableRef.value)
    if (!wrapper) return

    wrapper.addEventListener(
      'mousedown',
      onMouseDown,
      {
        capture: true,
      },
    )

    document.addEventListener(
      'mousemove',
      onMouseMove,
      {
        capture: true,
      },
    )

    document.addEventListener(
      'mouseup',
      onMouseUp,
      {
        capture: true,
      },
    )
  })

  onUnmounted(() => {
    const wrapper = getEl(tableRef.value)

    if (wrapper) {
      wrapper.removeEventListener(
        'mousedown',
        onMouseDown,
        {
          capture: true,
        },
      )
    }

    document.removeEventListener(
      'mousemove',
      onMouseMove,
      {
        capture: true,
      },
    )

    document.removeEventListener(
      'mouseup',
      onMouseUp,
      {
        capture: true,
      },
    )

    document.body.classList.remove(
      'el-table-col-dragging',
    )

    document.body.style.cursor = ''
    document.body.style.userSelect = ''
  })
}