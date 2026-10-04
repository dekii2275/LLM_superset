# Superset chart images in PDF reports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put screenshots of the saved Superset charts beside their LLM insights in the existing PDF report.

**Architecture:** Enable Superset's thumbnail cache API with Redis and a Celery/Playwright worker. The existing backend report endpoint requests each chart's cached PNG, returns it as base64 with the chart data, and the existing frontend places that image in the PDF document.

**Tech Stack:** Superset 6.1.0, Redis, Celery, Playwright/Chromium, FastAPI, Python `unittest`, Next.js/React, html2canvas, jsPDF.

**Spec:** `docs/superpowers/specs/2026-10-02-superset-chart-images-design.md`

## Global Constraints

- Use Superset 6.1.0's built-in `THUMBNAILS` screenshot API.
- Use the existing Redis instance for screenshot cache and Celery broker.
- Keep report scope to saved chart configuration; do not apply active dashboard filters.
- Keep existing browser-side PDF generation and Save dialog behavior.
- Keep Superset credentials server-side; only request image paths formed from chart IDs and cache keys returned by Superset.
- Do not silently replace a failed screenshot with a generic chart.

## Review Focus

- **Asynchronous cache state:** Superset may return `Pending`/`Computing` before `Updated`; test polling through `Updated`.
- **Worker failure:** Superset may return `Error` or remain pending; test immediate error and bounded timeout.
- **Image integrity:** screenshot endpoint must return a PNG; test that invalid image bytes fail clearly.
- **Path safety:** request the screenshot path derived from the known chart ID/cache key, never a URL supplied by the response; assert the path in the polling test.
- **Report association:** each chart image must stay paired with the same chart title and LLM insight; test the report response mapping.

---

### Task 1: Enable Superset screenshot workers

**Files:**
- Modify: `superset/superset_config.py`
- Modify: `superset/Dockerfile`
- Modify: `docker-compose.yml`

**Interfaces:**
- Produces a `superset-worker` Compose service that shares Superset's environment, Redis, metadata volume, and custom image.
- Superset exposes `THUMBNAILS`, uses Playwright for screenshots, and uses the existing Redis instance for Celery and thumbnail cache.

- [ ] Add Playwright and Chromium to the Superset image used by both web and worker processes.
- [ ] Enable `THUMBNAILS` and `PLAYWRIGHT_REPORTS_AND_THUMBNAILS`, set `WEBDRIVER_BASEURL` to the internal Superset service URL, configure Redis `THUMBNAIL_CACHE_CONFIG`/Celery task imports, and add a one-concurrency Celery worker using `superset.tasks.celery_app:app`.
- [ ] Validate Compose configuration with `docker compose config --quiet` and build the Superset image. Expected: valid Compose config and successful image build.

### Task 2: Fetch cached PNGs through SupersetClient

**Files:**
- Modify: `backend/app/services/superset.py`
- Test: `backend/tests/test_superset_dashboard_report.py`

**Interfaces:**
- Add `SupersetClient.chart_screenshot(chart_id: int) -> bytes`.
- Add the smallest binary-response helper needed by that method; keep JSON behavior of `request()` unchanged.

- [ ] **Step 1: Write failing tests** named `test_chart_screenshot_polls_until_updated`, `test_chart_screenshot_raises_on_superset_error`, `test_chart_screenshot_times_out`, and `test_chart_screenshot_rejects_non_png`.
- [ ] **Step 2: Run** `python -m unittest discover -s tests -p test_superset_dashboard_report.py -v` from `backend/`. Expected: the new tests fail because screenshot retrieval is not implemented.
- [ ] **Step 3: Implement** the authenticated Superset `cache_screenshot` polling flow; accept `Updated`, fail on `Error`/timeout, and retrieve the PNG using `/api/v1/chart/{chart_id}/screenshot/{cache_key}/`.
- [ ] **Step 4: Run** `python -m unittest discover -s tests -p test_superset_dashboard_report.py -v` from `backend/`. Expected: screenshot state, path, timeout, and PNG checks pass.

### Task 3: Attach screenshots to the report API response

**Files:**
- Modify: `backend/app/api/superset.py`
- Test: `backend/tests/test_superset_dashboard_report.py`

**Interfaces:**
- Preserve `POST /api/v1/superset/report` and its current report fields.
- Add an `image_base64` string field to each chart, encoded from `chart_screenshot()` PNG bytes.

- [ ] **Step 1: Write failing test** `test_dashboard_report_includes_each_chart_image`, asserting each image is base64-encoded and remains associated with its chart ID/title.
- [ ] **Step 2: Run** `python -m unittest discover -s tests -p test_superset_dashboard_report.py -v` from `backend/`. Expected: the new API response assertion fails because images are absent.
- [ ] **Step 3: Implement** screenshot retrieval in the existing report flow using `asyncio.to_thread(client.chart_screenshot, chart_id)` and return `image_base64` for every chart.
- [ ] **Step 4: Run** `python -m unittest discover -s tests -p test_superset_dashboard_report.py -v` from `backend/`. Expected: report and screenshot tests pass.

### Task 4: Render Superset PNGs in the PDF

**Files:**
- Modify: `frontend/components/superset/EmbeddedDashboard.tsx`
- Modify: `frontend/app/globals.css`

**Interfaces:**
- Extend the frontend chart type with `image_base64: string`.
- Render each chart using a PNG data URL in the hidden report document; keep the current LLM insight text and PDF save flow.

- [ ] Replace `ReportChart`'s generic `DynamicChart` reconstruction with an `<img>` using the corresponding chart PNG; remove now-unused chart reconstruction imports and wait logic, waiting for image `decode()` before PDF capture.
- [ ] Style report images to fit the existing report column without distortion.
- [ ] Run `npm run build` from `frontend/`. Expected: production build succeeds.

### Task 5: Verify end-to-end PDF output

**Files:** None.

- [ ] Rebuild/restart Superset and the new worker with Compose.
- [ ] Generate a PDF from the local dashboard and visually confirm its charts retain Superset labels, colors, and marks alongside the matching LLM insights.
- [ ] Run `python -m unittest discover -s tests -v` from `backend/` and `npm run build` from `frontend/`; report any environment-blocked integration step explicitly.
