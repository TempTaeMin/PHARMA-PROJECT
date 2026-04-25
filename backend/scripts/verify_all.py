"""지역별 병원 크롤러 전수 검증 러너.

사용법 (backend/ 에서 실행):
    python scripts/verify_all.py --region 서울,경기,인천
    python scripts/verify_all.py --region 인천 --concurrency 2

concurrency 기본 4 — 동시에 서로 다른 병원 사이트로만 요청하므로 안전.
결과는 루트 validation_result.md 로 저장된다.
"""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from scripts.verify_crawler import _setup_io, run_one  # noqa: E402
from app.crawlers.factory import _HOSPITAL_REGION  # noqa: E402

VERDICT_ICON = {"OK": "✅", "WARN": "⚠️", "FAIL": "❌"}


def _select_targets(regions: set[str]) -> list[str]:
    codes = [c for c, r in _HOSPITAL_REGION.items() if r in regions]
    codes.sort()
    return codes


async def _run_with_semaphore(sem: asyncio.Semaphore, code: str, timeout: float,
                              progress_prefix: str) -> dict:
    async with sem:
        print(f"  {progress_prefix} start   {code}", flush=True)
        t0 = time.monotonic()
        try:
            res = await run_one(code, timeout=timeout)
        except Exception as e:
            res = {
                "code": code, "name": code, "region": "",
                "verdict": "FAIL",
                "error": f"runner exception: {type(e).__name__}: {e}",
                "elapsed": round(time.monotonic() - t0, 1),
                "n_doctors": 0, "n_departments": 0,
                "empty_schedule_ratio": 0.0,
                "findings": [{"check": "C1", "msg": str(e)}],
                "warnings": [],
            }
        icon = VERDICT_ICON.get(res["verdict"], "?")
        print(
            f"  {progress_prefix} done    {code:<12} {icon} "
            f"{res.get('verdict'):<4} "
            f"의사 {res.get('n_doctors', 0):>3} / "
            f"{res.get('elapsed', 0):>5.1f}s",
            flush=True,
        )
        return res


async def run_all(regions: set[str], concurrency: int, timeout: float) -> list[dict]:
    codes = _select_targets(regions)
    print(f"[info] 대상 병원 {len(codes)}개 (지역: {', '.join(sorted(regions))})")
    print(f"[info] concurrency={concurrency}, timeout={timeout}s")
    print(f"[info] 시작: {datetime.now().strftime('%H:%M:%S')}")

    sem = asyncio.Semaphore(concurrency)
    tasks = [
        _run_with_semaphore(sem, code, timeout, f"[{i+1}/{len(codes)}]")
        for i, code in enumerate(codes)
    ]
    results = await asyncio.gather(*tasks)
    return results


