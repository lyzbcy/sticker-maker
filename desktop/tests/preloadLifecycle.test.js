import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import vm from 'node:vm'
import path from 'node:path'

describe('preload subscriptions release their own listeners', () => {
  for (const [method, channel] of Object.entries({ onProgress: 'python-progress', onExit: 'python-exit', onRestarting: 'python-restarting', onTask: 'task-status', onUpdateProgress: 'update-progress' })) {
    it(`${method} returns an idempotent unsubscriber`, () => {
      const listeners = new Set(), seen = []
      let api
      const ipcRenderer = {
        on(name, fn) { expect(name).toBe(channel); listeners.add(fn); return this },
        removeListener(name, fn) { expect(name).toBe(channel); listeners.delete(fn) },
      }
      const context = { require: () => ({ ipcRenderer, contextBridge: { exposeInMainWorld(_name, value) { api = value } } }), module: { exports: {} } }
      vm.runInNewContext(fs.readFileSync(path.resolve('src/preload/index.js'), 'utf8'), context)
      const off = api[method](value => seen.push(value))
      expect(typeof off).toBe('function')
      for (const fn of listeners) fn(null, { message: 'first' })
      expect(seen).toEqual([{ message: 'first' }])
      off(); off()
      expect(listeners.size).toBe(0)
    })
  }
})
