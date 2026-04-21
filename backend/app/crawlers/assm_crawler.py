"""안성성모병원(ASSM) 크롤러

병원 공식명: 안성성모병원 (경기 안성시 서인동)
홈페이지: ansmc.co.kr/sm2018/ (PHP 정적 사이트, UTF-8)

구조:
- 진료과 페이지: `/sm2018/sub01/sub01_{NN}.php`
    NN 은 진료과별 고정 번호 (01=심장내과, 02=소화기내과, ...)
- 각 페이지:
    div.subcont_wrap → 페이지 상단에 진료과명 + 과 소개 텍스트
    div.doctor_wrap 여러 개 (과당 1~6명):
      div.img > img src="../images/sub01/doctor_{key}.jpg" → 의사 식별자
      div.cont > div.text01 "{이름} <span>{직책}</span>"
             > div.text02 "{전문의 과목 등}"
             > ul.text04 "전문분야 리스트"

※ 홈페이지에는 주간 진료시간표가 게시되어 있지 않다. notes 로 안내한다.

external_id 포맷: `ASSM-{dept_num}-{image_key}` (e.g. ASSM-01-jni)
개별 조회: 해당 과 페이지 1회 GET (rule #7 준수)
"""
from __future__ import annotations

import re
import asyncio
import logging
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "http://ansmc.co.kr"
DEPT_URL_FMT = f"{BASE_URL}/sm2018/sub01/sub01_{{num}}.php"

# 사이트 내비게이션에서 확인한 진료과 번호 ↔ 이름 매핑
DEPT_MAP: dict[str, str] = {
    "01": "심장내과",
    "02": "소화기내과",
    "03": "내과",
    "04": "신장내과",
    "05": "신경과",
    "06": "외과",
    "07": "정형외과",
    "08": "신경외과",
    "09": "비뇨의학과",
    "12": "직업환경의학과",
    "13": "영상의학과",
    "14": "마취통증의학과",
    "15": "응급의학과",
    "16": "가정의학과",
    "18": "진단검사의학과",
    "19": "내분비내과",
    "21": "산부인과",
}

_IMG_KEY_PAT = re.compile(r"/([A-Za-z0-9_]+)\.(?:jpg|png|jpeg)", re.I)
NOTES_NO_SCHEDULE = "※ 안성성모병원 홈페이지에는 교수별 주간 진료시간표가 공개되어 있지 않습니다. 외래 가능 시간은 병원(031-670-5114)에 직접 문의해 주세요."


