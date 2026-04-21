"""강동성심병원 크롤러

구조:
  1) 진료과 목록 HTML: /sub202.php
     → div.clinic_list2 (onclick에 /sub202_1.php?bid=XXXXXX)
     → .clinic_list_txt2 = 진료과명
  2) 진료과별 의료진 HTML: /sub202_1.php?bid={bid}
     → table.sub201_02 내부 각 행:
         img.sub201_doc_img, span.doct_name_bold (이름+직책),
         span.sub201_dept (진료과), onclick="openDocPop('NNNN')" (의사 ID)
  3) 의사 상세/스케줄 JSON API: POST /proc/doctor_info.php  form: id={dtid}
     → { drname, posname, dtid, drdeptid, drmajor (|분리),
         drspec, drphoto, am:{mon..sat}, pm:{mon..sat} }
         am/pm 값이 '●' 이면 해당 요일 오전/오후 진료

external_id: KDH-{dtid}
"""
import re
import asyncio
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://www.kdh.or.kr"
DEPT_LIST_URL = f"{BASE_URL}/sub202.php"
DEPT_DETAIL_URL = f"{BASE_URL}/sub202_1.php"
DOCTOR_INFO_URL = f"{BASE_URL}/proc/doctor_info.php"
PROFILE_URL = f"{BASE_URL}/sub202_1.php?bid={{bid}}"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:30", "17:00")}
DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat"]


