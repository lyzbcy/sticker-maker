const {test}=require('node:test');
const assert=require('node:assert/strict');
const {batchCount,candidateMeanings}=require('./web_batch.cjs');
test('batch count follows supplied themes instead of silently stopping at two',()=>{
  assert.equal(batchCount({themes:Array(2).fill({})}),2);
  assert.equal(batchCount({count:10,themes:Array(10).fill({})}),10);
});
test('same-response meaning candidates require all sixteen distinct indexes',()=>{
  const rows=Array.from({length:16},(_,i)=>({index:i+1,text:'收到',meaning:'收到'}));
  assert.equal(candidateMeanings('image finished\n'+JSON.stringify(rows)).length,16);
  rows[15].index=1;assert.equal(candidateMeanings(JSON.stringify(rows)),null);
  assert.equal(candidateMeanings('not JSON'),null);
});
test('mismatched or excessive counts fail before creating albums or sending prompts',()=>{
  for(const n of [0,11,1.5])assert.throws(()=>batchCount({count:n,themes:Array(2).fill({})}));
  assert.throws(()=>batchCount({count:10,themes:Array(2).fill({})}));
});
