import assert from 'node:assert/strict';
import {hoursCycle} from '../web/src/hours-cycle.js';
for (const [today,offset,start,end] of [
  ['2026-09-24',0,'2026-08-25','2026-09-24'],
  ['2026-09-25',0,'2026-08-25','2026-09-24'],
  ['2026-09-29',-1,'2026-07-25','2026-08-24'],
  ['2026-12-25',0,'2026-11-25','2026-12-24'],
  ['2027-01-01',-1,'2026-11-25','2026-12-24'],
  ['2028-02-29',0,'2028-01-25','2028-02-24'],
]) {
  const result=hoursCycle(today,offset);
  assert.equal(result.start,start);assert.equal(result.end,end);
}
console.log('Hours cycle boundaries, year rollover and leap day passed');
