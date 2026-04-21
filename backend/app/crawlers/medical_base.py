"""경기도의료원(medical.or.kr) 통합 사이트 베이스 크롤러

경기도의료원은 6개 병원(수원·의정부·파주·이천·안성·포천)이 동일한 www.medical.or.kr
플랫폼을 공유한다. 각 병원은 `site_gb` 파라미터로 구분되며, 진료과 목록과 의료진 상세는
XML AJAX API 로 제공된다.

공통 엔드포인트:
    POST /front/deptList.do   form={site_gb=XXX}
    POST /front/deptDetail.do form={site_gb=XXX, dept_id={idx}}

<dept_detail> 엘리먼트 내부는 HTML 엔터티 이스케이프된 HTML 조각이며
`html.unescape()` 후 BeautifulSoup 로 재파싱한다. common_table3 테이블의 thead 는
요일×(오전/오후) 헤더, tbody 각 행이 의사 1명이다. 셀에 "진료"/"검진"/"수술" 이
포함되면 해당 시간대 진료로 판정한다.

external_id 포맷: `{HOSPITAL_CODE}-{dept_idx}-{doc_no}`
개별 조회는 dept_idx 하나로 deptDetail.do 1회 호출 (rule #7 준수).
"""
from __future__ import annotations

import re
import logging
import html as htmllib
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://www.medical.or.kr"
DEPT_LIST_URL = f"{BASE_URL}/front/deptList.do"
DEPT_DETAIL_URL = f"{BASE_URL}/front/deptDetail.do"

TIME_RANGES = {"morning": ("09:00", "12:30"), "afternoon": ("13:30", "17:30")}
DAYS = ["월", "화", "수", "목", "금", "토", "일"]


def _unescape_embedded(xml_inner: str) -> str:
    return htmllib.unescape(xml_inner)