class KdhCrawler:
    """강동성심병원 크롤러 — dept HTML + doctor_info.php JSON"""

    def __init__(self):
        self.hospital_code = "KDH"
        self.hospital_name = "강동성심병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Referer": BASE_URL,
        }
        self._cached_data: list[dict] | None = None
        self._cached_depts: list[dict] | None = None

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        )

    async def _fetch_dept_list(self, client: httpx.AsyncClient) -> list[dict]:
        """진료과 목록 HTML에서 (bid, 이름) 추출"""
        if self._cached_depts is not None:
            return self._cached_depts
        try:
            resp = await client.get(DEPT_LIST_URL)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[KDH] 진료과 목록 실패: {e}")
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        depts: list[dict] = []
        seen: set[str] = set()
        # sub_con_area 안에 있는 clinic_list2만 본문 진료과 (상단 메뉴 제외)
        con = soup.select_one("div.sub_con_area")
        if not con:
            return []
        for div in con.select("div.clinic_list2"):
            onclick = div.get("onclick", "")
            m = re.search(r"bid=(\d+)", onclick)
            if not m:
                continue
            bid = m.group(1)
            if bid in seen:
                continue
            seen.add(bid)
            name_el = div.select_one(".clinic_list_txt2")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                continue
            depts.append({"code": bid, "name": name})
        self._cached_depts = depts
        return depts

    async def _fetch_dept_doctors(
        self, client: httpx.AsyncClient, bid: str, dept_name: str,
    ) -> list[dict]:
        """진료과 상세 페이지에서 의사 (dtid, name, position) 추출"""
        try:
            resp = await client.get(DEPT_DETAIL_URL, params={"bid": bid})
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[KDH] {dept_name}({bid}) 페이지 실패: {e}")
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        doctors: list[dict] = []
        seen: set[str] = set()
        table = soup.select_one("table.sub201_02")
        if not table:
            return []
        # 각 의사 블록은 doct_name_bold 와 openDocPop 호출을 포함
        # 각 의사는 2행(tr)로 구성: 첫 행(rowspan=2) = 이미지 + 이름, 둘째 행 = 버튼들(openDocPop)
        for name_el in table.select("span.doct_name_bold"):
            raw = name_el.get_text(" ", strip=True)
            parts = raw.split()
            name = parts[0] if parts else ""
            position = " ".join(parts[1:]) if len(parts) > 1 else ""
            # 이름이 포함된 tr + 바로 다음 tr 까지 스캔
            row = name_el.find_parent("tr")
            scan_nodes = []
            if row:
                scan_nodes.append(row)
                nxt = row.find_next_sibling("tr")
                if nxt is not None:
                    scan_nodes.append(nxt)
            else:
                scan_nodes.append(name_el.parent)
            dtid = ""
            for node in scan_nodes:
                for tag in node.find_all(attrs={"onclick": re.compile(r"openDocPop")}):
                    m = re.search(r"openDocPop\s*\(\s*'([^']+)'", tag.get("onclick", ""))
                    if m:
                        dtid = m.group(1)
                        break
                if dtid:
                    break
            if not dtid or not name or dtid in seen:
                continue
            seen.add(dtid)
            doctors.append({"dtid": dtid, "name": name, "position": position, "dept_bid": bid, "dept_name": dept_name})
        return doctors

    async def _fetch_doctor_info(
        self, client: httpx.AsyncClient, dtid: str,
    ) -> dict | None:
        """doctor_info.php POST → JSON"""
        try:
            resp = await client.post(DOCTOR_INFO_URL, data={"id": dtid})
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"[KDH] 의사({dtid}) 정보 실패: {e}")
            return None

    def _build_schedules(self, info: dict) -> list[dict]:
        """am/pm JSON → schedules"""
        if not info:
            return []
        schedules: list[dict] = []
        for slot_key, slot_name in (("am", "morning"), ("pm", "afternoon")):
            slot_data = info.get(slot_key) or {}
            if not isinstance(slot_data, dict):
                continue
            for dow, day in enumerate(DAY_KEYS):
                val = slot_data.get(day)
                if not val or not isinstance(val, str):
                    continue
                # "●" 또는 다른 마커가 있으면 진료
                if val.strip() in ("", "-"):
                    continue
                start, end = TIME_RANGES[slot_name]
                schedules.append({
                    "day_of_week": dow,
                    "time_slot": slot_name,
                    "start_time": start,
                    "end_time": end,
                    "location": "",
                })
        return schedules

    def _build_doctor_dict(self, info: dict, fallback: dict) -> dict:
        """JSON 응답 + dept 정보 → 표준 dict"""
        dtid = (info.get("dtid") if info else None) or fallback.get("dtid", "")
        name = (info.get("drname") if info else None) or fallback.get("name", "")
        position = (info.get("posname") if info else None) or fallback.get("position", "")
        drmajor = (info.get("drmajor") if info else None) or fallback.get("dept_name", "")
        dept_name = drmajor.split("|")[0].strip() if drmajor else fallback.get("dept_name", "")
        specialty = (info.get("drspec") if info else None) or ""
        drphoto = (info.get("drphoto") if info else None) or ""
        photo_url = ""
        if drphoto:
            photo_url = drphoto if drphoto.startswith("http") else f"{BASE_URL}{drphoto}"
        bid = fallback.get("dept_bid") or (info.get("drdeptid") if info else "") or ""
        profile_url = PROFILE_URL.format(bid=bid) if bid else BASE_URL
        schedules = self._build_schedules(info) if info else []
        ext_id = f"KDH-{dtid}"
        return {
            "staff_id": ext_id,
            "external_id": ext_id,
            "dtid": dtid,
            "name": name,
            "department": dept_name,
            "position": position,
            "specialty": specialty,
            "profile_url": profile_url,
            "photo_url": photo_url,
            "notes": "",
            "schedules": schedules,
        }

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with self._make_client() as client:
            depts = await self._fetch_dept_list(client)
            if not depts:
                self._cached_data = []
                return []

            # 1) 모든 진료과에서 의사 목록 수집
            sem_dept = asyncio.Semaphore(5)

            async def fetch_dept(d):
                async with sem_dept:
                    return await self._fetch_dept_doctors(client, d["code"], d["name"])

            dept_tasks = [asyncio.create_task(fetch_dept(d)) for d in depts]
            dept_results = await asyncio.gather(*dept_tasks, return_exceptions=True)

            # dtid 중복 제거 — 여러 진료과 동시 소속 의사는 첫 번째 진료과만 사용
            doc_by_id: dict[str, dict] = {}
            for r in dept_results:
                if isinstance(r, Exception):
                    continue
                for d in r:
                    if d["dtid"] not in doc_by_id:
                        doc_by_id[d["dtid"]] = d

            # 2) 각 의사 JSON 조회
            sem_doc = asyncio.Semaphore(10)

            async def fetch_info(dtid):
                async with sem_doc:
                    return dtid, await self._fetch_doctor_info(client, dtid)

            info_tasks = [asyncio.create_task(fetch_info(dtid)) for dtid in doc_by_id.keys()]
            info_results = await asyncio.gather(*info_tasks, return_exceptions=True)

            all_doctors: list[dict] = []
            for r in info_results:
                if isinstance(r, Exception):
                    continue
                dtid, info = r
                fallback = doc_by_id.get(dtid, {})
                all_doctors.append(self._build_doctor_dict(info, fallback))

        logger.info(f"[KDH] 총 {len(all_doctors)}명")
        self._cached_data = all_doctors
        return all_doctors

    # ─── 공개 인터페이스 ───

    async def get_departments(self) -> list[dict]:
        async with self._make_client() as client:
            return await self._fetch_dept_list(client)

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
        """개별 교수 조회 — doctor_info.php 한 번만 호출"""
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "", "schedules": [],
        }

        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return {k: d.get(k, "") for k in
                            ("staff_id", "name", "department", "position",
                             "specialty", "profile_url", "notes", "schedules")}
            return empty

        prefix = "KDH-"
        dtid = staff_id[len(prefix):] if staff_id.startswith(prefix) else staff_id
        if not dtid:
            return empty

        async with self._make_client() as client:
            info = await self._fetch_doctor_info(client, dtid)

        if not info or not info.get("dtid"):
            return empty

        doc = self._build_doctor_dict(info, {"dtid": dtid})
        return {k: doc.get(k, "") for k in
                ("staff_id", "name", "department", "position",
                 "specialty", "profile_url", "notes", "schedules")}

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
