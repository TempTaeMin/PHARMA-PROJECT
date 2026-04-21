"""홍익병원(Hongik Hospital) 크롤러

병원 공식명: 홍익병원 (서울 양천구 목동로 225, 신정동)
홈페이지: hongikh.cafe24.com  (cafe24 호스팅 PHP, UTF-8)

구조:
  1) 진료과 목록: /depart/depart.php — `a[href*="depart_info"]?dept_name={한글}` 23개
  2) 진료과별 의료진+스케줄: /depart/depart_info.php?dept_name={한글}
      `div.doctor` 카드 반복. 각 카드:
        - `.d_pic img src="/upload/doctor/{docid}.png"` — 사진. filename 이 docid.
        - `button onclick="PopUp('depart_doctor_pop.php?doctor={docid}&dept_name=...')"` 에도 docid.
        - `.d_name` — "{진료과} {이름}" (mgl10 span 으로 이름 래핑)
        - `dl > dt=진료분야 + dd` — specialty + 월별 휴진일 공지
        - `dl.time_table > dd > table` — 진료시간표
             - `<td class="clinic">진료</td>` 또는 "변경진료" = 외래
             - 빈 `<td>` = 휴진
             - 월~토 6일

external_id: HONGIK-{DD}-{docid}
  DD = 진료과 인덱스 (00~22, 고정 순서). 개별 조회 시 해당 진료과 페이지 1회 GET (skill 규칙 #7 준수).
"""
import re
import asyncio
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://hongikh.cafe24.com"

# 고정 진료과 순서 — external_id 안정성을 위해 절대 변경 금지 (추가만 가능).
DEPT_LIST = [
    "소화기내과", "순환기내과", "호흡기내과", "내분비내과", "감염내과",
    "신장내과", "신경과", "정형외과", "신경외과", "피부/비뇨의학과",
    "산부인과", "외과", "소아청소년과", "가정의학과", "안과",
    "이비인후과", "성형외과", "정신건강의학과", "치과", "응급의학과",
    "마취통증의학과", "진단검사의학과", "영상의학과",
]

TIME_RANGES = {"morning": ("09:00", "12:30"), "afternoon": ("13:30", "17:00")}

_NON_WORKING_TEXT = {"", "-", "―", "휴진", "x", "X"}


