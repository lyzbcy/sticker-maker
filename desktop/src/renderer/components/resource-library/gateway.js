export function createLibraryGateway(bridge = () => typeof window !== 'undefined' ? window.api : null) {
function api() { return bridge() }
function responseError(res, fallback = '操作失败') {
  return res?.errors?.[0]?.message || res?.raw?.errors?.[0]?.message || res?.error || res?.message || fallback
}
function exceptionError(err, fallback = '操作失败') {
  return err?.errors?.[0]?.message || err?.data?.errors?.[0]?.message || err?.message || fallback
}
async function send(cmd, args = {}) {
  if (!api()?.send) throw new Error('桌面引擎尚未连接')
  return api().send(cmd, JSON.parse(JSON.stringify(args)))
}

return { api, send, responseError, exceptionError }
}
