"""한림대의료원 공용 베이스 크롤러

한림대 계열 3개 병원이 동일한 ASP 템플릿(`hallymuniv_sub.asp`)을 공유한다:
  - 한림성심 (HALLYM): https://hallym.hallym.or.kr
  - 강남성심 (HALLYMKN): https://kangnam.hallym.or.kr
  - 한강성심 (HALLYMHG): https://hangang.hallym.or.kr

엔드포인트:
  진료과: /hallymuniv_sub.asp?left_menu=left_ireserve&screen=ptm211
  의사 목록: /hallymuniv_sub.asp?left_menu=left_ireserve&screen=ptm212&scode={code}&stype=OS
  의사 프로필+스케줄: /ptm207.asp?Doctor_Id={id}

external_id 포맷: {HOSPITAL_CODE}-{Doctor_Id}
"""
import re
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}
DAY_CHAR_MAP = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5}


class HallymBaseCrawler:
    """한림대의료원 계열 공용 크롤러.

    서브클래스는 `__init__`에서 hospital_code, hospital_name, base_url을 주입한다.
    선택적으로 `fallback_depts` 하드코딩 리스트를 제공하면 진료과 파싱 실패 시 사용.
    """

    def __init__(
        self,
        *,
        hospital_code: str,
        hospital_name: str,
        base_url: str,
        fallback_depts: list[tuple[str, str, str]] | None = None,
    ):
        self.hospital_code = hospital_code
        self.hospital_name = hospital_name
        self.base_url = base_url.rstrip("/")
        self._fallback_depts = fallback_depts or []
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Referer": self.base_url,
        }
        self._cached_data = None
        self._cached_depts = None

    # ─── 진료과 목록 ───

    async def _fetch_departments(self) -> list[dict]:
        if self._cached_depts is not None:
            return self._cached_depts

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True,
        ) as client:
            try:
                resp = await client.get(
                    f"{self.base_url}/hallymuniv_sub.asp",
                    params={"left_menu": "left_ireserve", "screen": "ptm211"},
                )
                resp.raise_for_status()
                resp.encoding = "euc-kr"
                soup = BeautifulSoup(resp.text, "html.parser")

                depts: list[dict] = []
                seen: set[str] = set()

                for a_tag in soup.select("a[href*='ptm212']"):
                    href = a_tag.get("href", "")
                    name = a_tag.get_text(strip=True)
                    m_code = re.search(r"scode=([^&\s\"']+)", href)
                    m_type = re.search(r"stype=([^&\s\"']+)", href)
                    if m_code and name:
                        code = m_code.group(1).strip()
                        stype = m_type.group(1).strip() if m_type else "OS"
                        if code not in seen:
                            seen.add(code)
                            clean_name = re.sub(r"\s+", " ", name).strip()
                            if clean_name:
                                depts.append({"code": code, "name": clean_name, "stype": stype})

                if not depts and self._fallback_depts:
                    depts = [
                        {"code": c, "name": n, "stype": s}
                        for c, n, s in self._fallback_depts
                    ]

                logger.info(f"[{self.hospital_code}] 진료과 {len(depts)}개")
                self._cached_depts = depts
                return depts
            except Exception as e:
                logger.error(f"[{self.hospital_code}] 진료과 목록 실패: {e}")
                self._cached_depts = []
                return []

    # ─── 진료과별 의사 목록 ───

    async def _fetch_dept_doctors(
        self, client: httpx.AsyncClient, dept_code: str, dept_name: str, stype: str = "OS"
    ) -> list[dict]:
        try:
            resp = await client.get(
                f"{self.base_url}/hallymuniv_sub.asp",
                params={
                    "left_menu": "left_ireserve",
                    "screen": "ptm212",
                    "scode": dept_code,
                    "stype": stype,
                },
            )
            resp.raise_for_status()
            resp.encoding = "euc-kr"
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            logger.error(f"[{self.hospital_code}] {dept_name} 의사 목록 실패: {e}")
            return []

        doctors: list[dict] = []
        seen: set[str] = set()

        for a_tag in soup.select("a[href*='ptm207']"):
            href = a_tag.get("href", "")
            m = re.search(r"Doctor_Id=(\d+)", href)
            if not m:
                continue
            dr_id = m.group(1)
            if dr_id in seen:
                continue

            raw_name = a_tag.get_text(strip=True)
            name = re.sub(r"\s*(교수|전문의|과장|원장|의사)?\s*상세\s*보기.*$", "", raw_name).strip()
            if not name or name in ("상세보기", "자세히보기", "상세정보") or len(name) > 15:
                parent = a_tag.parent
                if parent:
                    for el in parent.select("strong, span, b, em"):
                        t = el.get_text(strip=True)
                        if t and len(t) <= 10 and t not in ("상세보기", "자세히보기"):
                            name = t
                            break
                if not name or name in ("상세보기", "자세히보기", "상세정보") or len(name) > 15:
                    name = ""

            seen.add(dr_id)

            specialty = ""
            parent = a_tag.parent
            if parent:
                full_text = parent.get_text(separator="|", strip=True)
                parts = [p.strip() for p in full_text.split("|") if p.strip()]
                for p in parts:
                    if p != name and p not in ("상세보기", "예약하기") and len(p) > 3:
                        specialty = p
                        break

            doctors.append({
                "dr_id": dr_id,
                "name": name,
                "department": dept_name,
                "position": "",
                "specialty": specialty,
            })

        if not doctors:
            html = str(soup)
            for m in re.finditer(r"Doctor_Id=(\d+)", html):
                dr_id = m.group(1)
                if dr_id not in seen:
                    seen.add(dr_id)
                    doctors.append({
                        "dr_id": dr_id,
                        "name": "",
                        "department": dept_name,
                        "position": "",
                        "specialty": "",
                    })

        logger.info(f"[{self.hospital_code}] {dept_name}: {len(doctors)}명")
        return doctors

    # ─── 의사 프로필 + 스케줄 ───

    async def _fetch_doctor_profile(
        self, client: httpx.AsyncClient, dr_id: str
    ) -> tuple[dict, list[dict]]:
        info = {"name": "", "department": "", "position": "", "specialty": ""}
        schedules: list[dict] = []

        try:
            resp = await client.get(
                f"{self.base_url}/ptm207.asp",
                params={"Doctor_Id": dr_id},
            )
            resp.raise_for_status()
            resp.encoding = "euc-kr"
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            logger.error(f"[{self.hospital_code}] 프로필 조회 실패 (Doctor_Id={dr_id}): {e}")
            return info, schedules

        page_text = soup.get_text()
        if "잘못된 접근" in page_text:
            return info, schedules

        for sel in ("h2", "h3", "h4", "strong.name", "span.name", ".doctor-name"):
            el = soup.select_one(sel)
            if el:
                name = el.get_text(strip=True)
                if name and len(name) <= 10:
                    info["name"] = name
                    break

        for dt in soup.select("dt, th"):
            text = dt.get_text(strip=True)
            dd = dt.find_next_sibling("dd") or dt.find_next_sibling("td")
            if not dd:
                continue
            val = dd.get_text(strip=True)
            if "진료과" in text or "과명" in text:
                info["department"] = val
            elif "직위" in text or "직급" in text:
                info["position"] = val
            elif "전문" in text or "진료분야" in text:
                info["specialty"] = val

        schedules = self._parse_schedule_table(soup)
        return info, schedules

    @staticmethod
    def _parse_schedule_table(soup) -> list[dict]:
        schedules: list[dict] = []
        seen: set[tuple[int, str]] = set()

        for table in soup.select("table"):
            col_to_dow: dict[int, int] = {}
            header_row = table.select_one("thead tr") or table.select_one("tr")
            if not header_row:
                continue
            header_cells = header_row.select("th, td")
            for ci, cell in enumerate(header_cells):
                text = cell.get_text(strip=True)
                for char, dow in DAY_CHAR_MAP.items():
                    if char in text:
                        col_to_dow[ci] = dow
                        break
            if not col_to_dow:
                continue

            rows = table.select("tbody tr") or table.select("tr")[1:]
            for row in rows:
                cells = row.select("th, td")
                if not cells:
                    continue
                first_text = cells[0].get_text(strip=True)
                if "오전" in first_text:
                    slot = "morning"
                elif "오후" in first_text:
                    slot = "afternoon"
                else:
                    continue

                for ci, cell in enumerate(cells):
                    if ci not in col_to_dow:
                        continue
                    dow = col_to_dow[ci]
                    cell_text = cell.get_text(strip=True)
                    has = bool(cell_text and cell_text not in ("-", "X", "x", "휴진", ""))
                    if "진료" in cell_text:
                        has = True
                    if not has:
                        has = bool(cell.select("img, i, span.on, span.active"))
                    if not has:
                        cell_classes = " ".join(cell.get("class", []))
                        has = "on" in cell_classes or "active" in cell_classes
                    if has:
                        key = (dow, slot)
                        if key not in seen:
                            seen.add(key)
                            start, end = TIME_RANGES[slot]
                            schedules.append({
                                "day_of_week": dow,
                                "time_slot": slot,
                                "start_time": start,
                                "end_time": end,
                                "location": "",
                            })
        return schedules

    # ─── 전체 크롤링 ───

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        depts = await self._fetch_departments()
        all_doctors: dict[str, dict] = {}

        async with httpx.AsyncClient(
            headers=self.headers, timeout=60, follow_redirects=True,
        ) as client:
            for dept in depts:
                stype = dept.get("stype", "OS")
                docs = await self._fetch_dept_doctors(client, dept["code"], dept["name"], stype)
                for doc in docs:
                    dr_id = doc["dr_id"]
                    if dr_id in all_doctors:
                        existing = all_doctors[dr_id]
                        if doc["specialty"] and doc["specialty"] not in existing["specialty"]:
                            existing["specialty"] = (
                                f"{existing['specialty']}, {doc['specialty']}"
                                if existing["specialty"] else doc["specialty"]
                            )
                        continue

                    profile_info, schedules = await self._fetch_doctor_profile(client, dr_id)
                    name = doc["name"] or profile_info.get("name", "")
                    department = doc["department"] or profile_info.get("department", "")
                    position = doc["position"] or profile_info.get("position", "")
                    specialty = doc["specialty"] or profile_info.get("specialty", "")
                    ext_id = f"{self.hospital_code}-{dr_id}"

                    all_doctors[dr_id] = {
                        "staff_id": ext_id,
                        "external_id": ext_id,
                        "name": name,
                        "department": department,
                        "position": position,
                        "specialty": specialty,
                        "profile_url": f"{self.base_url}/ptm207.asp?Doctor_Id={dr_id}",
                        "notes": "",
                        "schedules": schedules,
                    }

        result = list(all_doctors.values())
        logger.info(f"[{self.hospital_code}] 총 {len(result)}명")
        self._cached_data = result
        return result

    # ─── 공개 인터페이스 ───

    async def get_departments(self) -> list[dict]:
        depts = await self._fetch_departments()
        return [{"code": d["code"], "name": d["name"]} for d in depts]

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
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "", "schedules": [],
        }

        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return {k: d.get(k, "") if k != "schedules" else d.get(k, [])
                            for k in ("staff_id", "name", "department", "position",
                                     "specialty", "profile_url", "notes", "schedules")}
            return empty

        prefix = f"{self.hospital_code}-"
        dr_id = staff_id.replace(prefix, "") if staff_id.startswith(prefix) else staff_id

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True,
        ) as client:
            profile_info, schedules = await self._fetch_doctor_profile(client, dr_id)
            ext_id = f"{self.hospital_code}-{dr_id}"
            return {
                "staff_id": ext_id,
                "name": profile_info.get("name", ""),
                "department": profile_info.get("department", ""),
                "position": profile_info.get("position", ""),
                "specialty": profile_info.get("specialty", ""),
                "profile_url": f"{self.base_url}/ptm207.asp?Doctor_Id={dr_id}",
                "notes": "",
                "schedules": schedules,
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
                position=d["position"],
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
