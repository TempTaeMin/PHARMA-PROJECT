"""서울아산병원 맞춤 크롤러

실제 페이지 구조 기반으로 만든 크롤러.
httpx로 직접 HTTP 요청 → HTML 파싱 → 교수 목록 + 상세 + 진료시간표 추출.

URL 패턴:
  의료진 목록: /asan/departments/deptDetail.do?hpCd={과코드}&type=K&moduleMenuId=3133
  교수 상세:   /asan/staff/base/staffBaseInfoDetail.do?drEmpId={id}&searchHpCd={과코드}

교수 ID: drEmpId= 뒤의 Base64 암호화 문자열
"""
import re
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://www.amc.seoul.kr"

# 실제 서울아산병원 진료과 코드 (hpCd)
AMC_DEPARTMENTS = {
    "D001": "소화기내과",
    "D002": "순환기내과",
    "D003": "호흡기내과",
    "D004": "혈액내과",
    "D005": "종양내과",
    "D006": "내분비내과",
    "D007": "류마티스내과",
    "D008": "감염내과",
    "D009": "신장내과",
    "D010": "알레르기내과",
    "D020": "일반외과",
    "D030": "흉부외과",
    "D035": "신경외과",
    "D038": "정형외과",
    "D040": "산부인과",
    "D045": "소아청소년과",
    "D050": "안과",
    "D055": "신경과",
    "D060": "정신건강의학과",
    "D065": "피부과",
    "D070": "비뇨의학과",
    "D075": "이비인후과",
    "D080": "재활의학과",
    "D085": "마취통증의학과",
    "D090": "영상의학과",
    "D095": "방사선종양학과",
    "D100": "진단검사의학과",
    "D105": "핵의학과",
    "D110": "병리과",
    "D115": "가정의학과",
    "D120": "응급의학과",
    "D125": "성형외과",
}

DAY_MAP = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}
TIME_SLOT_MAP = {"오전": "morning", "오후": "afternoon"}


