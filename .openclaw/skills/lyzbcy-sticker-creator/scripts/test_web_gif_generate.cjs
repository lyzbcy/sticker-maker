const {test}=require('node:test');
const assert=require('node:assert/strict');
const {validatePlan}=require('./web_gif_generate.cjs');
const valid=()=>({outputDir:'album',logDir:'logs',base:'base.png',guide:'guide.png',sheetPlans:Array.from({length:8},(_,i)=>({index:i,prompt:'原图/prompt-'+i+'.txt'})),sheets:[]});
test('accepts eight distinct 40-frame sheet plans for one album',()=>assert.doesNotThrow(()=>validatePlan(valid())));
test('unknown send outcome is never implicitly retried',()=>{
  const m=valid();m.sheets=[{index:0,sendIntentAt:1}];assert.throws(()=>validatePlan(m),/Unknown send outcome/);
});
test('duplicate plans and unrelated saved sheets are rejected',()=>{
  const m=valid();m.sheetPlans[7].index=0;assert.throws(()=>validatePlan(m));
  const n=valid();n.sheets=[{index:99}];assert.throws(()=>validatePlan(n),/original plan/);
});
