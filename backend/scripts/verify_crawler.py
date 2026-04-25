"""단일 병원 크롤러 검증 스크립트.

사용법 (backend/ 디렉터리에서 실행):
    python scripts/verify_crawler.py --hospital SNUH
    python scripts/verify_crawler.py --hospital HYUMC --timeout 180

9개 품질 체크(C1~C9)를 수행하고 JSON 결과를 반환한다.
판정: OK / WARN / FAIL

verify_all.py 에서 `run_one()` 을 import 해서 사용한다.
"""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

# backend/ 를 sys.path 에 추가하여 `app.*` import 가능하게
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Windows + Playwright 호환 (run.py 와 동일 설정)
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


def _setup_io() -> None:
    """stdout/stderr 을 UTF-8 TextIOWrapper 로 래핑 (한 번만)."""
    if sys.platform != "win32":
        return
    if getattr(sys.stdout, "_wrapped_utf8", False):
        return
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
    sys.stdout._wrapped_utf8 = True  # type: ignore[attr-defined]

from app.crawlers._schedule_rules import (
    find_exclude_keyword,
    has_biweekly_mark,
)
from app.crawlers.factory import _DEDICATED_CRAWLERS, _HOSPITAL_REGION, get_crawler
from app.schemas.schemas import CrawlResult

# 달력형 (월별 date_schedules) 을 반드시 지원해야 하는 병원
CALENDAR_HOSPITALS = {"HYUMC", "KUH", "KCCH", "KBSMC"}


def _run_quality_checks(result: CrawlResult) -> dict:
    """CrawlResult 에 대해 C1~C9 중 실행-후 가능한 체크(C2~C9)를 수행."""
    findings: list[dict] = []
    warnings: list[dict] = []

    doctors = result.doctors or []
    n = len(doctors)

    # C2: 의사 수
    if n < 5:
        warnings.append({"check": "C2", "msg": f"의사 수 부족 ({n}명)"})

    # C3: 진료과 수
    depts = {d.department for d in doctors if d.department}
    if len(depts) < 1:
        warnings.append({"check": "C3", "msg": "진료과 0개"})

    # C4: external_id 고유성
    ids = [d.external_id for d in doctors if d.external_id]
    dup = {x for x in ids if ids.count(x) > 1}
    if dup:
        findings.append({
            "check": "C4",
            "msg": f"external_id 중복 {len(dup)}건",
            "samples": list(dup)[:5],
        })

    # C5: 스키마 적합성 — CrawlResult 가 만들어졌으면 통과한 것이므로 통과

    # C6: 스케줄 0건 비율
    # 단, notes 에 "시간표 미공개" 안내가 있는 의사는 의도적으로 비어있는 것이라
    # 실제 스케줄 비율 계산에서 제외 (모두 미공개면 그 병원은 OK)
    no_pub_keywords = ("공개되지", "공개하지", "공개되어 있지", "이미지로만", "직접 문의")
    def _intentionally_empty(d) -> bool:
        if d.schedules or d.date_schedules:
            return False
        notes = d.notes or ""
        return any(kw in notes for kw in no_pub_keywords)
    intentional = sum(1 for d in doctors if _intentionally_empty(d))
    empty = sum(
        1 for d in doctors
        if not d.schedules and not d.date_schedules
    )
    real_empty = empty - intentional
    eligible = n - intentional
    empty_ratio = (real_empty / eligible * 100) if eligible else 0.0
    if empty_ratio > 70:
        warnings.append({
            "check": "C6",
            "msg": f"스케줄 없는 의사 {empty_ratio:.0f}% ({real_empty}/{eligible})"
                   + (f" — 미공개 안내 {intentional}명 제외" if intentional else ""),
        })

    # C7: EXCLUDE 키워드 누수
    leaks: list[dict] = []
    for d in doctors:
        for s in d.schedules or []:
            loc = (s.get("location") or "")
            kw = find_exclude_keyword(loc)
            if kw:
                leaks.append({
                    "doctor": d.name, "dept": d.department,
                    "location": loc, "keyword": kw,
                })
        for s in d.date_schedules or []:
            loc = (s.get("location") or "")
            kw = find_exclude_keyword(loc)
            if kw:
                leaks.append({
                    "doctor": d.name, "dept": d.department,
                    "location": loc, "keyword": kw,
                })
    if leaks:
        warnings.append({
            "check": "C7",
            "msg": f"제외 키워드 누수 {len(leaks)}건",
            "samples": leaks[:5],
        })

    # C8: 격주 notes 반영
    missing_biweekly: list[dict] = []
    for d in doctors:
        had_biweekly = False
        for s in (d.schedules or []) + (d.date_schedules or []):
            loc = s.get("location") or ""
            if has_biweekly_mark(loc):
                had_biweekly = True
                break
        if had_biweekly:
            notes = d.notes or ""
            if not has_biweekly_mark(notes):
                missing_biweekly.append({
                    "doctor": d.name, "dept": d.department,
                })
    if missing_biweekly:
        warnings.append({
            "check": "C8",
            "msg": f"격주 근무인데 notes 미반영 {len(missing_biweekly)}명",
            "samples": missing_biweekly[:5],
        })

    # C9: 달력형 date_schedules
    if result.hospital_code in CALENDAR_HOSPITALS:
        has_date = any((d.date_schedules or []) for d in doctors)
        if not has_date:
            warnings.append({
                "check": "C9",
                "msg": "달력형 병원인데 date_schedules 전원 비어있음",
            })

    return {
        "n_doctors": n,
        "n_departments": len(depts),
        "empty_schedule_ratio": round(empty_ratio, 1),
        "findings": findings,
        "warnings": warnings,
    }