class AsanCrawler:
    """서울아산병원 맞춤 크롤러"""

    def __init__(self):
        self.hospital_code = "AMC"
        self.hospital_name = "서울아산병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Referer": "https://www.amc.seoul.kr/asan/main.do",
        }

    async def _discover_departments(self) -> dict[str, str]:
        """사이트에서 실제 진료과 목록을 동적으로 수집"""
        dept_map = {}
        async with httpx.AsyncClient(headers=self.headers, timeout=20, follow_redirects=True) as client:
            try:
                resp = await client.get(f"{BASE_URL}/asan/departments/deptListTypeA.do")
                resp.raise_for_status()
                # <a href="...staffBaseInfoList.do?searchHpCd=D001"><img alt="소화기내과 소속 의료진정보" />
                matches = re.findall(
                    r'staffBaseInfoList\.do\?searchHpCd=(\w+)">\s*<img[^>]*alt="([^"]+)"',
                    resp.text,
                )
                for code, alt_text in matches:
                    name = re.sub(r"\s*소속.*", "", alt_text).strip()
                    if name and code not in dept_map:
                        dept_map[code] = name
                logger.info(f"[AMC] 사이트에서 {len(dept_map)}개 진료과 발견")
            except Exception as e:
                logger.error(f"[AMC] 진료과 동적 수집 실패: {e}")

        # 실패 시 하드코딩 폴백
        return dept_map if dept_map else AMC_DEPARTMENTS

    async def get_departments(self) -> list[dict]:
        """진료과 목록 반환 (사이트에서 동적 수집)"""
        dept_map = await self._discover_departments()
        return [{"code": k, "name": v} for k, v in sorted(dept_map.items())]

    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        """1차 경량 크롤링: 교수 이름 + ID 목록

        staffBaseInfoList.do 페이지에서 추출.
        fnDrDetail onclick에서 drEmpId, p.doctor_name에서 이름.
        """
        all_doctors = []

        # 진료과 목록 동적 수집
        all_depts = await self._discover_departments()

        targets = (
            {k: v for k, v in all_depts.items()
             if v == department or k == department}
            if department else all_depts
        )

        async with httpx.AsyncClient(headers=self.headers, timeout=20, follow_redirects=True) as client:
            for dept_code, dept_name in targets.items():
                url = f"{BASE_URL}/asan/staff/base/staffBaseInfoList.do?searchHpCd={dept_code}"
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    html = resp.text
                    soup = BeautifulSoup(html, "html.parser")

                    # 카드 기반 추출: li 안에 p.doctor_name + fnDrDetail
                    cards = soup.select("li:has(p.doctor_name)")
                    for card in cards:
                        name_el = card.select_one("p.doctor_name")
                        name = name_el.get_text(strip=True) if name_el else ""

                        # fnDrDetail에서 ID 추출
                        staff_id = ""
                        for a in card.select("a[onclick*=fnDrDetail]"):
                            m = re.search(r"fnDrDetail\('([A-Za-z0-9+/=]+)'", a.get("onclick", ""))
                            if m:
                                staff_id = m.group(1)
                                break

                        if not staff_id or not name:
                            continue

                        all_doctors.append({
                            "staff_id": staff_id,
                            "external_id": staff_id,
                            "name": name,
                            "department": dept_name,
                            "dept_code": dept_code,
                            "specialty": "",
                            "profile_url": f"{BASE_URL}/asan/staff/base/staffBaseInfoDetail.do?drEmpId={staff_id}&searchHpCd={dept_code}",
                        })

                    logger.info(f"[AMC] {dept_name}: {len(cards)}명 발견")

                except Exception as e:
                    logger.error(f"[AMC] {dept_name} 목록 크롤링 실패: {e}")

        return all_doctors

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """2차 상세 크롤링: 교수 상세 페이지에서 진료시간표 추출"""
        result = {
            "staff_id": staff_id,
            "name": "",
            "department": "",
            "position": "",
            "specialty": "",
            "profile_url": f"{BASE_URL}/asan/staff/base/staffBaseInfoDetail.do?drEmpId={staff_id}",
            "schedules": [],
        }

        async with httpx.AsyncClient(headers=self.headers, timeout=20, follow_redirects=True) as client:
            # 상세 페이지
            url = f"{BASE_URL}/asan/staff/base/staffBaseInfoDetail.do?drEmpId={staff_id}"
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")
                text = soup.get_text()

                # 이름 추출 - title에서 우선 (h3/h4가 "의료진" 등 잡음)
                title_tag = soup.find("title")
                if title_tag:
                    title_text = title_tag.get_text(strip=True)
                    # "김기봉 | 의료진 | ..." → "김기봉"
                    name_part = title_text.split("|")[0].strip()
                    nm = re.match(r"([가-힣]{2,4})", name_part)
                    if nm:
                        result["name"] = nm.group(1)

                if not result["name"]:
                    og = soup.find("meta", property="og:title")
                    if og and og.get("content"):
                        nm = re.match(r"([가-힣]{2,4})", og["content"])
                        if nm:
                            result["name"] = nm.group(1)

                # 전문분야
                spec_match = re.search(r"전문\s*분야[:\s]*([^\n<]{3,100})", text)
                if spec_match:
                    result["specialty"] = spec_match.group(1).strip()

                # 직위
                pos_match = re.search(r"(교수|부교수|조교수|임상강사|전임의)", text)
                if pos_match:
                    result["position"] = pos_match.group(1)

                # 진료과
                dept_match = re.search(r"진료과\s*([가-힣]+과)", text)
                if dept_match:
                    result["department"] = dept_match.group(1)

                # 진료시간표 추출
                result["schedules"] = self._parse_schedule_table(soup)

                # 테이블이 없으면 텍스트 패턴으로 폴백
                if not result["schedules"]:
                    result["schedules"] = self._parse_schedule_text(text)

            except Exception as e:
                logger.error(f"[AMC] {staff_id} 상세 크롤링 실패: {e}")

        logger.info(f"[AMC] {result['name']}({staff_id[:15]}...) → 일정 {len(result['schedules'])}개")
        return result

    def _parse_schedule_table(self, soup: BeautifulSoup) -> list[dict]:
        """AMC 진료시간표 파싱

        테이블 구조:
          헤더행1: 구분 | 질병/치료범위 | 예약방법 | 진료시간
          헤더행2: (병합)                           | 오전 | 오후
          데이터:  소화기내과 | ... | ... | 화,금, | 월,수,
        td.reservSchedule 셀에 "화,금," 형태로 요일이 들어있음
        """
        schedules = []
        time_ranges = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

        # 오전/오후 헤더 순서 파악
        headers = soup.select("th")
        slot_order = []
        for th in headers:
            text = th.get_text(strip=True)
            if text in TIME_SLOT_MAP:
                slot_order.append(TIME_SLOT_MAP[text])

        if not slot_order:
            slot_order = ["morning", "afternoon"]

        # reservSchedule 셀에서 요일 추출
        rows = soup.select("tr")
        for row in rows:
            cells = row.select("td.reservSchedule")
            if not cells:
                continue

            for i, cell in enumerate(cells):
                if i >= len(slot_order):
                    break
                slot = slot_order[i]
                text = cell.get_text(strip=True)
                if not text or text == "-":
                    continue

                for day_char in re.split(r"[,\s·]+", text):
                    day_char = day_char.strip()
                    dow = DAY_MAP.get(day_char)
                    if dow is not None:
                        start, end = time_ranges.get(slot, ("", ""))
                        schedules.append({
                            "day_of_week": dow,
                            "time_slot": slot,
                            "start_time": start,
                            "end_time": end,
                            "location": "",
                        })

        # 중복 제거
        seen = set()
        unique = []
        for s in schedules:
            key = (s["day_of_week"], s["time_slot"])
            if key not in seen:
                seen.add(key)
                unique.append(s)
        return unique

    def _parse_schedule_text(self, text: str) -> list[dict]:
        """텍스트에서 진료일정 패턴 추출 (테이블이 없는 경우)"""
        schedules = []
        time_ranges = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

        # "월(오전)" 패턴
        for m in re.findall(r"([월화수목금토일])\s*\(\s*(오전|오후)\s*\)", text):
            dow = DAY_MAP.get(m[0])
            slot = TIME_SLOT_MAP.get(m[1])
            if dow is not None and slot:
                start, end = time_ranges.get(slot, ("", ""))
                schedules.append({"day_of_week": dow, "time_slot": slot, "start_time": start, "end_time": end, "location": ""})

        # "월요일 오전" 패턴
        if not schedules:
            for m in re.findall(r"([월화수목금토일])요일?\s*(오전|오후)", text):
                dow = DAY_MAP.get(m[0])
                slot = TIME_SLOT_MAP.get(m[1])
                if dow is not None and slot:
                    start, end = time_ranges.get(slot, ("", ""))
                    schedules.append({"day_of_week": dow, "time_slot": slot, "start_time": start, "end_time": end, "location": ""})

        return schedules

    async def crawl_doctors(self, department: str = None):
        """전체 크롤링 (목록 + 상세)"""
        from app.schemas.schemas import CrawlResult, CrawledDoctor

        doc_list = await self.crawl_doctor_list(department)
        all_doctors = []

        for d in doc_list:
            try:
                detail = await self.crawl_doctor_schedule(d["staff_id"])
                all_doctors.append(CrawledDoctor(
                    name=detail.get("name") or d.get("name", ""),
                    department=detail.get("department") or d.get("department", ""),
                    position=detail.get("position", ""),
                    specialty=detail.get("specialty") or d.get("specialty", ""),
                    profile_url=detail.get("profile_url", ""),
                    external_id=d["staff_id"],
                    schedules=detail.get("schedules", []),
                ))
            except Exception as e:
                logger.error(f"[AMC] 교수 크롤링 실패 {d.get('name', '')}: {e}")

        return CrawlResult(
            hospital_code=self.hospital_code,
            hospital_name=self.hospital_name,
            status="success" if all_doctors else "partial",
            doctors=all_doctors,
            crawled_at=datetime.utcnow(),
        )
