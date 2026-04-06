"""서울대학교병원 크롤러

전체 진료일정표 페이지 하나로 교수 목록 + 진료시간 전부 추출.
URL: https://www.snuh.org/allSchedulePopup.do

테이블 구조:
  병원 | 과 | 의사명 | 월 | 화 | 수 | 목 | 금 | 토 | 전문 분야 | 전화
  일정 셀: "전오전진료", "후오후진료", "전후전일진료" 등
"""
import re
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

DAY_MAP = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5}
TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

SCHEDULE_BASE = "https://www.snuh.org/allSchedulePopup.do"
# 본원, 어린이병원, 암병원
HSP_CODES = {"1": "본원", "2": "어린이병원", "G": "암병원"}
DEPT_SUFFIX = re.compile(r"분과명을\s*클릭.*$")


def _parse_day_cell(text: str) -> list[str]:
    """일정 셀 텍스트에서 오전/오후 슬롯 추출.

    패턴:
      "전오전진료" → ["morning"]
      "후오후진료" → ["afternoon"]
      "전후전일진료" → ["morning", "afternoon"]
      "전 C오전클리닉" → ["morning"]
      "" → []
    """
    if not text:
        return []
    slots = []
    if "전" in text and ("오전" in text or text.startswith("전")):
        slots.append("morning")
    if "후" in text and ("오후" in text or "전후" in text or "후" in text):
        slots.append("afternoon")
    # "전후전일진료" 같은 경우
    if "전일" in text and "morning" not in slots:
        slots.append("morning")
    if "전일" in text and "afternoon" not in slots:
        slots.append("afternoon")
    # 단순히 "전" 또는 "후"만 있는 경우
    if not slots and text:
        if text.startswith("전"):
            slots.append("morning")
        elif text.startswith("후"):
            slots.append("afternoon")
    return slots


