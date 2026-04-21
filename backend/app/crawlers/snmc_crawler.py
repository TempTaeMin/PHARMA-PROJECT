"""서울특별시 서남병원(SNMC) 크롤러

병원 공식명: 서울특별시 서남병원 (서울 양천구 신정로)
홈페이지: seoulsnh.or.kr (ASP, 정적 HTML, EUC-KR)

구조:
- 진료과: GET `/medical/medical01.asp?AC_F=3&AC_S=1`
    각 과 링크: `/dept/clinic_01.asp?AC_F=3&AC_S=1&m_code={N}` — img alt="{과이름}"
- 의사 목록 + 스케줄: GET `/dept/clinic_02.asp?AC_F=3&AC_S=1&m_code={N}`
    table.time_table 안:
      의사당 2 개 tr (rowspan=2 로 묶인 이름 셀)
      row1: [이름셀 rowspan=2, "오전", 월, 화, 수, 목, 금, 토, 비고셀, 전문분야 rowspan=2]
      row2: ["오후", 월, 화, 수, 목, 금, 토]
    시간 cell: `<img src="/images/img_out.png" alt="외래진료">` 또는 img_blue_c("검진")/img_special("특수클리닉") 존재 시 진료
- 의사 개인 프로필: GET `/dept/popup_doc.asp?d_code={N}&m_code={N}`
    ul li 2개 = 이름, 직책; span.con = 전문분야

external_id: SNMC-{d_code}-{m_code}  (d_code 혼자로는 타 과 중복 우려)

개별 조회: external_id 에서 (d_code, m_code) 파싱 → clinic_02.asp?m_code={M} + popup_doc.asp?d_code={D}&m_code={M}
두 개 페이지만 GET (해당 과 전체 의사 목록이지만 페이지 1 개로 끝남)
"""
from __future__ import annotations

import re
import logging
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "http://www.seoulsnh.or.kr"
DEPT_URL = f"{BASE_URL}/medical/medical01.asp?AC_F=3&AC_S=1"

TIME_RANGES = {"morning": ("09:00", "12:30"), "afternoon": ("13:30", "17:30")}
_MCODE_PAT = re.compile(r"m_code=(\d+)")
_DCODE_PAT = re.compile(r"d_code=(\d+)")


