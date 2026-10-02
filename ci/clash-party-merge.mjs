// Execute the unmodified upstream TypeScript with Node's native type stripping.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { deepMerge } from '../.tools/clash-party-merge.mts'
const fixture = JSON.parse(readFileSync(0, 'utf8'))
let merged
for (const [canonical, legacy] of [[fixture.canonical, fixture.legacy], [fixture.arrayCanonical, fixture.arrayLegacy]]) {
  const actual = deepMerge(structuredClone(fixture.base), legacy, true)
  assert.deepEqual(actual.dns['fake-ip-filter'], [...fixture.base.dns['fake-ip-filter'], ...canonical.dns['fake-ip-filter']])
  assert.deepEqual(actual.dns['nameserver-policy'], {...fixture.base.dns['nameserver-policy'], ...canonical.dns['nameserver-policy']})
  assert.deepEqual(actual.rules.slice(0, canonical['+rules'].length), canonical['+rules'])
  assert.equal(actual.rules[0], 'IP-CIDR,100.64.0.0/10,DIRECT,no-resolve')
  assert.equal(actual.rules.at(-1), 'MATCH,漏网之鱼')
  assert.equal('fake-ip-filter+' in actual.dns, false)
  assert.equal('.git.yun' in actual.dns['nameserver-policy'], false)
  merged ??= actual
}
process.stdout.write(JSON.stringify(merged))
