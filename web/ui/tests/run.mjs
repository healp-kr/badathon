/* 골든 검증 — TypeScript 엔진이 파이썬 엔진을 그대로 재현하는가.
 *
 *     node tests/run.mjs            (web/ui 에서)
 *
 * 정답지는 `tools/make_golden.py` 가 만든다. 파라미터나 규칙을 고쳤으면 그것부터
 * 다시 돌려야 한다 — 정답지를 손으로 고치면 검증이 의미를 잃는다.
 *
 * Node 24 가 .ts 를 그대로 실행하므로 빌드 단계가 없다. 대신 엔진 코드는
 * 지울 수 있는 문법(erasable syntax)만 써야 한다 — enum·namespace 는 못 쓴다.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (name) => JSON.parse(readFileSync(join(HERE, 'golden', name), 'utf8'));

/** 예외 메시지의 첫 줄만. 스택이 붙어 오면 읽기 어렵다. */
const firstLine = (text) => String(text).split(String.fromCharCode(10))[0];

let failed = 0;
const results = [];

function section(name, fn) {
  const before = failed;
  const started = Date.now();
  fn();
  results.push({
    name,
    ok: failed === before,
    bad: failed - before,
    ms: Date.now() - started,
  });
}

function fail(where, want, got) {
  failed++;
  if (failed <= 12) {
    console.log(`  ✗ ${where}`);
    console.log(`      기대 ${JSON.stringify(want)}`);
    console.log(`      실제 ${JSON.stringify(got)}`);
  } else if (failed === 13) {
    console.log('  … (이하 생략)');
  }
}

/** 깊은 비교. 어디가 다른지 경로로 알려준다. */
function diff(want, got, path = '') {
  if (Object.is(want, got)) return null;
  if (want === null || got === null || typeof want !== typeof got) return path || '(root)';
  if (typeof want !== 'object') return path || '(root)';
  if (Array.isArray(want) !== Array.isArray(got)) return path || '(root)';

  if (Array.isArray(want)) {
    if (want.length !== got.length) return `${path}.length`;
    for (let i = 0; i < want.length; i++) {
      const d = diff(want[i], got[i], `${path}[${i}]`);
      if (d) return d;
    }
    return null;
  }

  const keys = new Set([...Object.keys(want), ...Object.keys(got)]);
  for (const key of keys) {
    const d = diff(want[key], got[key], `${path}.${key}`);
    if (d) return d;
  }
  return null;
}

function at(obj, path) {
  // "부분.경로[3].키" 를 따라간다. 실패하면 undefined
  try {
    return path
      .replace(/\[(\d+)\]/g, '.$1')
      .split('.')
      .filter(Boolean)
      .reduce((acc, key) => (acc === undefined || acc === null ? acc : acc[key]), obj);
  } catch {
    return undefined;
  }
}

// ── 1. 반올림 ────────────────────────────────────────────────────────
const { pyRound } = await import('../src/engine/pyround.ts');

section('반올림 (은행가 반올림)', () => {
  for (const c of read('round.json')) {
    const got = pyRound(c.x, c.n);
    if (!Object.is(got, c.want)) fail(`round(${c.x}, ${c.n})`, c.want, got);
  }
});

// ── 2. serve() 전체 ──────────────────────────────────────────────────
let serveModule = null;
try {
  serveModule = await import('../src/engine/serve.ts');
} catch (error) {
  console.log(`[건너뜀] engine/serve.ts 아직 없음 — ${firstLine(error.message)}`);
}

if (serveModule) {
  const golden = read('serve.json');
  section(`serve() 전체 (${golden.케이스수}건)`, () => {
    for (const c of golden.cases) {
      let got;
      try {
        got = serveModule.serve(c.payload, { topN: c.top_n ?? null });
      } catch (error) {
        if (c.거절 !== undefined) {
          if (error.message !== c.거절) fail(`거절 «${c.이름}»`, c.거절, error.message);
          continue;
        }
        fail(`«${c.이름}» 예외`, '정상 응답', `${error.message}`);
        continue;
      }
      if (c.거절 !== undefined) {
        fail(`«${c.이름}»`, `거절: ${c.거절}`, '통과해 버림');
        continue;
      }
      for (const key of golden.제외필드) delete got[key];
      const where = diff(c.결과, got);
      if (where) fail(`«${c.이름}» ${where}`, at(c.결과, where), at(got, where));
    }
  });
}

