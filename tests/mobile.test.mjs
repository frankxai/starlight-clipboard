import test from "node:test";
import assert from "node:assert/strict";
import {emptyPacket,makeCapture,merge,validate,exportSelection,matching} from "../mobile/store.js";

test("capture retains exact text, chosen category and user labels",()=>{
  const body="  Cinematic piano, 84 BPM\nKeep the trailing space.  ";
  const packet=makeCapture(body,"suno","Piano, quiet, piano");
  assert.equal(packet.records[0].body,body);
  assert.equal(packet.records[0].use_case,"suno");
  assert.equal(packet.records[0].kind,"prompt");
  assert.deepEqual(packet.tags.map(row=>row.label),["piano","quiet"]);
  assert.equal(packet.tags[0].source,"user");
});
test("repeating a handoff preserves source identities and dates",()=>{
  const packet=makeCapture("An idea I want to keep");
  const once=merge(emptyPacket(),packet),twice=merge(once,packet);
  assert.equal(twice.records.length,1);
  assert.deepEqual(twice.records,packet.records);
});
test("a conflicting original refuses the complete import without mutation",()=>{
  const existing=makeCapture("First original"),before=JSON.stringify(existing);
  const incoming=makeCapture("Second original");
  incoming.records.push({...existing.records[0],body:"Changed source"});
  assert.throws(()=>merge(existing,incoming),/differs/);
  assert.equal(JSON.stringify(existing),before);
});
test("user labels take precedence over agent labels",()=>{
  const existing=makeCapture("Piano direction","suno","quiet");
  const agent=structuredClone(existing);agent.tags[0].source="agent";
  const result=merge(existing,agent);
  assert.equal(result.tags[0].source,"user");
  assert.equal(merge(agent,existing).tags[0].source,"user");
});
test("export filters originals, memberships and labels without changing the archive",()=>{
  const one=makeCapture("Piano direction","suno","piano"),two=makeCapture("A separate idea");
  const book=merge(one,two);
  book.collections=[{id:"my-vibe",name:"My vibe",description:"",mode:"manual",query:""}];
  book.members=book.records.map(row=>({collection:"my-vibe",uid:row.uid}));
  const packet=exportSelection(book,[one.records[0].uid]);
  assert.equal(packet.records.length,1);assert.equal(packet.members.length,1);assert.equal(packet.tags.length,1);
  assert.equal(book.records.length,2);
});
test("search and type views match actual retained originals",()=>{
  const book=merge(makeCapture("Piano and silver strings","suno","quiet"),makeCapture("A thought about tomorrow"));
  assert.equal(matching(book,{kind:"suno"}).length,1);
  assert.equal(matching(book,{query:"quiet"}).length,1);
  assert.equal(matching(book,{query:"missing"}).length,0);
  assert.equal(matching(book,{kind:"ideas"}).length,1);
});
test("source dates need a timezone and unexpected fields are rejected",()=>{
  const packet=makeCapture("A retained idea");
  packet.records[0].captured_at="2026-11-01T10:00:00";
  assert.throws(()=>validate(packet),/date/);
  packet.records[0].captured_at="2026-11-01T10:00:00Z";
  packet.records[0].execute="command";
  assert.throws(()=>validate(packet),/fields/);
});
test("protected record types cannot enter portable files",()=>{
  const packet=makeCapture("A retained idea");packet.records[0].kind="secret";
  assert.throws(()=>validate(packet),/protected/);
});
test("impossible calendar dates cannot shift into another month",()=>{
  const packet=makeCapture("A retained idea");packet.records[0].captured_at="2026-02-30T10:00:00Z";
  assert.throws(()=>validate(packet),/invalid source date/);
});
test("handoff limits measure UTF-8 bytes and never truncate originals",()=>{
  const book=emptyPacket();
  for(let i=0;i<4;i++) book.records.push(makeCapture("琴".repeat(40000)).records[0]);
  assert.equal(validate(book,false),book);
  assert.throws(()=>exportSelection(book,book.records.map(row=>row.uid)),/450 KB/);
  assert.equal(book.records[0].body.length,40000);
});
test("a changed vibe refuses import rather than overwriting its definition",()=>{
  const existing=makeCapture("A retained original");
  existing.collections=[{id:"vibe",name:"Piano",description:"",mode:"manual",query:""}];
  const incoming=structuredClone(existing);incoming.collections[0].name="Changed";
  assert.throws(()=>merge(existing,incoming),/vibe differs/);
  assert.equal(existing.collections[0].name,"Piano");
});
