// k6: нагрузка на GET /api/grid. Запуск:
//   k6 run -e BASE=http://localhost:3000 -e EMAIL=load@example.com -e PASSWORD=... -e TEAM_ID=... loadtest/grid.js
// Три прогона для слайда: GRID_CACHE_ENABLED=false (без кеша), true (кеш Redis), true + ETAG=1 (If-None-Match).
import http from "k6/http";
import { check } from "k6";

export const options = {
  scenarios: {
    peak: { executor: "constant-arrival-rate", rate: Number(__ENV.RPS || 50), timeUnit: "1s", duration: "60s", preAllocatedVUs: 50 },
  },
  thresholds: { http_req_duration: ["p(95)<100"] },
};

const BASE = __ENV.BASE || "http://localhost:3000";

export function setup() {
  const res = http.post(`${BASE}/api/auth/login`, JSON.stringify({ email: __ENV.EMAIL, password: __ENV.PASSWORD }), {
    headers: { "Content-Type": "application/json" },
  });
  check(res, { "login ok": (r) => r.status === 200 });
  return { cookie: res.cookies.session[0].value };
}

export default function (data) {
  const url = `${BASE}/api/grid?team_id=${__ENV.TEAM_ID}&step_minutes=30&slot_minutes=60`;
  const headers = { Cookie: `session=${data.cookie}` };
  const first = http.get(url, { headers });
  if (__ENV.ETAG) {
    const again = http.get(url, { headers: { ...headers, "If-None-Match": first.headers["Etag"] } });
    check(again, { "304": (r) => r.status === 304 });
    return;
  }
  check(first, { "200": (r) => r.status === 200 });
}