class MedicalOrKrBaseCrawler:
    """경기도의료원 공통 로직 베이스.

    서브클래스는 __init__ 에서 아래를 세팅한다:
        hospital_code    : 우리 시스템 코드 (e.g. "ICHEON")
        hospital_name    : 병원 정식 명칭
        site_gb          : medical.or.kr 의 site_gb 파라미터 (e.g. "ICHEON", "ANSUNG")
        site_path        : 홈페이지 서브 경로 (e.g. "icheon", "ansung") — profile_url 에 사용
    """

    hospital_code: str = ""
    hospital_name: str = ""
    site_gb: str = ""
    site_path: str = ""

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120",
            "Accept": "text/xml,application/xml,text/html;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Referer": f"{BASE_URL}/{self.site_path}/index.do",
            "X-Requested-With": "XMLHttpRequest",
        }
        self._cached_data: list[dict] | None = None

    # ─── 파싱 헬퍼 ───

    @staticmethod
    def _parse_schedule_table(dept_detail_html: str, doctor_name: str) -> list[dict]:
        if not dept_detail_html:
            return []
        soup = BeautifulSoup(dept_detail_html, "html.parser")
        tbl = soup.find("table", class_="common_table3")
        if not tbl:
            return []
        thead = tbl.find("thead")
        if not thead:
            return []
        trs = thead.find_all("tr")
        if len(trs) < 2:
            return []
        day_tr, slot_tr = trs[0], trs[1]
        day_list: list[int] = []
        for th in day_tr.find_all("th"):
            if th.get("rowspan"):
                continue
            txt = th.get_text(" ", strip=True)
            for idx, d in enumerate(DAYS):
                if d in txt:
                    day_list.append(idx)
                    break
        slot_list: list[str] = []
        for th in slot_tr.find_all("th"):
            t = th.get_text(" ", strip=True)
            if "오전" in t:
                slot_list.append("morning")
            elif "오후" in t:
                slot_list.append("afternoon")
            else:
                slot_list.append("")
        n_cells = len(slot_list)
        if n_cells == 0 or len(day_list) * 2 != n_cells:
            return []

        tbody = tbl.find("tbody")
        if not tbody:
            return []

        out: list[dict] = []
        for tr in tbody.find_all("tr"):
            th = tr.find("th")
            if not th:
                continue
            row_name = th.get_text(" ", strip=True)
            if doctor_name not in row_name and row_name not in doctor_name:
                continue
            tds = tr.find_all("td")
            if len(tds) < n_cells:
                continue
            for i, td in enumerate(tds[:n_cells]):
                text = td.get_text(" ", strip=True)
                if not text or text == "-" or "휴" in text:
                    continue
                has_btn = td.find("span", class_="medical_btn") is not None
                has_kw = any(k in text for k in ("진료", "검진", "수술"))
                if not has_btn and not has_kw:
                    continue
                day_idx = day_list[i // 2]
                slot = slot_list[i]
                if not slot:
                    continue
                s, e = TIME_RANGES[slot]
                out.append({
                    "day_of_week": day_idx, "time_slot": slot,
                    "start_time": s, "end_time": e, "location": "",
                })
            break
        return out

    def _parse_dept_list_xml(self, xml: str) -> list[dict]:
        soup = BeautifulSoup(xml, "xml") or BeautifulSoup(xml, "html.parser")
        out: list[dict] = []
        for node in soup.find_all("list"):
            idx = node.find("idx")
            nm = node.find("dept_nm")
            use = node.find("use_yn")
            if not idx or not nm:
                continue
            if use and use.get_text(strip=True) != "Y":
                continue
            out.append({"idx": idx.get_text(strip=True), "name": nm.get_text(strip=True)})
        return out

    def _parse_dept_detail_xml(self, xml: str, dept_idx: str, dept_name: str) -> list[dict]:
        soup = BeautifulSoup(xml, "xml") or BeautifulSoup(xml, "html.parser")
        doctors: list[dict] = []
        for node in soup.find_all("list"):
            name_el = node.find("doc_nm")
            no_el = node.find("doc_no")
            if not name_el or not no_el:
                continue
            name = name_el.get_text(strip=True)
            doc_no = no_el.get_text(strip=True)
            if not name or not doc_no:
                continue

            dept_detail = node.find("dept_detail")
            detail_html = _unescape_embedded(dept_detail.get_text()) if dept_detail else ""
            schedules = self._parse_schedule_table(detail_html, name)

            doc_career = node.find("doc_career")
            career_html = _unescape_embedded(doc_career.get_text()) if doc_career else ""
            position = ""
            career_soup = BeautifulSoup(career_html, "html.parser") if career_html else None
            if career_soup:
                first_p = career_soup.find("p")
                if first_p:
                    position = first_p.get_text(" ", strip=True)

            subj_el = node.find("doc_subject")
            subject = subj_el.get_text(strip=True) if subj_el else dept_name

            file_el = node.find("file_url")
            photo_url = ""
            if file_el:
                raw = file_el.get_text(strip=True)
                if raw:
                    photo_url = raw if raw.startswith("http") else f"{BASE_URL}{raw}"

            external_id = f"{self.hospital_code}-{dept_idx}-{doc_no}"
            notes = "" if schedules else "※ 진료시간표가 홈페이지에 게시되어 있지 않거나 파싱에 실패했습니다. 병원에 직접 문의해 주세요."
            doctors.append({
                "staff_id": external_id,
                "external_id": external_id,
                "_dept_idx": dept_idx,
                "_doc_no": doc_no,
                "name": name,
                "department": subject or dept_name,
                "position": position,
                "specialty": "",
                "profile_url": f"{BASE_URL}/{self.site_path}/index.do",
                "photo_url": photo_url,
                "notes": notes,
                "schedules": schedules,
                "date_schedules": [],
            })
        return doctors

    # ─── 네트워크 호출 ───

    async def _fetch_dept_list(self, client: httpx.AsyncClient) -> list[dict]:
        try:
            resp = await client.post(DEPT_LIST_URL, data={"site_gb": self.site_gb})
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[{self.hospital_code}] deptList 실패: {e}")
            return []
        xml = resp.content.decode("utf-8", errors="replace")
        return self._parse_dept_list_xml(xml)

    async def _fetch_dept_detail(self, client: httpx.AsyncClient, dept_idx: str, dept_name: str) -> list[dict]:
        try:
            resp = await client.post(
                DEPT_DETAIL_URL,
                data={"site_gb": self.site_gb, "dept_id": dept_idx},
            )
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[{self.hospital_code}] deptDetail {dept_idx} ({dept_name}) 실패: {e}")
            return []
        xml = resp.content.decode("utf-8", errors="replace")
        return self._parse_dept_detail_xml(xml, dept_idx, dept_name)

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        ) as client:
            depts = await self._fetch_dept_list(client)
            if not depts:
                self._cached_data = []
                return []
            logger.info(f"[{self.hospital_code}] 진료과 {len(depts)}개")

            doctors: list[dict] = []
            seen: set[str] = set()
            for dept in depts:
                docs = await self._fetch_dept_detail(client, dept["idx"], dept["name"])
                for d in docs:
                    if d["external_id"] in seen:
                        continue
                    seen.add(d["external_id"])
                    doctors.append(d)

        for d in doctors:
            d.pop("_dept_idx", None)
            d.pop("_doc_no", None)
        self._cached_data = doctors
        logger.info(f"[{self.hospital_code}] 총 {len(doctors)}명")
        return doctors

    # ─── 공개 인터페이스 ───

    async def get_departments(self) -> list[dict]:
        data = await self._fetch_all()
        depts = sorted({d["department"] for d in data if d["department"]})
        return [{"code": dn, "name": dn} for dn in depts]

    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]
        return [
            {k: d[k] for k in ("staff_id", "external_id", "name", "department",
                                "position", "specialty", "profile_url", "notes")}
            for d in data
        ]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 조회 — dept_idx 1 개로 해당 과 deptDetail.do 한 번만 호출 (rule #7)"""
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
        raw = staff_id.replace(prefix, "") if staff_id.startswith(prefix) else staff_id
        parts = raw.split("-", 1)
        if len(parts) != 2:
            return empty
        dept_idx, doc_no = parts
        if not dept_idx.isdigit():
            return empty

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        ) as client:
            docs = await self._fetch_dept_detail(client, dept_idx, "")
        target = next((d for d in docs if d.get("_doc_no") == doc_no), None)
        if not target:
            return empty
        return {
            "staff_id": staff_id,
            "name": target["name"],
            "department": target["department"],
            "position": target["position"],
            "specialty": target["specialty"],
            "profile_url": target["profile_url"],
            "notes": target["notes"],
            "schedules": target["schedules"],
            "date_schedules": target["date_schedules"],
        }

    async def crawl_doctors(self, department: str = None):
        from app.schemas.schemas import CrawlResult, CrawledDoctor

        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]

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
