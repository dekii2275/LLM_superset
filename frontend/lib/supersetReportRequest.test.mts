import assert from "node:assert/strict";
import { test } from "node:test";
import { createDashboardReportRequest, supersetErrorMessage } from "./supersetReportRequest.ts";

test("removes empty Superset tab entries while preserving the selected tab and filters", () => {
  const mask = { "NATIVE_FILTER-VENDOR": { filterState: { value: ["VeriFone Inc"] } } };
  const request = createDashboardReportRequest(
    4,
    ["TAB-TRIPS-REVENUE", undefined, null, "", "TAB-TRIPS-REVENUE"],
    mask,
  );
  assert.deepEqual(JSON.parse(JSON.stringify(request)), {
    dashboard_id: 4,
    active_tabs: ["TAB-TRIPS-REVENUE"],
    data_mask: mask,
  });
  assert.equal(request.data_mask, mask);
});

test("supports dashboards without tabs and refuses unreadable filter state", () => {
  assert.deepEqual(createDashboardReportRequest(undefined, [], {}).active_tabs, []);
  for (const mask of [null, undefined, [], "invalid"]) {
    assert.throws(() => createDashboardReportRequest(4, [], mask), /bộ lọc/);
  }
  assert.throws(() => createDashboardReportRequest(4, [7], {}), /tab/);
  assert.throws(() => createDashboardReportRequest(4, null, {}), /tab/);
});

test("displays FastAPI validation errors instead of object Object", () => {
  const message = supersetErrorMessage(
    { detail: [{ loc: ["body", "active_tabs", 1], msg: "Input should be a valid string" }] },
    422,
  );
  assert.match(message, /body.active_tabs.1: Input should be a valid string/);
  assert.match(message, /HTTP 422/);
  assert.doesNotMatch(message, /object Object/);
});

test("handles gateway HTML, object details and existing string errors", () => {
  assert.match(supersetErrorMessage(null, 504), /mất quá lâu.*HTTP 504/);
  assert.match(
    supersetErrorMessage({ detail: { message: "Report unavailable" } }, 503),
    /Report unavailable/,
  );
  assert.match(supersetErrorMessage({ detail: "Access denied" }, 403), /Access denied.*HTTP 403/);
  assert.doesNotMatch(
    supersetErrorMessage({ detail: { arbitrary: "error" } }, 502),
    /object Object/,
  );
});
