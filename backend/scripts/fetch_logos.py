"""25개 신규 병원 로고 자동 수집.

SKILL.md 의 3단계 절차:
1. Google favicons 서비스 (sz=128) 다운로드 → 48px 이상이면 채택
2. 부족하면 병원 홈페이지에서 <img class="logo"> / <img alt="logo"> 추출
3. 둘 다 실패하면 🏥 이모지 폴백 (파일 안 만듦)

저장: frontend/public/hospital-logos/{CODE}.png 또는 .svg
이미 파일이 있으면 skip.
"""
import io
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse, urljoin

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
LOGOS_DIR = ROOT / "frontend" / "public" / "hospital-logos"

# 코드 → (도메인, 홈페이지 URL)
HOSPITAL_DOMAINS = {
    "DAMC":    ("damc.or.kr",        "https://www.damc.or.kr/"),
    "KOSIN":   ("kosinmed.or.kr",    "https://www.kosinmed.or.kr/"),
    "DCMC":    ("dcmc.co.kr",        "https://www.dcmc.co.kr/"),
    "DKUH":    ("dkuh.co.kr",        "https://www.dkuh.co.kr/"),
    "GNAH":    ("gnah.co.kr",        "https://www.gnah.co.kr/"),
    "UUH":     ("uuh.ulsan.kr",      "https://www.uuh.ulsan.kr/"),
    "KNUH":    ("knuh.or.kr",        "https://www.knuh.or.kr/"),
    "KNUHCG":  ("knuh.or.kr",        "https://www.knuh.or.kr/"),
    "JNUH":    ("cnuh.com",          "https://www.cnuh.com/"),
    "JNUHHS":  ("cnuhh.com",         "https://www.cnuhh.com/"),
    "PAIKBS":  ("paik.ac.kr",        "https://www.paik.ac.kr/busan/"),
    "PNUH":    ("pnuh.or.kr",        "https://www.pnuh.or.kr/"),
    "PNUYH":   ("pnuyh.or.kr",       "https://www.pnuyh.or.kr/"),
    "YUMC":    ("yumc.ac.kr",        "https://www.yumc.ac.kr/"),
    "DSMC":    ("dsmc.or.kr",        "https://www.dsmc.or.kr/"),
    "SCWH":    ("smc.skku.edu",      "https://smc.skku.edu/"),
    "CBNUH":   ("cbnuh.or.kr",       "https://www.cbnuh.or.kr/"),
    "CHNUH":   ("cnuh.co.kr",        "https://www.cnuh.co.kr/"),
    "YWMC":    ("ywmc.or.kr",        "https://www.ywmc.or.kr/"),
    "CUH":     ("hosp.chosun.ac.kr", "https://hosp.chosun.ac.kr/"),
    "KYUH":    ("kyuh.ac.kr",        "https://www.kyuh.ac.kr/"),
    "JBUH":    ("jbuh.co.kr",        "https://www.jbuh.co.kr/"),
    "MIZMEDI": ("mizmedi.com",       "https://mizmedi.com/wweb/main/"),
    "WKUH":    ("wkuh.org",          "https://www.wkuh.org/main/main.do"),
    "GNUH2":   ("gnuh.co.kr",        "https://www.gnuh.co.kr/gnuh/main/main.do?rbsIdx=1"),
}

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36"}
MIN_PX = 48


def write_bytes(path: Path, data: bytes):
    path.write_bytes(data)


def is_valid_image(path: Path) -> tuple[bool, int]:
    """returns (ok, max_dim)."""
    try:
        with Image.open(path) as img:
            return True, max(img.size)
    except Exception:
        return False, 0


def try_google_favicon(domain: str) -> bytes | None:
    url = f"https://www.google.com/s2/favicons?domain={domain}&sz=128"
    try:
        r = requests.get(url, headers=UA, timeout=10)
        if r.status_code == 200 and r.content and len(r.content) > 200:
            return r.content
    except Exception as e:
        print(f"    [favicon err] {e}")
    return None


def fetch_html(url: str) -> str | None:
    """httpx-style 비표준 헤더 호환 위해 curl 폴백."""
    try:
        r = requests.get(url, headers=UA, timeout=15, verify=False, allow_redirects=True)
        if r.status_code == 200 and len(r.text) > 500:
            return r.text
    except Exception:
        pass
    # curl 폴백
    try:
        out = subprocess.run(
            ["curl", "-sk", "-A", UA["User-Agent"], "-L", url],
            capture_output=True, timeout=20,
        )
        text = out.stdout.decode("utf-8", errors="replace")
        if len(text) > 500:
            return text
    except Exception:
        pass
    return None


