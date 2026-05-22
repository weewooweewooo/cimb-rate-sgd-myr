from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime

import requests
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

CIMB_SGD_TO_MYR_URL = "https://www.cimbclicks.com.sg/sgd-to-myr"


@dataclass(frozen=True)
class CimbRateResult:
    checked_at: str
    page_url: str
    rate: float
    rate_list_raw: str
    converted_amts_raw: str | None
    max_transfer_amts_raw: str | None
    display_text: str | None


def fetch_cimb_rate(*, headless: bool = True, timeout_ms: int = 30_000) -> CimbRateResult:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        page = browser.new_page()
        try:
            page.goto(CIMB_SGD_TO_MYR_URL, wait_until="domcontentloaded", timeout=timeout_ms)
            _wait_for_rate_object(page, timeout_ms)
            payload = page.evaluate(
                """
                () => {
                  const getDisplayText = () => {
                    const selectors = [
                      '[data-testid="exchange-rate"]',
                      '[data-testid="fx-rate"]',
                      '.exchange-rate',
                      '.rate',
                    ];
                    for (const selector of selectors) {
                      const el = document.querySelector(selector);
                      if (el && el.textContent) return el.textContent.trim();
                    }
                    return null;
                  };

                  let value = null;
                  let extractionError = null;
                  try {
                    if (typeof getObject === "function" && typeof encodeNamespace === "function") {
                      value = getObject(encodeNamespace("rateList"))?.value ?? null;
                    }
                  } catch (err) {
                    extractionError = String(err);
                  }

                  const bodyText = document.body?.innerText ?? "";
                  return {
                    value,
                    extractionError,
                    displayText: getDisplayText(),
                    bodyTextSample: bodyText.slice(0, 1200),
                  };
                }
                """
            )
        finally:
            browser.close()

    extracted = payload.get("value") if isinstance(payload, dict) else None
    display_text = payload.get("displayText") if isinstance(payload, dict) else None
    body_sample = payload.get("bodyTextSample") if isinstance(payload, dict) else None
    extraction_error = payload.get("extractionError") if isinstance(payload, dict) else None

    data = extracted if isinstance(extracted, dict) else {}
    rate_list_raw = data.get("rateList") if isinstance(data.get("rateList"), str) else None
    converted_raw = data.get("convertedAmts") if isinstance(data.get("convertedAmts"), str) else None
    max_transfer_raw = (
        data.get("maxTransferAmts") if isinstance(data.get("maxTransferAmts"), str) else None
    )

    if not rate_list_raw:
        fallback = _extract_rate_list_from_text(body_sample or "")
        if fallback:
            rate_list_raw = fallback

    fallback_error: str | None = None
    if not rate_list_raw:
        try:
            fallback_payload = _fetch_rate_via_http_fallback(timeout_ms=timeout_ms)
            rate_list_raw = fallback_payload.get("rateList")
            converted_raw = fallback_payload.get("convertedAmts")
            max_transfer_raw = fallback_payload.get("maxTransferAmts")
            display_text = display_text or fallback_payload.get("displayText")
        except Exception as exc:  # noqa: BLE001
            fallback_error = str(exc)

    if not rate_list_raw:
        raise RuntimeError(
            "Unable to extract rateList from CIMB page. "
            f"extraction_error={extraction_error!r}, payload_keys={list(data.keys())}, "
            f"fallback_error={fallback_error!r}, body_sample={body_sample!r}"
        )

    rate = _parse_first_rate(rate_list_raw)
    return CimbRateResult(
        checked_at=datetime.now().isoformat(timespec="seconds"),
        page_url=CIMB_SGD_TO_MYR_URL,
        rate=rate,
        rate_list_raw=rate_list_raw,
        converted_amts_raw=converted_raw,
        max_transfer_amts_raw=max_transfer_raw,
        display_text=display_text,
    )


def _wait_for_rate_object(page, timeout_ms: int) -> None:
    try:
        page.wait_for_function(
            """() =>
              typeof window.getObject === "function" &&
              typeof window.encodeNamespace === "function"
            """,
            timeout=min(timeout_ms, 10_000),
        )
    except PlaywrightTimeoutError:
        # Keep going; we'll still attempt extraction and provide explicit error context.
        pass


def _parse_first_rate(rate_list_raw: str) -> float:
    values = _parse_rate_list(rate_list_raw)
    if not values:
        raise RuntimeError(f"rateList parsed but empty: {rate_list_raw!r}")
    return float(values[0])


def _parse_rate_list(rate_list_raw: str) -> list[float]:
    raw = rate_list_raw.strip()
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [float(item) for item in parsed]
    except json.JSONDecodeError:
        pass

    trimmed = raw.strip("[]").strip()
    if not trimmed:
        return []
    return [float(item.strip()) for item in trimmed.split(",") if item.strip()]


def _extract_rate_list_from_text(source: str) -> str | None:
    match = re.search(r'"rateList"\s*:\s*"(\[[^"]+\])"', source)
    if match:
        return match.group(1)
    return None


def _fetch_rate_via_http_fallback(timeout_ms: int) -> dict[str, str | None]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/136.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-SG,en;q=0.9",
    }
    response = requests.get(CIMB_SGD_TO_MYR_URL, headers=headers, timeout=timeout_ms / 1000)
    response.raise_for_status()
    html = response.text

    rate_list = _extract_hidden_value(html, "rateList")
    converted = _extract_hidden_value(html, "convertedAmts")
    max_transfer = _extract_hidden_value(html, "maxTransferAmts")
    display_text = _extract_rate_label(html)

    if not rate_list:
        raise RuntimeError("HTTP fallback loaded page but hidden rateList input was not found.")

    return {
        "rateList": rate_list,
        "convertedAmts": converted,
        "maxTransferAmts": max_transfer,
        "displayText": display_text,
    }


def _extract_hidden_value(html: str, field_name: str) -> str | None:
    pattern = rf'name="[^"]*_{field_name}"[^>]*value="([^"]+)"'
    match = re.search(pattern, html)
    if match:
        return match.group(1)
    return None


def _extract_rate_label(html: str) -> str | None:
    match = re.search(r'<label id="rateStr"[^>]*>([^<]*)</label>', html)
    if match:
        return match.group(1).strip() or None
    return None
