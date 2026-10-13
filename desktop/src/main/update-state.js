const fs = require('fs'), path = require('path')
function dayInShanghai(now = new Date()) {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year:'numeric', month:'2-digit', day:'2-digit' }).format(now)
}
function recordAttempt(userData, now = new Date()) {
  const file = path.join(userData, 'update-check.json'), day = dayInShanghai(now)
  let state = {}; try { state = JSON.parse(fs.readFileSync(file, 'utf8')) } catch {}
  if (state.attemptDay === day) return false
  fs.mkdirSync(userData, { recursive: true }); fs.writeFileSync(file, JSON.stringify({ ...state, attemptDay: day }))
  return true
}
function recordSuccess(userData, now = new Date()) {
  const file = path.join(userData, 'update-check.json')
  let state = {}; try { state = JSON.parse(fs.readFileSync(file, 'utf8')) } catch {}
  fs.mkdirSync(userData, {recursive:true}); fs.writeFileSync(file, JSON.stringify({...state, successDay: dayInShanghai(now)}))
}
module.exports = { dayInShanghai, recordAttempt, recordSuccess }