def _build_report(results: list[dict], regions: set[str], wall_elapsed: float) -> str:
    total = len(results)
    by_verdict = Counter(r["verdict"] for r in results)
    n_ok = by_verdict.get("OK", 0)
    n_warn = by_verdict.get("WARN", 0)
    n_fail = by_verdict.get("FAIL", 0)

    total_doctors = sum(r.get("n_doctors", 0) for r in results)
    avg_elapsed = (
        sum(r.get("elapsed", 0.0) for r in results) / total if total else 0.0
    )
    avg_empty = (
        sum(r.get("empty_schedule_ratio", 0.0) for r in results) / total
        if total else 0.0
    )

    lines: list[str] = []
    lines.append("# 서울/경기 크롤러 1차 검증 결과")
    lines.append("")
    lines.append(f"- 검증 일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- 대상 지역: {', '.join(sorted(regions))}")
    lines.append(f"- 전체: **{total}**개 / 총 소요: {wall_elapsed:.1f}s")
    lines.append(
        f"- ✅ OK **{n_ok}** / ⚠️ WARN **{n_warn}** / ❌ FAIL **{n_fail}**"
    )
    lines.append(f"- 수집된 의사 총합: {total_doctors:,}명")
    lines.append(
        f"- 평균 실행시간: {avg_elapsed:.1f}s / "
        f"평균 스케줄 미보유 비율: {avg_empty:.1f}%"
    )
    lines.append("")

    # 결과표
    lines.append("## 전체 결과표")
    lines.append("")
    lines.append(
        "| 코드 | 병원명 | 지역 | 판정 | 의사 | 진료과 | 빈스케줄% | 시간(s) | 주요 이슈 |"
    )
    lines.append(
        "|------|--------|------|------|------|--------|-----------|---------|-----------|"
    )
    order = {"FAIL": 0, "WARN": 1, "OK": 2}
    sorted_results = sorted(
        results, key=lambda r: (order.get(r["verdict"], 9), r["code"])
    )
    for r in sorted_results:
        icon = VERDICT_ICON.get(r["verdict"], "?")
        issues: list[str] = []
        for f in r.get("findings", []):
            issues.append(f"{f['check']}:{f['msg']}")
        for w in r.get("warnings", []):
            issues.append(f"{w['check']}:{w['msg']}")
        issue_str = "; ".join(issues) if issues else "-"
        if len(issue_str) > 60:
            issue_str = issue_str[:57] + "..."
        lines.append(
            f"| {r['code']} | {r.get('name', '')} | {r.get('region', '')} | "
            f"{icon} {r['verdict']} | "
            f"{r.get('n_doctors', 0)} | "
            f"{r.get('n_departments', 0)} | "
            f"{r.get('empty_schedule_ratio', 0):.0f}% | "
            f"{r.get('elapsed', 0):.1f} | {issue_str} |"
        )
    lines.append("")

    # FAIL 상세
    fails = [r for r in results if r["verdict"] == "FAIL"]
    if fails:
        lines.append("## ❌ FAIL 상세")
        lines.append("")
        for r in fails:
            lines.append(f"### {r.get('name', '')} ({r['code']}) — {r.get('region', '')}")
            if r.get("error"):
                lines.append(f"- 원인: `{r['error']}`")
            for f in r.get("findings", []):
                lines.append(f"- {f['check']}: {f['msg']}")
                if "samples" in f:
                    lines.append(f"  - 샘플: `{f['samples']}`")
                if "traceback" in f:
                    tb = f['traceback'].strip().split('\n')
                    lines.append("  - traceback:")
                    for tb_line in tb[-5:]:
                        lines.append(f"    `{tb_line}`")
            lines.append("")

    # WARN 상세
    warns = [r for r in results if r["verdict"] == "WARN"]
    if warns:
        lines.append("## ⚠️ WARN 상세")
        lines.append("")
        for r in warns:
            lines.append(f"### {r.get('name', '')} ({r['code']}) — {r.get('region', '')}")
            lines.append(
                f"- 의사 {r.get('n_doctors', 0)}명, 진료과 {r.get('n_departments', 0)}개, "
                f"실행 {r.get('elapsed', 0):.1f}s"
            )
            for w in r.get("warnings", []):
                lines.append(f"- {w['check']}: {w['msg']}")
                if "samples" in w:
                    lines.append(f"  - 샘플(최대 5개):")
                    for s in w["samples"]:
                        lines.append(f"    - `{s}`")
            lines.append("")

    # 전체 통계
    lines.append("## 통계")
    lines.append("")
    warn_codes_by_check: dict[str, list[str]] = {}
    for r in results:
        for w in r.get("warnings", []):
            warn_codes_by_check.setdefault(w["check"], []).append(r["code"])
    for check, codes in sorted(warn_codes_by_check.items()):
        lines.append(f"- {check}: {len(codes)}개 병원 ({', '.join(sorted(codes)[:15])}"
                     f"{'...' if len(codes) > 15 else ''})")

    return "\n".join(lines) + "\n"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="지역별 병원 크롤러 전수 검증")
    p.add_argument(
        "--region",
        default="서울,경기,인천",
        help="대상 지역(콤마구분). 예: 서울,경기 또는 인천",
    )
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--timeout", type=float, default=120.0)
    p.add_argument(
        "--output",
        default=str(PROJECT_ROOT / "validation_result.md"),
        help="리포트 저장 경로",
    )
    return p.parse_args()


async def _main() -> None:
    args = _parse_args()
    regions = {x.strip() for x in args.region.split(",") if x.strip()}

    t_start = time.monotonic()
    results = await run_all(regions, args.concurrency, args.timeout)
    wall = time.monotonic() - t_start

    # JSON raw dump (트러블슈팅용)
    raw_path = Path(args.output).with_suffix(".json")
    try:
        raw_path.write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as e:
        print(f"[warn] JSON 저장 실패: {e}")

    report = _build_report(results, regions, wall)
    out_path = Path(args.output)
    out_path.write_text(report, encoding="utf-8")
    print(f"\n[done] 리포트: {out_path}")
    print(f"[done] raw json: {raw_path}")


if __name__ == "__main__":
    _setup_io()
    asyncio.run(_main())