class AssmCrawler:
    def __init__(self):
        self.hospital_code = "ASSM"
        self.hospital_name = "안성성모병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Referer": f"{BASE_URL}/sm2018/",
        }
        self._cached_data: list[dict] | None = None

    @staticmethod
    def _parse_dept_page(html: str, dept_num: str, dept_name: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        out: list[dict] = []
        for wrap in soup.select("div.doctor_wrap"):
            img = wrap.select_one("div.img img")
            img_src = img.get("src", "") if img else ""
            m = _IMG_KEY_PAT.search(img_src)
            if not m:
                # 이미지 없는 경우 텍스트에서 대체 키 생성
                continue
            key = m.group(1)

            t1 = wrap.select_one(".text01")
            name = ""
            position = ""
            if t1:
                span = t1.find("span")
                if span:
                    position = span.get_text(" ", strip=True)
                    span.extract()
                name = t1.get_text(" ", strip=True).replace(" ", "").strip()

            t2 = wrap.select_one(".text02")
            specialty_line = t2.get_text(" ", strip=True) if t2 else ""

            # 전문분야 상세 (ul.text04)
            interests = []
            for li in wrap.select("ul.text04 li"):
                line = li.get_text(" ", strip=True)
                if line:
                    interests.append(line)
            detail_specialty = " / ".join(interests) if interests else ""

            external_id = f"ASSM-{dept_num}-{key}"
            photo_url = img_src
            if photo_url.startswith("../"):
                photo_url = f"{BASE_URL}/sm2018/" + photo_url[3:]
            elif photo_url.startswith("/"):
                photo_url = f"{BASE_URL}{photo_url}"

            out.append({
                "staff_id": external_id,
                "external_id": external_id,
                "name": name,
                "department": dept_name,
                "position": position,
                "specialty": specialty_line + (f" — {detail_specialty}" if detail_specialty else ""),
                "profile_url": DEPT_URL_FMT.format(num=dept_num),
                "photo_url": photo_url,
                "notes": NOTES_NO_SCHEDULE,
                "schedules": [],
                "date_schedules": [],
            })
        return out

    async def _fetch_dept(self, client: httpx.AsyncClient, dept_num: str) -> list[dict]:
        url = DEPT_URL_FMT.format(num=dept_num)
        try:
            r = await client.get(url)
            r.raise_for_status()
        except Exception as e:
            logger.warning(f"[ASSM] 진료과 {dept_num} 실패: {e}")
            return []
        html = r.content.decode("utf-8", errors="replace")
        return self._parse_dept_page(html, dept_num, DEPT_MAP.get(dept_num, ""))

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        ) as client:
            sem = asyncio.Semaphore(4)

            async def bounded(n):
                async with sem:
                    return await self._fetch_dept(client, n)

            results = await asyncio.gather(*[bounded(n) for n in DEPT_MAP.keys()])

        doctors: list[dict] = []
        seen: set[str] = set()
        for docs in results:
            for d in docs:
                if d["external_id"] in seen:
                    continue
                seen.add(d["external_id"])
                doctors.append(d)

        self._cached_data = doctors
        logger.info(f"[ASSM] 총 {len(doctors)}명")
        return doctors

    # ─── 공개 인터페이스 ───

    async def get_departments(self) -> list[dict]:
        data = await self._fetch_all()
        depts = sorted({d["department"] for d in data if d["department"]})
        return [{"code": dn, "name": dn} for dn in depts]

    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        data = await self._fetch_all()
        if department:
            data = [d for d in data if department in d["department"]]
        return [
            {k: d[k] for k in ("staff_id", "external_id", "name", "department",
                                "position", "specialty", "profile_url", "notes")}
            for d in data
        ]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 조회 — 해당 과 페이지 1회만 GET (rule #7)"""
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }

        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return {k: d.get(k, "") if k not in ("schedules", "date_schedules")
                            else d.get(k, [])
                            for k in ("staff_id", "name", "department", "position",
                                     "specialty", "profile_url", "notes",
                                     "schedules", "date_schedules")}

        prefix = f"{self.hospital_code}-"
        if not staff_id.startswith(prefix):
            return empty
        rest = staff_id[len(prefix):]
        parts = rest.split("-", 1)
        if len(parts) != 2:
            return empty
        dept_num, img_key = parts
        if dept_num not in DEPT_MAP:
            return empty

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        ) as client:
            docs = await self._fetch_dept(client, dept_num)
        for d in docs:
            if d["external_id"] == staff_id:
                return {k: d.get(k, "") if k not in ("schedules", "date_schedules")
                        else d.get(k, [])
                        for k in ("staff_id", "name", "department", "position",
                                 "specialty", "profile_url", "notes",
                                 "schedules", "date_schedules")}
        return empty

    async def crawl_doctors(self, department: str = None):
        from app.schemas.schemas import CrawlResult, CrawledDoctor

        data = await self._fetch_all()
        if department:
            data = [d for d in data if department in d["department"]]

        doctors = [
            CrawledDoctor(
                name=d["name"],
                department=d["department"],
                position=d.get("position", ""),
                specialty=d.get("specialty", ""),
                profile_url=d.get("profile_url", ""),
                external_id=d["external_id"],
                notes=d.get("notes", ""),
                schedules=d["schedules"],
                date_schedules=d.get("date_schedules", []),
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
