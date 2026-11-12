'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
require('../dashboard/tax-breakdown.js');
const summarize=globalThis.TaxBreakdown.summarize;
const year={year:2026,remaining:60,federal:20,payroll:5,state:10,local:5};
test('segments reconcile and percentages use modeled income, not headline',()=>{
 const data=summarize({salary:100,headline_value:500,complete:false,annual:[year]},'salary');
 assert.equal(data.available,true);assert.equal(data.complete,false);
 assert.deepEqual(data.percentages,{remaining:60,federal:20,payroll:5,state:10,local:5});
});
test('NFL uses stricter coverage status while preserving figures',()=>{
 const data=summarize({gross:100,complete:true,coverage_complete:false,annual:[year]},'gross');
 assert.equal(data.complete,false);assert.equal(data.amounts.remaining,60);
});
test('annual aggregation excludes unavailable years',()=>{
 const data=summarize({gross:200,complete:false,annual:[year,{...year,year:2027},{year:2028,remaining:null,cash:null}]},'gross');
 assert.equal(data.available,true);assert.equal(data.income,200);
 assert.equal(data.amounts.federal,40);assert.deepEqual(data.years,[2026,2027]);
});
test('missing components are never silently represented as zero',()=>{
 assert.equal(summarize(null,'gross').available,false);
 assert.equal(summarize({gross:null,annual:[]},'gross').available,false);
 assert.equal(summarize({gross:100,annual:[{...year,local:null}]},'gross').available,false);
 assert.equal(summarize({gross:100,annual:[{...year,payroll:null}]},'gross').available,false);
});
test('unsupported historical local taxes remain explicitly omitted',()=>{
 const data=summarize({salary:95,annual:[{...year,year:2023,local:null,local_supported:false}]},'salary');
 assert.equal(data.available,true);assert.equal(data.localOmitted,true);assert.equal(data.amounts.local,0);
 assert.ok(Math.abs(Object.values(data.percentages).reduce((a,b)=>a+b,0)-100)<1e-9);
});
test('unreconciled or negative components do not draw misleading bars',()=>{
 assert.equal(summarize({gross:300,annual:[year]},'gross').available,false);
 assert.equal(summarize({gross:100,annual:[{...year,remaining:-10}]},'gross').available,false);
 assert.equal(summarize({gross:0,annual:[year]},'gross').available,false);
});