class SnuhCrawler:
    """서울대학교병원 크롤러"""

    def __init__(self):
        self.hospital_code = "SNUH"
        self.hospital_name = "서울대학교병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        self._cached_data = None  # 파싱 결과 캐시

    async def _fetch_all(self) -> list[dict]:
        """본원+어린이병원+암병원 전체 일정표를 파싱"""
        if self._cached_data is not None:
            return self._cached_data

        # 이름 기준으로 병합하기 위한 dict
        merged = {}  # name -> doctor dict

        async with httpx.AsyncClient(headers=self.headers, timeout=30, follow_redirects=True) as client:
            for hsp_cd, hsp_name in HSP_CODES.items():
                try:
                    resp = await client.get(f"{SCHEDULE_BASE}?hsp_cd={hsp_cd}")
                    resp.raise_for_status()
                    soup = BeautifulSoup(resp.text, "html.parser")

                    rows = soup.select("table tr")
                    count = 0
                    for row in rows[1:]:
                        cells = row.select("td")
                        if len(cells) < 10:
                            continue

                        # 테이블 구조가 병원마다 다름:
                        #   암병원(11칸): 센터 | 과 | 의사 | 월~토 | 전문 | 전화
                        #   본원/어린이(10칸): 과(colspan=2) | 의사 | 월~토 | 전문 | 전화
                        has_colspan = cells[0].get("colspan") is not None
                        if has_colspan:
                            # 본원/어린이: td[0]=과(colspan2), td[1]=의사, td[2~7]=월~토, td[8]=전문
                            dept_idx, name_idx, day_start, spec_idx = 0, 1, 2, 8
                        else:
                            # 암병원: td[0]=센터, td[1]=과, td[2]=의사, td[3~8]=월~토, td[9]=전문
                            dept_idx, name_idx, day_start, spec_idx = 1, 2, 3, 9

                        # 진료과 — "분과명을 클릭 시..." 제거
                        dept_raw = cells[dept_idx].get_text(strip=True)
                        department = DEPT_SUFFIX.sub("", dept_raw).strip()

                        # 의사명 — "의사명을 클릭 시..." 제거
                        doc_raw = cells[name_idx].get_text(strip=True)
                        name = re.sub(r"의사명을?\s*클릭.*$", "", doc_raw).strip()
                        doc_links = cells[name_idx].select("a")
                        for a in doc_links:
                            a_text = a.get_text(strip=True)
                            if a_text and len(a_text) <= 10:
                                name = a_text
                                break

                        if not name:
                            continue

                        # 월~토 일정
                        schedules = []
                        day_names = ["월", "화", "수", "목", "금", "토"]
                        for i, day_name in enumerate(day_names):
                            cell_idx = day_start + i
                            if cell_idx >= len(cells):
                                break
                            text = cells[cell_idx].get_text(strip=True)
                            slots = _parse_day_cell(text)
                            dow = DAY_MAP[day_name]
                            for slot in slots:
                                start, end = TIME_RANGES.get(slot, ("", ""))
                                schedules.append({
                                    "day_of_week": dow,
                                    "time_slot": slot,
                                    "start_time": start,
                                    "end_time": end,
                                    "location": hsp_name,
                                })

                        # 전문분야
                        specialty = cells[spec_idx].get_text(strip=True) if len(cells) > spec_idx else ""

                        # 같은 이름의 교수가 이미 있으면 병합
                        if name in merged:
                            doc = merged[name]
                            # 일정 추가 (중복 제거)
                            existing_keys = {(s["day_of_week"], s["time_slot"], s["location"]) for s in doc["schedules"]}
                            for s in schedules:
                                key = (s["day_of_week"], s["time_slot"], s["location"])
                                if key not in existing_keys:
                                    doc["schedules"].append(s)
                                    existing_keys.add(key)
                            # 진료 장소 추가
                            if hsp_name not in doc["locations"]:
                                doc["locations"].append(hsp_name)
                            # 진료과 추가
                            if department and department not in doc["departments"]:
                                doc["departments"].append(department)
                            # 전문분야 병합
                            if specialty and specialty not in doc["specialty"]:
                                doc["specialty"] = f"{doc['specialty']}, {specialty}" if doc["specialty"] else specialty
                        else:
                            merged[name] = {
                                "name": name,
                                "department": department,
                                "departments": [department] if department else [],
                                "locations": [hsp_name],
                                "specialty": specialty,
                                "profile_url": "",
                                "schedules": schedules,
                            }
                        count += 1

                    logger.info(f"[SNUH] {hsp_name}(hsp_cd={hsp_cd}): {count}행")

                except Exception as e:
                    logger.error(f"[SNUH] {hsp_name} 크롤링 실패: {e}")

        # merged → list 변환
        all_doctors = []
        for name, doc in merged.items():
            ext_id = f"SNUH-{name}"
            # 특이사항 생성: 여러 장소에서 진료하는 경우
            notes = ""
            if len(doc["locations"]) > 1:
                lines = []
                for loc in doc["locations"]:
                    loc_schedules = [s for s in doc["schedules"] if s["location"] == loc]
                    if loc_schedules:
                        day_slots = []
                        for s in loc_schedules:
                            day = ["월","화","수","목","금","토"][s["day_of_week"]] if s["day_of_week"] < 6 else "?"
                            slot = "오전" if s["time_slot"] == "morning" else "오후"
                            day_slots.append(f"{day} {slot}")
                        lines.append(f"{loc}: {', '.join(day_slots)}")
                notes = "\n".join(lines)

            all_doctors.append({
                "staff_id": ext_id,
                "external_id": ext_id,
                "name": name,
                "department": doc["department"],
                "specialty": doc["specialty"],
                "profile_url": "",
                "schedules": doc["schedules"],
                "notes": notes,
            })

        logger.info(f"[SNUH] 총 {len(all_doctors)}명 (병합 후)")
        self._cached_data = all_doctors
        return all_doctors

    async def get_departments(self) -> list[dict]:
        """진료과 목록 반환"""
        data = await self._fetch_all()
        depts = {}
        for d in data:
            dept = d["department"]
            if dept and dept not in depts:
                depts[dept] = dept
        return [{"code": name, "name": name} for name in sorted(depts.keys())]

    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        """교수 목록 (일정 포함)"""
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]
        # 목록용으로는 schedules 제외
        return [
            {
                "staff_id": d["staff_id"],
                "external_id": d["external_id"],
                "name": d["name"],
                "department": d["department"],
                "specialty": d["specialty"],
                "profile_url": d["profile_url"],
                "notes": d.get("notes", ""),
            }
            for d in data
        ]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 교수 진료시간 조회 (캐시된 데이터에서)"""
        data = await self._fetch_all()
        # 정확한 ID 매칭
        for d in data:
            if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                return self._doctor_schedule_dict(d)
        # 폴백: SNUH-...-이름 형식에서 이름 추출하여 매칭
        if staff_id.startswith("SNUH-"):
            name = staff_id.split("-")[-1]
            for d in data:
                if d["name"] == name:
                    return self._doctor_schedule_dict(d)
        return {"staff_id": staff_id, "name": "", "department": "", "position": "",
                "specialty": "", "profile_url": "", "notes": "", "schedules": []}

    @staticmethod
    def _doctor_schedule_dict(d: dict) -> dict:
        return {
            "staff_id": d["staff_id"],
            "name": d["name"],
            "department": d["department"],
            "position": "",
            "specialty": d["specialty"],
            "profile_url": d["profile_url"],
            "notes": d.get("notes", ""),
            "schedules": d["schedules"],
        }

    async def crawl_doctors(self, department: str = None):
        """전체 크롤링 (CrawlResult 반환)"""
        from app.schemas.schemas import CrawlResult, CrawledDoctor

        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]

        doctors = [
            CrawledDoctor(
                name=d["name"],
                department=d["department"],
                specialty=d["specialty"],
                profile_url=d["profile_url"],
                external_id=d["external_id"],
                notes=d.get("notes", ""),
                schedules=d["schedules"],
            )
            for d in data
        ]

        return CrawlResult(
            hospital_code=self.hospital_code,
            hospital_name=self.hospital_name,
            status="success" if doctors else "partial",
            doctors=doctors,
            crawled_at=datetime.utcnow(),
        )