async def run_one(code: str, timeout: float = 120.0) -> dict:
    """한 병원을 크롤링하고 9가지 품질 체크 결과를 반환."""
    code = code.upper()
    started_at = time.monotonic()
    entry = _DEDICATED_CRAWLERS.get(code)
    hospital_name = entry[1] if entry else code
    region = _HOSPITAL_REGION.get(code, "")

    base = {
        "code": code,
        "name": hospital_name,
        "region": region,
        "started_at": datetime.utcnow().isoformat(),
    }

    # C1: 실행
    try:
        crawler = get_crawler(code)
    except Exception as e:
        return {
            **base,
            "verdict": "FAIL",
            "elapsed": 0.0,
            "error": f"팩토리 생성 실패: {e}",
            "findings": [{"check": "C1", "msg": str(e)}],
            "warnings": [],
            "n_doctors": 0,
            "n_departments": 0,
            "empty_schedule_ratio": 0.0,
        }

    try:
        result: CrawlResult = await asyncio.wait_for(
            crawler.crawl_doctors(), timeout=timeout,
        )
    except asyncio.TimeoutError:
        return {
            **base,
            "verdict": "FAIL",
            "elapsed": timeout,
            "error": f"Timeout after {timeout}s",
            "findings": [{"check": "C1", "msg": f"Timeout after {timeout}s"}],
            "warnings": [],
            "n_doctors": 0,
            "n_departments": 0,
            "empty_schedule_ratio": 0.0,
        }
    except Exception as e:
        return {
            **base,
            "verdict": "FAIL",
            "elapsed": round(time.monotonic() - started_at, 1),
            "error": f"{type(e).__name__}: {e}",
            "findings": [{
                "check": "C1",
                "msg": f"{type(e).__name__}: {e}",
                "traceback": traceback.format_exc(limit=3),
            }],
            "warnings": [],
            "n_doctors": 0,
            "n_departments": 0,
            "empty_schedule_ratio": 0.0,
        }

    elapsed = round(time.monotonic() - started_at, 1)
    checks = _run_quality_checks(result)

    if checks["findings"]:
        verdict = "FAIL"
    elif checks["warnings"]:
        verdict = "WARN"
    else:
        verdict = "OK"

    # 스냅샷 저장 (경량화 — 핵심 필드만)
    snap_dir = BACKEND_ROOT / "scripts" / "verification_snapshots"
    snap_dir.mkdir(exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    snap_path = snap_dir / f"{code}_{ts}.json"
    try:
        with snap_path.open("w", encoding="utf-8") as f:
            json.dump({
                "hospital_code": result.hospital_code,
                "hospital_name": result.hospital_name,
                "status": result.status,
                "doctors": [
                    {
                        "name": d.name,
                        "department": d.department,
                        "external_id": d.external_id,
                        "n_schedules": len(d.schedules or []),
                        "n_date_schedules": len(d.date_schedules or []),
                        "notes": d.notes,
                    }
                    for d in result.doctors[:500]  # 최대 500명
                ],
            }, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    return {
        **base,
        "verdict": verdict,
        "elapsed": elapsed,
        "error": None,
        **checks,
        "snapshot": str(snap_path.relative_to(BACKEND_ROOT)),
    }


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="단일 병원 크롤러 검증")
    p.add_argument("--hospital", required=True, help="병원 코드 (예: SNUH)")
    p.add_argument("--timeout", type=float, default=120.0, help="타임아웃 초")
    return p.parse_args()


async def _main() -> None:
    args = _parse_args()
    result = await run_one(args.hospital, timeout=args.timeout)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    _setup_io()
    asyncio.run(_main())