class SnmcCrawler:
    def __init__(self):
        self.hospital_code = "SNMC"
        self.hospital_name = "서울특별시 서남병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Referer": f"{BASE_URL}/",
        }
        self._cached_data: list[dict] | None = None
        self._dept_map: dict[str, str] | None = None  # m_code → dept name

    @staticmethod
    def _decode(resp: httpx.Response) -> str:
        """EUC-KR 응답을 안전하게 유니코드로 디코딩"""
        return resp.content.decode("euc-kr", errors="replace")

    async def _fetch_dept_map(self, client: httpx.AsyncClient) -> dict[str, str]:
        if self._dept_map is not None:
            return self._dept_map
        try:
            resp = await client.get(DEPT_URL)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[SNMC] dept list 실패: {e}")
            return {}
        html = self._decode(resp)
        soup = BeautifulSoup(html, "html.parser")
        out: dict[str, str] = {}
        for a in soup.find_all("a", href=True):
            m = _MCODE_PAT.search(a["href"])
            if not m:
                continue
            img = a.find("img")
            if not img or not img.get("alt"):
                continue
            m_code = m.group(1)
            dept = img["alt"].strip()
            if m_code and dept and m_code not in out:
                out[m_code] = dept
        self._dept_map = out
        logger.info(f"[SNMC] 진료과 {len(out)}개")
        return out

    def _parse_schedule_cells(self, tds, slot: str) -> list[dict]:
        """6개 요일 셀 → schedules. 각 셀에 <img>가 있으면 진료 (휴진은 &nbsp;)"""
        from app.crawlers._schedule_rules import find_exclude_keyword
        out: list[dict] = []
        for dow, td in enumerate(tds[:6]):
            img = td.find("img")
            if not img:
                continue
            alt = (img.get("alt") or "").strip()
            if "휴" in alt:
                continue
            if find_exclude_keyword(alt):
                continue
            s, e = TIME_RANGES[slot]
            out.append({
                "day_of_week": dow, "time_slot": slot,
                "start_time": s, "end_time": e,
                "location": alt if alt and alt not in ("외래진료",) else "",
            })
        return out

    def _parse_clinic_page(self, html: str, m_code: str, dept: str) -> list[dict]:
        """clinic_02.asp 페이지에서 의사 + 스케줄 추출"""
        soup = BeautifulSoup(html, "html.parser")
        tbl = soup.select_one("table.time_table")
        if not tbl:
            return []

        out: list[dict] = []
        tbody = tbl.find("tbody") or tbl
        trs = tbody.find_all("tr")

        # rowspan=2 인 이름 셀이 나오는 tr 를 앵커로 잡는다.
        i = 0
        while i < len(trs):
            tr1 = trs[i]
            tds1 = tr1.find_all("td")
            if not tds1:
                i += 1
                continue
            name_td = tds1[0]
            name_rowspan = name_td.get("rowspan", "1")
            if str(name_rowspan) != "2":
                i += 1
                continue

            # popup_doc 링크에서 d_code 추출 + 이름 텍스트
            link = name_td.find("a", href=_DCODE_PAT)
            if not link:
                i += 1
                continue
            m = _DCODE_PAT.search(link["href"])
            if not m:
                i += 1
                continue
            d_code = m.group(1)
            # 이름: 링크 텍스트에서 한글만 추출 (앞뒤에 &nbsp; 나 img alt 섞임)
            name_text = name_td.get_text(" ", strip=True)
            name_match = re.search(r"([가-힣]{2,4})", name_text)
            name = name_match.group(1) if name_match else ""
            if not name:
                i += 1
                continue

            # row1 슬롯 라벨 (tds1[1])
            slot1 = None
            if len(tds1) >= 2:
                lbl = tds1[1].get_text(" ", strip=True)
                if "오전" in lbl:
                    slot1 = "morning"
                elif "오후" in lbl:
                    slot1 = "afternoon"
            # row1 의 시간 셀 (tds1[2:8])
            schedules: list[dict] = []
            if slot1 and len(tds1) >= 8:
                schedules.extend(self._parse_schedule_cells(tds1[2:8], slot1))

            # 전문분야 (마지막 rowspan=2 셀의 텍스트)
            specialty = ""
            for td in tds1[-3:]:
                if td.get("rowspan") == "2" and td is not name_td:
                    txt = td.get_text(" ", strip=True)
                    if txt and len(txt) >= 2 and not re.fullmatch(r"[\s&]+", txt):
                        specialty = txt
                        break

            # row2 처리
            if i + 1 < len(trs):
                tr2 = trs[i + 1]
                tds2 = tr2.find_all("td")
                if tds2:
                    lbl2 = tds2[0].get_text(" ", strip=True)
                    slot2 = "morning" if "오전" in lbl2 else (
                        "afternoon" if "오후" in lbl2 else None)
                    if slot2 and len(tds2) >= 7:
                        schedules.extend(self._parse_schedule_cells(tds2[1:7], slot2))

            external_id = f"{self.hospital_code}-{d_code}-{m_code}"
            out.append({
                "staff_id": external_id,
                "external_id": external_id,
                "_d_code": d_code,
                "_m_code": m_code,
                "name": name,
                "department": dept,
                "position": "",
                "specialty": specialty,
                "profile_url": f"{BASE_URL}/dept/popup_doc.asp?d_code={d_code}&m_code={m_code}",
                "notes": "",
                "schedules": schedules,
                "date_schedules": [],
            })
            i += 2  # 두 행 한 의사
        return out

    async def _fetch_dept_doctors(self, client: httpx.AsyncClient, m_code: str, dept: str) -> list[dict]:
        url = f"{BASE_URL}/dept/clinic_02.asp?AC_F=3&AC_S=1&m_code={m_code}"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[SNMC] m_code={m_code} ({dept}) 실패: {e}")
            return []
        html = self._decode(resp)
        return self._parse_clinic_page(html, m_code, dept)

    async def _fetch_popup_info(self, client: httpx.AsyncClient, d_code: str, m_code: str) -> dict:
        """popup_doc.asp 에서 이름/직책/전문분야 보강"""
        url = f"{BASE_URL}/dept/popup_doc.asp?d_code={d_code}&m_code={m_code}"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[SNMC] popup {d_code}/{m_code} 실패: {e}")
            return {}
        html = self._decode(resp)
        soup = BeautifulSoup(html, "html.parser")
        first = soup.find("div", class_="first")
        if not first:
            return {}
        info_ul = first.find("ul")
        name, position, specialty = "", "", ""
        if info_ul:
            lis = info_ul.find_all("li")
            if len(lis) >= 1:
                t = lis[0].get_text(" ", strip=True)
                m = re.search(r"([가-힣]{2,4})", t)
                if m:
                    name = m.group(1)
            if len(lis) >= 2:
                t = lis[1].get_text(" ", strip=True)
                # 이름 다음에 직책만 추출 (한글 제외 불필요, 전체 텍스트 중 img alt "직위" 뒤 텍스트)
                # img alt="직위" 다음에 텍스트가 붙는 형태
                imgs = lis[1].find_all("img")
                position = t
                for im in imgs:
                    al = im.get("alt", "")
                    if al and al in t:
                        position = position.replace(al, "", 1).strip()
            # specialty
            spec_span = info_ul.find("span", class_="con")
            if spec_span:
                specialty = spec_span.get_text(" ", strip=True)
        return {"name": name, "position": position, "specialty": specialty}

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True,
        ) as client:
            dept_map = await self._fetch_dept_map(client)
            if not dept_map:
                logger.error("[SNMC] 진료과 비어있음")
                self._cached_data = []
                return []

            doctors: list[dict] = []
            seen: set[str] = set()
            for m_code, dept in dept_map.items():
                docs = await self._fetch_dept_doctors(client, m_code, dept)
                for d in docs:
                    if d["external_id"] in seen:
                        continue
                    seen.add(d["external_id"])
                    doctors.append(d)
                logger.info(f"[SNMC] {dept} (m_code={m_code}): {len(docs)}명")

            # position 은 popup_doc 호출이 필요하지만 의사 수가 적고 rule #7 취지상 건너뛴다.
            # 필요 시 _fetch_popup_info 를 추가로 호출. 여기서는 목록 페이지 기반 정보만 사용.

        for d in doctors:
            d.pop("_d_code", None)
            d.pop("_m_code", None)
        self._cached_data = doctors
        logger.info(f"[SNMC] 총 {len(doctors)}명")
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
        """개별 조회 — external_id 에서 (d_code, m_code) 파싱 후 해당 과 페이지만 GET.

        rule #7 준수: 1개 진료과 페이지(clinic_02.asp) + 1개 프로필(popup_doc.asp) GET 만 발생.
        """
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
        parts = raw.split("-")
        if len(parts) != 2:
            return empty
        d_code, m_code = parts
        if not d_code.isdigit() or not m_code.isdigit():
            return empty

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True,
        ) as client:
            dept_map = await self._fetch_dept_map(client)
            dept = dept_map.get(m_code, "")
            docs = await self._fetch_dept_doctors(client, m_code, dept)
            matched = next((d for d in docs if d.get("_d_code") == d_code), None)
            popup = await self._fetch_popup_info(client, d_code, m_code)

        if not matched and not popup:
            return empty

        name = (matched.get("name") if matched else "") or popup.get("name", "")
        position = popup.get("position", "")
        specialty = (matched.get("specialty") if matched else "") or popup.get("specialty", "")
        schedules = matched.get("schedules", []) if matched else []

        return {
            "staff_id": staff_id,
            "name": name,
            "department": dept,
            "position": position,
            "specialty": specialty,
            "profile_url": f"{BASE_URL}/dept/popup_doc.asp?d_code={d_code}&m_code={m_code}",
            "notes": "",
            "schedules": schedules,
            "date_schedules": [],
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
