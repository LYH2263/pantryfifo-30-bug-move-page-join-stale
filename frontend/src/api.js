// 所有会改变库存/层位的写操作（入库、扣减、转层、过期收走）成功后广播
// pantry:changed：紧急条与各分层视图据此重取，保证看到的是同一提交后的状态。
const MUTATING = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

export async function api(path, opts = {}) {
  const method = (opts.method || 'GET').toUpperCase()
  const r = await fetch('/api' + path, {
    headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
    ...opts,
  })
  if (!r.ok) {
    let detail = r.statusText
    try { const j = await r.json(); detail = j.detail || JSON.stringify(j) } catch {}
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  if (MUTATING.has(method)) {
    window.dispatchEvent(new CustomEvent('pantry:changed'))
  }
  if (r.status === 204) return null
  return r.json()
}
