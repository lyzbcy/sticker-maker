import { onMounted, onBeforeUnmount } from 'vue'
import { createLibraryState } from './state'
import { createLibraryGateway } from './gateway'
import { createLibraryProgress } from './progress'
import { createLibraryActions } from './actions'
import * as presenters from './presenters'

// One controller per panel; views share refs, never create extra pollers or IPC.
export function useResourceLibrary() {
 const state = createLibraryState()
 const gateway = createLibraryGateway()
 const progress = createLibraryProgress(state)
 let pollTimer = null
 let unsubscribe = null
 const delayedRefreshes = new Set()
 const actions = createLibraryActions(state, gateway, delay => {
  if (!state.mounted.value) return
  const timer = setTimeout(() => {
   delayedRefreshes.delete(timer)
   if (state.mounted.value) actions.refreshStatus({ quiet: true })
  }, delay)
  delayedRefreshes.add(timer)
 })
 onMounted(async () => {
  state.mounted.value = true
  if (gateway.api()?.onProgress) unsubscribe = gateway.api().onProgress(progress.acceptProgress)
  await actions.refreshStatus()
  if (!state.mounted.value) return
  pollTimer = setInterval(() => {
   if (state.mounted.value && !state.transferBusy.value) actions.refreshStatus({ quiet: true })
  }, 30000)
 })
 onBeforeUnmount(() => {
  state.mounted.value = false
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = null
  if (typeof unsubscribe === 'function') unsubscribe()
  unsubscribe = null
  for (const timer of delayedRefreshes) clearTimeout(timer)
  delayedRefreshes.clear()
  progress.stop()
 })
 return { ...state, ...actions, ...presenters, progressPercent: progress.progressPercent, progressText: progress.progressText }
}
