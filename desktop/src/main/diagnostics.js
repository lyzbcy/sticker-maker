function scrubText(value) {
  return String(value || '').replace(/(?:https?:\/\/)\S+\?(?:\S+)/gi, '[链接参数已移除]')
    .replace(/\b(Bearer)\s+[^\s"',;]+/gi, '[凭据已移除]')
    .replace(/"(?:password|token|authorization|secret|api[_-]?key|cookie|storage_state)"\s*:\s*"(?:\\.|[^"\\])*"/gi, '"凭据":"已移除"')
    .replace(/\b(?:token|password|authorization|secret|api[_-]?key)\s*[=:]\s*[^\s,;]+/gi, '[凭据已移除]')
    .replace(/\bsk-[A-Za-z0-9_-]+/g, '[密钥已移除]')
    .replace(/[A-Za-z]:[\\/][^\n,;]+/g, '[本机路径已移除]')
    .replace(/\/(?:Users|home)\/[^\s]+/g, '[本机路径已移除]')
    .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, '[邮箱已移除]')
}
module.exports = { scrubText }
