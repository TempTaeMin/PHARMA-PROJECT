"""서울아산병원 크롤링 PoC 테스트

실제 병원 홈페이지에 접속하여 크롤링 가능 여부를 확인합니다.
테스트 항목:
1. 진료과 목록 조회
2. 특정 진료과 의료진 목록 크롤링
3. 특정 의료진 상세정보 + 진료시간표 크롤링
"""
import asyncio
import json
import httpx
import re
from bs4 import BeautifulSoup
from datetime import datetime


BASE_URL = "https://www.amc.seoul.kr"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}


async def test_1_connectivity():
    """1단계: 서울아산병원 사이트 접근 가능 여부"""
    print("=" * 60)
    print("TEST 1: 사이트 접근성 테스트")
    print("=" * 60)

    async with httpx.AsyncClient(headers=HEADERS, timeout=15, follow_redirects=True) as client:
        urls = [
            (f"{BASE_URL}/asan/main.do", "메인 페이지"),
            (f"{BASE_URL}/asan/departments/deptListTypeA.do", "진료과 목록"),
            (f"{BASE_URL}/asan/staff/base/staffBaseInfoList.do", "의료진 목록"),
        ]
        for url, desc in urls:
            try:
                resp = await client.get(url)
                print(f"  ✅ {desc}: HTTP {resp.status_code} (길이: {len(resp.text):,}자)")
            except Exception as e:
                print(f"  ❌ {desc}: {e}")


async def test_2_find_staff_ids():
    """2단계: 진료과 페이지에서 의료진 staffId 추출"""
    print("\n" + "=" * 60)
    print("TEST 2: 의료진 ID 추출 테스트 (정형외과 D038)")
    print("=" * 60)

    async with httpx.AsyncClient(headers=HEADERS, timeout=15, follow_redirects=True) as client:
        # 정형외과 페이지
        url = f"{BASE_URL}/asan/depts/D038/K/deptLink.do"
        resp = await client.get(url)
        soup = BeautifulSoup(resp.text, "html.parser")

        # 방법 1: staffId가 포함된 링크 찾기
        staff_links = soup.find_all("a", href=re.compile(r"staffId="))
        print(f"\n  방법1 (staffId 링크): {len(staff_links)}개 발견")
        for link in staff_links[:5]:
            href = link.get("href", "")
            match = re.search(r"staffId=(\w+)", href)
            name = link.get_text(strip=True)[:20]
            if match:
                print(f"    → staffId={match.group(1)}, 이름={name}")

        # 방법 2: HTML 전체에서 staffId 패턴 찾기
        all_ids = set(re.findall(r"staffId['\"]?\s*[:=]\s*['\"]?(\w+)", resp.text))
        print(f"\n  방법2 (전체 텍스트): {len(all_ids)}개 staffId 발견")
        for sid in list(all_ids)[:10]:
            print(f"    → {sid}")

        # 방법 3: 의료진 목록 AJAX 호출 시도
        ajax_url = f"{BASE_URL}/asan/staff/base/staffBaseInfoList.do"
        ajax_data = {"deptCd": "D038", "pageIndex": "1"}
        try:
            resp2 = await client.post(ajax_url, data=ajax_data)
            if resp2.status_code == 200:
                soup2 = BeautifulSoup(resp2.text, "html.parser")
                ajax_ids = set(re.findall(r"staffId['\"]?\s*[:=]\s*['\"]?(\w+)", resp2.text))
                print(f"\n  방법3 (AJAX POST): {len(ajax_ids)}개 staffId 발견")
                for sid in list(ajax_ids)[:10]:
                    print(f"    → {sid}")
        except Exception as e:
            print(f"\n  방법3 (AJAX POST): 실패 - {e}")

        return all_ids


