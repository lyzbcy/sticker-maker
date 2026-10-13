import { describe, it, expect, vi, beforeEach } from 'vitest'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { sendFeedback } from '../src/main/feedback'
let store, now=2000000
beforeEach(()=>{store=fs.mkdtempSync(path.join(os.tmpdir(),'sticker-feedback-fixture-'));now+=60000;vi.spyOn(Date,'now').mockReturnValue(now)})
describe('feedback backend (no actual messages)', () => {
 it('preserves an explicit unconfigured-service error without contacting a bot', async () => {
  const fetchFn=vi.fn();const result=await sendFeedback({message:'fixture'}, {endpoint:'',fetchFn});
  expect(result.ok).toBe(false);expect(result.error).toContain('尚未配置');expect(fetchFn).not.toHaveBeenCalled()
 })
 it('reports upstream HTTP and service failure without consuming cooldown', async () => {
  expect((await sendFeedback({message:'fixture'}, {storageDir:store,version:'0.5.1',endpoint:'https://feedback.test/intake',fetchFn:vi.fn().mockResolvedValue({ok:false,status:503})})).ok).toBe(false)
  expect((await sendFeedback({message:'fixture'}, {storageDir:store,version:'0.5.1',endpoint:'https://feedback.test/intake',fetchFn:vi.fn().mockResolvedValue({ok:true,json:async()=>({errcode:1,state:'failed'})})})).ok).toBe(false)
 })
 it('validates empty input before network', async () => {
  const fetchFn=vi.fn();expect((await sendFeedback({message:' '},{fetchFn})).ok).toBe(false);expect(fetchFn).not.toHaveBeenCalled()
 })
 it('redacts body, confirms errcode=0, and blocks immediate resend', async () => {
  const fetchFn=vi.fn().mockResolvedValue({ok:true,json:async()=>({errcode:0})})
  expect((await sendFeedback({message:'fixture password=sample-password',logs:'token=sample-token user@sample.com'}, {storageDir:store,version:'0.5.1',endpoint:'https://feedback.test/intake',fetchFn})).ok).toBe(true)
  const body=fetchFn.mock.calls[0][1].body;expect(body).not.toContain('sample-password');expect(body).not.toContain('sample-token');expect(body).toContain('0.5.1')
  expect((await sendFeedback({message:'again'},{version:'0.5.1',endpoint:'https://feedback.test/intake',fetchFn})).ok).toBe(false);expect(fetchFn).toHaveBeenCalledTimes(1)
 })
 it('persists one request identity and queries it again after a lost receipt', async()=>{
  const fetchFn=vi.fn().mockRejectedValueOnce(new Error('timeout')).mockResolvedValueOnce({ok:true,json:async()=>({errcode:0})})
  const options={storageDir:store,version:'0.5.1',endpoint:'https://feedback.test/intake',fetchFn}
  expect((await sendFeedback({message:'receipt fixture'},options)).ok).toBe(false)
  const pending=JSON.parse(fs.readFileSync(path.join(store,'feedback-pending.json'),'utf8'))
  expect((await sendFeedback({message:'receipt fixture'},options)).ok).toBe(true)
  const first=JSON.parse(fetchFn.mock.calls[0][1].body),second=JSON.parse(fetchFn.mock.calls[1][1].body)
  expect(first.request_id).toBe(second.request_id);expect(first.request_id).toBe(pending.id)
  expect(fs.existsSync(path.join(store,'feedback-pending.json'))).toBe(false)
 })
})