// ── 3. 지도·시설·혼잡도 ──────────────────────────────────────────────
let geoModules = null;
try {
  geoModules = {
    locate: await import('../src/engine/locate.ts'),
    crowding: await import('../src/engine/crowding.ts'),
    facility: await import('../src/engine/facility.ts'),
    mapdata: await import('../src/engine/mapdata.ts'),
  };
} catch (error) {
  console.log(`[건너뜀] geo 엔진 아직 없음 — ${firstLine(error.message)}`);
}

if (geoModules) {
  const g = read('geo.json');
  const { locate, crowding, facility, mapdata } = geoModules;

  section(`좌표 판정 (${g.locate.length}건)`, () => {
    for (const c of g.locate) {
      const got = locate.resolveDistrict(c.lat, c.lon);
      const where = diff(c.결과, got);
      if (where) fail(`«${c.이름}» ${where}`, at(c.결과, where), at(got, where));
    }
    const dw = diff(g.districts, locate.listDistricts());
    if (dw) fail(`listDistricts ${dw}`, at(g.districts, dw), at(locate.listDistricts(), dw));

    const bAll = locate.boundaryFeatures();
    const bw = diff(g['boundary_전체'], bAll);
    if (bw) fail(`boundaryFeatures() ${bw}`, '(생략)', '(생략)');
    const bOne = locate.boundaryFeatures('중구');
    const bw2 = diff(g['boundary_중구'], bOne);
    if (bw2) fail(`boundaryFeatures('중구') ${bw2}`, '(생략)', '(생략)');

    for (const [name, want] of Object.entries(g.center)) {
      const got = locate.districtCenter(name);
      if (diff(want, got)) fail(`districtCenter(${name})`, want, got);
    }
    for (const [name, want] of Object.entries(g.supported)) {
      const got = locate.isSupported(name);
      if (want !== got) fail(`isSupported(${name})`, want, got);
    }
  });

  section(`혼잡도 (${g.crowding.length}건)`, () => {
    for (const c of g.crowding) {
      const got = crowding.getCrowding(c.district, c.daytype, c.hour) ?? null;
      const where = diff(c.결과, got);
      if (where) fail(`«${c.이름}» ${where}`, at(c.결과, where), at(got, where));
    }
    for (const c of g.slot) {
      const got = crowding.slotToHour(c.slot) ?? null;
      if (!Object.is(c.결과, got)) fail(`slotToHour(${c.slot})`, c.결과, got);
    }
  });

  section(`시설 검색 (${g.facilities.length}건)`, () => {
    for (const c of g.facilities) {
      const got = facility.findFacilities(c.sport, {
        lat: c.lat, lon: c.lon, district: c.district,
      });
      const where = diff(c.결과, got);
      if (where) fail(`«${c.이름}» ${where}`, at(c.결과, where), at(got, where));
    }
    for (const c of g.access) {
      const got = facility.access(c.lat, c.lon);
      const where = diff(c.결과, got);
      if (where) fail(`access «${c.이름}» ${where}`, at(c.결과, where), at(got, where));
    }
  });

  section(`지도 핀 (${g.pins.length}건)`, () => {
    for (const c of g.pins) {
      const got = mapdata.pins(c.sport, {
        district: c.district, lat: c.lat, lon: c.lon,
        limit: c.limit, reservableOnly: c.reservable_only,
      });
      const where = diff(c.결과, got);
      if (where) fail(`«${c.이름}» ${where}`, at(c.결과, where), at(got, where));
    }
  });
}

// ── 결과 ─────────────────────────────────────────────────────────────
console.log('');
for (const r of results) {
  const mark = r.ok ? '통과' : `실패 ${r.bad}건`;
  console.log(`  ${r.ok ? '✓' : '✗'} ${r.name.padEnd(28)} ${mark}  (${r.ms}ms)`);
}
console.log('');
console.log(failed === 0 ? '전부 통과' : `실패 ${failed}건`);
process.exit(failed === 0 ? 0 : 1);