def find_logo_url(html: str, base_url: str) -> str | None:
    """HTML 에서 logo img src 추출. class/alt/src 에 logo 포함."""
    pat = re.compile(
        r'<img[^>]*?(?:class|alt|id|src)\s*=\s*["\'][^"\']*?logo[^"\']*?["\'][^>]*>',
        re.IGNORECASE,
    )
    for m in pat.findall(html)[:10]:
        src_match = re.search(r'src\s*=\s*["\']([^"\']+)["\']', m, re.IGNORECASE)
        if not src_match:
            continue
        src = src_match.group(1)
        if src.startswith("data:"):
            continue
        if "footer" in m.lower():  # footer 로고는 보통 작음, 헤더 우선
            continue
        return urljoin(base_url, src)
    # 두 번째 시도: footer 도 허용
    for m in pat.findall(html)[:10]:
        src_match = re.search(r'src\s*=\s*["\']([^"\']+)["\']', m, re.IGNORECASE)
        if not src_match:
            continue
        src = src_match.group(1)
        if src.startswith("data:"):
            continue
        return urljoin(base_url, src)
    return None


def fetch_binary(url: str) -> bytes | None:
    try:
        r = requests.get(url, headers=UA, timeout=15, verify=False, allow_redirects=True)
        if r.status_code == 200 and len(r.content) > 200:
            return r.content
    except Exception:
        pass
    try:
        out = subprocess.run(
            ["curl", "-sk", "-A", UA["User-Agent"], "-L", "-o", "-", url],
            capture_output=True, timeout=20,
        )
        if out.returncode == 0 and len(out.stdout) > 200:
            return out.stdout
    except Exception:
        pass
    return None


def process_one(code: str, domain: str, homepage: str) -> str:
    """returns status string."""
    out_png = LOGOS_DIR / f"{code}.png"
    out_svg = LOGOS_DIR / f"{code}.svg"

    if out_png.exists() or out_svg.exists():
        return f"  [skip] {code} — 이미 존재"

    # 1단계: Google favicon
    fav = try_google_favicon(domain)
    if fav:
        out_png.write_bytes(fav)
        ok, max_dim = is_valid_image(out_png)
        if ok and max_dim >= MIN_PX:
            return f"  [ok-favicon] {code} ← {domain} ({max_dim}px)"
        # 작거나 invalid → 다음 단계로
        out_png.unlink(missing_ok=True)

    # 2단계: 홈페이지 logo img 추출
    html = fetch_html(homepage)
    if not html:
        return f"  [fail] {code} — 홈페이지 응답 없음 (이모지 폴백)"

    logo_url = find_logo_url(html, homepage)
    if not logo_url:
        return f"  [fail] {code} — logo img 못 찾음 (이모지 폴백)"

    data = fetch_binary(logo_url)
    if not data:
        return f"  [fail] {code} — 로고 다운로드 실패 (이모지 폴백)"

    # 확장자 결정
    ext = ".svg" if logo_url.lower().endswith(".svg") or data[:5] == b"<?xml" or data[:4] == b"<svg" else ".png"
    out = LOGOS_DIR / f"{code}{ext}"
    out.write_bytes(data)

    if ext == ".png":
        ok, max_dim = is_valid_image(out)
        if not ok:
            out.unlink(missing_ok=True)
            return f"  [fail] {code} — invalid PNG (이모지 폴백)"
        return f"  [ok-html] {code} ← {logo_url} ({max_dim}px)"
    else:
        return f"  [ok-svg] {code} ← {logo_url}"


def main():
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    LOGOS_DIR.mkdir(parents=True, exist_ok=True)

    requests.packages.urllib3.disable_warnings()

    print(f"[start] {len(HOSPITAL_DOMAINS)} hospitals → {LOGOS_DIR}\n")
    results = []
    for code, (domain, homepage) in HOSPITAL_DOMAINS.items():
        print(f"\n=== {code} ({domain}) ===")
        status = process_one(code, domain, homepage)
        print(status)
        results.append(status)

    print("\n" + "=" * 60)
    ok_count = sum(1 for s in results if "[ok-" in s)
    fail_count = sum(1 for s in results if "[fail]" in s)
    skip_count = sum(1 for s in results if "[skip]" in s)
    print(f"[done] ok={ok_count}, fail={fail_count}, skip={skip_count}")


if __name__ == "__main__":
    main()