class HongikCrawler:
    def __init__(self):
        self.hospital_code = "HONGIK"
        self.hospital_name = "홍익병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Referer": BASE_URL,
        }
        self._cached_data: list[dict] | None = None

    @staticmethod
    def _is_working(text: str) -> bool:
        t = (text or "").strip()
        if not t:
            return False
        if t in _NON_WORKING_TEXT:
            return False
        return True

    def _parse_schedule_table(self, table) -> list[dict]:
        if table is None:
            return []
        tbody = table.find("tbody") or table
        trs = tbody.find_all("tr", recursive=False) or tbody.find_all("tr")
        schedules: list[dict] = []
        for tr in trs:
            label_el = tr.find("th")
            if not label_el:
                continue
            label = label_el.get_text(strip=True)
            slot = "morning" if "오전" in label else ("afternoon" if "오후" in label else None)
            if slot is None:
                continue
            tds = tr.find_all("td")
            for dow, td in enumerate(tds[:6]):
                text = td.get_text(" ", strip=True)
                if not self._is_working(text):
                    continue
                s, e = TIME_RANGES[slot]
                schedules.append({
                    "day_of_week": dow, "time_slot": slot,
                    "start_time": s, "end_time": e, "location": "",
                })
        return schedules

    def _parse_dept_page(self, html: str, dept_name: str, dept_idx: int) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        doctors = soup.select("div.doctor")
        result: list[dict] = []
        for d in doctors:
            img = d.select_one(".d_pic img")
            img_src = img.get("src", "") if img else ""
            # filename = docid
            m = re.search(r"/upload/doctor/(\w+)\.(?:png|jpg|gif|jpeg)", img_src)
            docid = m.group(1) if m else ""
            if not docid:
                # 폴백: button onclick 에서 추출
                btn = d.select_one(".d_pic button")
                if btn:
                    onclick = btn.get("onclick", "")
                    m2 = re.search(r"doctor=([\w\d]+)", onclick)
                    if m2:
                        docid = m2.group(1)
            if not docid:
                continue

            # 이름: '.d_name' 전체 텍스트는 "{dept} {name}" 형태. mgl10 span 안의 이름을 우선.
            name_el = d.select_one(".d_name .mgl10")
            if name_el:
                raw_name = name_el.get_text(" ", strip=True)
            else:
                name_full = d.select_one(".d_name")
                raw_name = name_full.get_text(" ", strip=True) if name_full else ""
                # dept_name 접두사 제거
                if raw_name.startswith(dept_name):
                    raw_name = raw_name[len(dept_name):].strip()
            m_name = re.match(r"^([가-힣]{2,4})", raw_name)
            name = m_name.group(1) if m_name else raw_name.split()[0] if raw_name else ""

            # specialty (진료분야)
            specialty = ""
            notes = ""
            for dl in d.find_all("dl"):
                dt = dl.find("dt")
                if not dt:
                    continue
                dt_text = dt.get_text(strip=True)
                dd = dl.find("dd")
                if not dd:
                    continue
                if "진료분야" in dt_text:
                    # <br> 를 개행으로 치환해 줄 단위 분리 가능하도록
                    dd_copy = BeautifulSoup(str(dd), "html.parser")
                    for br in dd_copy.find_all("br"):
                        br.replace_with("\n")
                    full_dd = dd_copy.get_text("\n", strip=True)
                    lines = [ln.strip() for ln in full_dd.split("\n") if ln.strip()]
                    spec_lines = []
                    note_lines = []
                    for ln in lines:
                        # "※", "▶", "휴진", "휴무" 로 시작/포함하는 줄은 notes
                        if re.search(r"^[※▶]|(휴진|휴무)", ln):
                            note_lines.append(ln)
                        else:
                            spec_lines.append(ln)
                    specialty = " ".join(spec_lines).strip()
                    if note_lines:
                        notes = " / ".join(note_lines)

            schedules = []
            time_dl = None
            for dl in d.find_all("dl"):
                if "time_table" in (dl.get("class") or []):
                    time_dl = dl
                    break
            if time_dl:
                tbl = time_dl.find("table")
                schedules = self._parse_schedule_table(tbl)

            ext_id = f"{self.hospital_code}-{dept_idx:02d}-{docid}"
            photo_url = f"{BASE_URL}{img_src}" if img_src.startswith("/") else img_src
            profile_url = (
                f"{BASE_URL}/depart/depart_doctor_pop.php?doctor={docid}"
                f"&dept_name={dept_name}"
            )
            result.append({
                "staff_id": ext_id,
                "external_id": ext_id,
                "name": name,
                "department": dept_name,
                "position": "",
                "specialty": specialty,
                "profile_url": profile_url,
                "photo_url": photo_url,
                "notes": notes,
                "schedules": schedules,
                "date_schedules": [],
                "_docid": docid,
                "_dept_idx": dept_idx,
            })
        return result

    async def _fetch_dept(
        self, client: httpx.AsyncClient, dept_idx: int, dept_name: str
    ) -> list[dict]:
        url = f"{BASE_URL}/depart/depart_info.php"
        try:
            resp = await client.get(url, params={"dept_name": dept_name})
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[HONGIK] {dept_name} 실패: {e}")
            return []
        return self._parse_dept_page(resp.text, dept_name, dept_idx)

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        all_doctors: dict[str, dict] = {}
        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True,
        ) as client:
            results = await asyncio.gather(
                *[
                    self._fetch_dept(client, idx, dn)
                    for idx, dn in enumerate(DEPT_LIST)
                ],
                return_exceptions=True,
            )

        for res in results:
            if isinstance(res, Exception):
                continue
            for d in res:
                key = d["external_id"]
                if key not in all_doctors:
                    all_doctors[key] = d

        result = list(all_doctors.values())
        logger.info(f"[HONGIK] 총 {len(result)}명")
        self._cached_data = result
        return result

    # ─── 공개 인터페이스 ───

    async def get_departments(self) -> list[dict]:
        return [{"code": dn, "name": dn} for dn in DEPT_LIST]

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
        """개별 조회 — external_id 의 dept_idx 로 해당 진료과 페이지 1회 GET"""
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
            return empty

        m = re.match(r"^HONGIK-(\d{2})-(\w+)$", staff_id)
        if not m:
            return empty
        dept_idx = int(m.group(1))
        docid = m.group(2)
        if dept_idx >= len(DEPT_LIST):
            return empty
        dept_name = DEPT_LIST[dept_idx]

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True,
        ) as client:
            doctors = await self._fetch_dept(client, dept_idx, dept_name)

        for d in doctors:
            if d["_docid"] == docid:
                return {
                    "staff_id": staff_id,
                    "name": d["name"], "department": d["department"],
                    "position": d["position"], "specialty": d["specialty"],
                    "profile_url": d["profile_url"], "notes": d["notes"],
                    "schedules": d["schedules"],
                    "date_schedules": d["date_schedules"],
                }
        return empty

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
