import { describe, it, expect, vi } from 'vitest'
import { sendFeedback } from '../src/main/feedback'
describe('feedback backend (no actual messages)', () => {
 it('preserves an explicit unconfigured-service error without contacting a bot', async () => {
  const fetchFn=vi.fn();const result=await sendFeedback({message:'fixture'}, {endpoint:'',fetchFn});
  expect(result.ok).toBe(false);expect(result.error).toContain('尚未配置');expect(fetchFn).not.toHaveBeenCalled()
 })
 it('reports upstream HTTP and service failure without consuming cooldown', async () => {
  expect((await sendFeedback({message:'fixture'}, {version:'0.5.1',endpoint:'https://feedback.test/intake',fetchFn:vi.fn().mockResolvedValue({ok:false,status:503})})).ok).toBe(false)
  expect((await sendFeedback({message:'fixture'}, {version:'0.5.1',endpoint:'https://feedback.test/intake',fetchFn:vi.fn().mockResolvedValue({ok:true,json:async()=>({errcode:1})})})).ok).toBe(false)
 })
 it('validates empty input before network', async () => {
  const fetchFn=vi.fn();expect((await sendFeedback({message:' '},{fetchFn})).ok).toBe(false);expect(fetchFn).not.toHaveBeenCalled()
 })
 it('redacts body, confirms errcode=0, and blocks immediate resend', async () => {
  const fetchFn=vi.fn().mockResolvedValue({ok:true,json:async()=>({errcode:0})})
  expect((await sendFeedback({message:'fixture password=sample-password',logs:'token=sample-token user@sample.com'}, {version:'0.5.1',endpoint:'https://feedback.test/intake',fetchFn})).ok).toBe(true)
  const body=fetchFn.mock.calls[0][1].body;expect(body).not.toContain('sample-password');expect(body).not.toContain('sample-token');expect(body).toContain('0.5.1')
  expect((await sendFeedback({message:'again'},{version:'0.5.1',endpoint:'https://feedback.test/intake',fetchFn})).ok).toBe(false);expect(fetchFn).toHaveBeenCalledTimes(1)
 })
})