async def test_3_doctor_detail(staff_id: str):
    """3단계: 특정 의료진 상세정보 + 진료시간표 크롤링"""
    print("\n" + "=" * 60)
    print(f"TEST 3: 의료진 상세 크롤링 (staffId={staff_id})")
    print("=" * 60)

    async with httpx.AsyncClient(headers=HEADERS, timeout=15, follow_redirects=True) as client:
        # 기본 정보 페이지
        info_url = f"{BASE_URL}/asan/staff/base/staffBaseInfoView.do?staffId={staff_id}"
        resp = await client.get(info_url)
        soup = BeautifulSoup(resp.text, "html.parser")

        print(f"\n  📄 기본정보 페이지: HTTP {resp.status_code}")

        # og:title 메타태그에서 이름 추출
        og_title = soup.find("meta", {"property": "og:title"})
        if og_title:
            print(f"  이름 (og:title): {og_title.get('content', 'N/A')}")

        # 페이지 타이틀
        title = soup.find("title")
        if title:
            print(f"  페이지 타이틀: {title.get_text(strip=True)}")

        # 주요 텍스트 요소 탐색
        for selector in [".staffName", "h3.tit", ".doctor-name", ".infoName",
                         ".professorName", ".docName"]:
            elem = soup.select_one(selector)
            if elem:
                print(f"  이름 ({selector}): {elem.get_text(strip=True)}")

        # 진료시간표 페이지
        sched_url = f"{BASE_URL}/asan/staff/schedule/staffScheduleView.do?staffId={staff_id}"
        resp2 = await client.get(sched_url)
        soup2 = BeautifulSoup(resp2.text, "html.parser")

        print(f"\n  📅 진료시간표 페이지: HTTP {resp2.status_code}")

        # 테이블 찾기
        tables = soup2.find_all("table")
        print(f"  테이블 수: {len(tables)}")

        for i, table in enumerate(tables):
            rows = table.find_all("tr")
            print(f"\n  --- 테이블 {i+1} ({len(rows)}행) ---")
            for row in rows[:6]:
                cells = row.find_all(["th", "td"])
                row_text = " | ".join(c.get_text(strip=True)[:15] for c in cells)
                print(f"    {row_text}")

        # 텍스트에서 진료 관련 키워드 찾기
        text = soup2.get_text()
        schedule_patterns = [
            r"([월화수목금토일])\s*(?:요일)?\s*[:\s]?\s*(오전|오후)",
            r"(오전|오후)\s*[:\s]?\s*([월화수목금토일])",
            r"진료\s*시간",
        ]
        print(f"\n  📝 텍스트 기반 일정 패턴 탐색:")
        for pat in schedule_patterns:
            matches = re.findall(pat, text)
            if matches:
                print(f"    패턴 '{pat}': {matches[:5]}")


async def test_4_api_endpoints():
    """4단계: 숨겨진 API 엔드포인트 탐색"""
    print("\n" + "=" * 60)
    print("TEST 4: AJAX/API 엔드포인트 탐색")
    print("=" * 60)

    async with httpx.AsyncClient(headers=HEADERS, timeout=15, follow_redirects=True) as client:
        # 의료진 검색 API 시도
        search_urls = [
            (f"{BASE_URL}/asan/staff/base/staffBaseInfoList.do", "POST", {"deptCd": "D038", "searchKeyword": ""}),
            (f"{BASE_URL}/asan/staff/base/getStaffList.do", "POST", {"deptCd": "D038"}),
            (f"{BASE_URL}/asan/staff/schedule/staffScheduleList.do", "POST", {"deptCd": "D038"}),
        ]

        for url, method, data in search_urls:
            try:
                if method == "POST":
                    resp = await client.post(url, data=data)
                else:
                    resp = await client.get(url, params=data)
                
                content_type = resp.headers.get("content-type", "")
                is_json = "json" in content_type
                is_html = "html" in content_type

                print(f"\n  {method} {url.split('/asan/')[-1]}")
                print(f"    → HTTP {resp.status_code}, Type: {content_type[:40]}")
                print(f"    → 길이: {len(resp.text):,}자, JSON: {is_json}")

                if is_json:
                    try:
                        data = resp.json()
                        print(f"    → JSON Keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
                    except:
                        pass

                # staffId가 포함되어 있는지 확인
                ids = set(re.findall(r"staffId['\"]?\s*[:=]\s*['\"]?(\w+)", resp.text))
                if ids:
                    print(f"    → staffId 발견: {len(ids)}개 — {list(ids)[:5]}")

            except Exception as e:
                print(f"\n  {method} {url.split('/asan/')[-1]}")
                print(f"    → 실패: {e}")


async def main():
    print("🏥 서울아산병원 크롤링 PoC 테스트")
    print(f"📅 실행 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # 1. 접근성 테스트
    await test_1_connectivity()

    # 2. 의료진 ID 추출
    staff_ids = await test_2_find_staff_ids()

    # 3. 의료진 상세 크롤링 (첫 번째 발견된 ID 사용)
    if staff_ids:
        test_id = list(staff_ids)[0]
        await test_3_doctor_detail(test_id)
    else:
        print("\n⚠️ staffId를 찾지 못해 상세 테스트를 건너뜁니다.")

    # 4. API 엔드포인트 탐색
    await test_4_api_endpoints()

    print("\n" + "=" * 60)
    print("✅ PoC 테스트 완료")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
