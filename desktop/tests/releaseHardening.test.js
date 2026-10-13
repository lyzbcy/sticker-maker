import { describe, it, expect } from 'vitest'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import crypto from 'node:crypto'
import { isNewerVersion, verifyChecksum, validateReleaseAsset, pickUpdateAsset } from '../src/main/updater'
import { dayInShanghai, recordAttempt, recordSuccess } from '../src/main/update-state'
import { scrubText } from '../src/main/diagnostics'
describe('distribution hardening', () => {
 it('never upgrades to malformed/prerelease or downgraded versions', () => {
  for (const v of ['0.6.0-beta.1', '1.0', 'x.2.3', '0.05.1', '0.4.9']) expect(isNewerVersion(v,'0.5.0')).toBe(false)
  expect(isNewerVersion('0.10.0','0.9.9')).toBe(true)
 })
 it('requires a complete actual hash; mismatch is refused', async () => {
  const dir=await fs.mkdtemp(path.join(os.tmpdir(),'sticker-hash-test-')), file=path.join(dir,'test.bin')
  try { await fs.writeFile(file,'fixture'); expect(await verifyChecksum(file,'')).toBe(false)
   expect(await verifyChecksum(file,'0'.repeat(64))).toBe(false)
   expect(await verifyChecksum(file,crypto.createHash('sha256').update('fixture').digest('hex'))).toBe(true)
  } finally { await fs.unlink(file); await fs.rmdir(dir) }
 })
 it('uses release source and platform-specific package', () => {
  const asset={url:'https://github.com/lyzbcy/sticker-maker/releases/download/v0.5.1/sticker-maker-win-v0.5.1-setup.exe',sha256:'1'.repeat(64)}
  expect(validateReleaseAsset(asset,'win32')).toBe(true)
  expect(validateReleaseAsset({...asset,sha256:''},'win32')).toBe(false)
  expect(validateReleaseAsset({...asset,url:'https://example.com/a-setup.exe'},'win32')).toBe(false)
  expect(validateReleaseAsset(asset,'darwin')).toBe(false)
  expect(pickUpdateAsset({downloadUrl:'https://a.com/mac.zip'},'win32')).toBe(null)
  expect(pickUpdateAsset({downloadUrl:'https://a.com/mac.zip'},'linux')).toBe(null)
 })
 it('records failure as attempt only; manual success updates its own field', async () => {
  const dir=await fs.mkdtemp(path.join(os.tmpdir(),'sticker-day-test-')), now=new Date('2026-10-12T17:00:00Z')
  try {
   expect(dayInShanghai(now)).toBe('2026-10-13'); expect(recordAttempt(dir,now)).toBe(true)
   expect(recordAttempt(dir,now)).toBe(false)
   let state=JSON.parse(await fs.readFile(path.join(dir,'update-check.json'))); expect(state.successDay).toBeUndefined()
   recordSuccess(dir,now); state=JSON.parse(await fs.readFile(path.join(dir,'update-check.json')));expect(state.successDay).toBe('2026-10-13')
  } finally { await fs.unlink(path.join(dir,'update-check.json'));await fs.rmdir(dir) }
 })
 it('removes common secrets, mail and private paths', () => {
  const s=scrubText('token=abc password=pw user@example.com C:\\Users\\Person\\file sk-testing123')
  expect(s).not.toContain('abc');expect(s).not.toContain('pw');expect(s).not.toContain('example.com');expect(s).not.toContain('Person')
 })
})
