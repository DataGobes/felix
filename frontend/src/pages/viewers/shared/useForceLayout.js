import { useRef, useEffect, useCallback, useState } from 'react'

const IDEAL_LENGTHS = [220, 170, 130, 100, 80]
const CENTER_STRENGTH = 0.03
const REPULSION = 600
const SPRING_STRENGTH = 0.1
const DAMPING = 0.82
const ALPHA_DECAY = 0.002
const ALPHA_MIN = 0.003
const GRID_SIZE = 250
const MAX_REPULSION_FORCE = 10
const MIN_SEPARATION = 60

function idealLength(depth) {
  return IDEAL_LENGTHS[Math.min(depth, IDEAL_LENGTHS.length - 1)]
}

function buildSpatialHash(positions, gridSize) {
  const grid = {}
  positions.forEach((pos, id) => {
    const cx = Math.floor(pos.x / gridSize)
    const cy = Math.floor(pos.y / gridSize)
    const key = `${cx},${cy}`
    if (!grid[key]) grid[key] = []
    grid[key].push({ id, ...pos })
  })
  return grid
}

function getNeighborCells(cx, cy) {
  const cells = []
  for (let dx = -1; dx <= 1; dx++) {
    for (let dy = -1; dy <= 1; dy++) {
      cells.push(`${cx + dx},${cy + dy}`)
    }
  }
  return cells
}

export default function useForceLayout({ nodes, links, width, height, enabled }) {
  const posRef = useRef(new Map())
  const velRef = useRef(new Map())
  const pinnedRef = useRef(new Set())
  const alphaRef = useRef(1.0)
  const rafRef = useRef(null)
  const lastRenderRef = useRef(0)
  const [positions, setPositions] = useState(new Map())

  // Initialize positions for new nodes, remove old ones
  useEffect(() => {
    if (!enabled) return
    const pos = posRef.current
    const vel = velRef.current
    const existing = new Set(nodes.map(n => n.id))

    for (const id of pos.keys()) {
      if (!existing.has(id)) {
        pos.delete(id)
        vel.delete(id)
        pinnedRef.current.delete(id)
      }
    }

    // Group new nodes by parent for even angular distribution
    const newByParent = new Map()
    for (const node of nodes) {
      if (!pos.has(node.id)) {
        const pid = node.parentId || '__root__'
        if (!newByParent.has(pid)) newByParent.set(pid, [])
        newByParent.get(pid).push(node)
      }
    }

    const cx = width / 2
    const cy = height / 2

    for (const [pid, children] of newByParent) {
      const parentPos = pid !== '__root__' ? pos.get(pid) : null
      const base = parentPos || { x: cx, y: cy }
      const count = children.length
      const radius = Math.max(120, count * 25)
      const angleOffset = Math.random() * Math.PI * 2

      children.forEach((node, i) => {
        const angle = angleOffset + (2 * Math.PI * i) / count
        pos.set(node.id, {
          x: base.x + Math.cos(angle) * radius,
          y: base.y + Math.sin(angle) * radius,
        })
        vel.set(node.id, { vx: 0, vy: 0 })
      })
    }

    alphaRef.current = 1.0
  }, [nodes, links, width, height, enabled])

  // Main simulation loop
  useEffect(() => {
    if (!enabled || nodes.length === 0) {
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
      return
    }

    const nodeDepthMap = new Map()
    for (const n of nodes) nodeDepthMap.set(n.id, n.depth ?? 0)

    const tick = (now) => {
      rafRef.current = requestAnimationFrame(tick)
      if (alphaRef.current < ALPHA_MIN) return

      const pos = posRef.current
      const vel = velRef.current
      const cx = width / 2
      const cy = height / 2
      const alpha = alphaRef.current

      // 1) Center gravity
      pos.forEach((p, id) => {
        if (pinnedRef.current.has(id)) return
        const v = vel.get(id)
        v.vx += (cx - p.x) * CENTER_STRENGTH * alpha
        v.vy += (cy - p.y) * CENTER_STRENGTH * alpha
      })

      // 2) Repulsion — with force cap and minimum separation
      const grid = buildSpatialHash(pos, GRID_SIZE)
      pos.forEach((p, id) => {
        if (pinnedRef.current.has(id)) return
        const v = vel.get(id)
        const cellX = Math.floor(p.x / GRID_SIZE)
        const cellY = Math.floor(p.y / GRID_SIZE)
        const cells = getNeighborCells(cellX, cellY)

        for (const key of cells) {
          const bucket = grid[key]
          if (!bucket) continue
          for (const other of bucket) {
            if (other.id === id) continue
            let dx = p.x - other.x
            let dy = p.y - other.y
            let dist = Math.sqrt(dx * dx + dy * dy)
            if (dist < 1) { dx = Math.random() - 0.5; dy = Math.random() - 0.5; dist = 1 }

            // Stronger repulsion at close range to enforce minimum separation
            const effectiveDist = Math.max(dist, 1)
            let force = (REPULSION * alpha) / (effectiveDist * effectiveDist)
            if (dist < MIN_SEPARATION) {
              force += (MIN_SEPARATION - dist) * 0.5 * alpha
            }
            force = Math.min(force, MAX_REPULSION_FORCE * alpha)
            v.vx += (dx / dist) * force
            v.vy += (dy / dist) * force
          }
        }
      })

      // 3) Spring links
      for (const link of links) {
        const sp = pos.get(link.source)
        const tp = pos.get(link.target)
        if (!sp || !tp) continue

        const depth = Math.max(nodeDepthMap.get(link.source) ?? 0, nodeDepthMap.get(link.target) ?? 0)
        const ideal = idealLength(depth)
        let dx = tp.x - sp.x
        let dy = tp.y - sp.y
        let dist = Math.sqrt(dx * dx + dy * dy)
        if (dist < 1) dist = 1
        const displacement = dist - ideal
        const force = displacement * SPRING_STRENGTH * alpha
        const fx = (dx / dist) * force
        const fy = (dy / dist) * force

        if (!pinnedRef.current.has(link.source)) {
          vel.get(link.source).vx += fx
          vel.get(link.source).vy += fy
        }
        if (!pinnedRef.current.has(link.target)) {
          vel.get(link.target).vx -= fx
          vel.get(link.target).vy -= fy
        }
      }

      // Apply velocities
      pos.forEach((p, id) => {
        if (pinnedRef.current.has(id)) return
        const v = vel.get(id)
        v.vx *= DAMPING
        v.vy *= DAMPING
        p.x += v.vx
        p.y += v.vy
      })

      alphaRef.current = Math.max(alphaRef.current - ALPHA_DECAY, 0)

      if (now - lastRenderRef.current > 33) {
        lastRenderRef.current = now
        setPositions(new Map(pos))
      }
    }

    rafRef.current = requestAnimationFrame(tick)
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current) }
  }, [nodes, links, width, height, enabled])

  const reheat = useCallback(() => { alphaRef.current = 1.0 }, [])

  const dragStart = useCallback((id) => { pinnedRef.current.add(id) }, [])

  const dragMove = useCallback((id, x, y) => {
    const p = posRef.current.get(id)
    if (p) { p.x = x; p.y = y; alphaRef.current = Math.max(alphaRef.current, 0.3) }
  }, [])

  const dragEnd = useCallback((id) => {
    pinnedRef.current.delete(id)
    const v = velRef.current.get(id)
    if (v) { v.vx = 0; v.vy = 0 }
  }, [])

  return { positions, reheat, dragStart, dragMove, dragEnd }
}
