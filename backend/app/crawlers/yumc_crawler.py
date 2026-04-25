"""영남대학교병원(Yeungnam University Medical Center) 크롤러

병원 공식명: 영남대학교병원
홈페이지: www.yumc.ac.kr
기술: Spring MVC `.do` + JSON API + 서버렌더링 HTML 테이블
      (httpx + BeautifulSoup)

구조:
  1) 의료진 JSON 목록 (XHR):
     POST /yumc/JsonPSearch.do  (form: clubid=all&word=)
     → {count, list:[{no, h_name, orders, profession, pic, p_class,
                      p_club_id, p_club_name, ocs_dr_id, ocs_clncDeptCde,
                      experience, ...}]}
     - `no` = 프로필 URL 의 `did` (교수 고유 번호, external_id 에 사용)
     - `ocs_dr_id` = 의사 로그인/OCS ID (스케줄 테이블에서 해당 행 식별)
     - `p_club_id` = 진료과 클럽 ID (8자리 영숫자)

  2) 진료시간표 HTML:
     GET /medical/timetable.do?clubid={p_club_id}
     → 서버렌더링 `<table class="board_doc">` — 진료과 내 모든 의사의
       오전/오후×월~토 가 한 테이블에 담김.
       각 의사 섹션은 `<th id="doc-name-{n}" mdr="ordDr:{ocs_dr_id}">` 로 시작하고
       연속 2행이 오전/오후, 셀에 `<em>예약가능</em>●` 또는 `예약가능` 혹은 빈 셀.
       간혹 행에 `*외래진료 없음` 같은 공지성 텍스트가 올 수 있음(마크 없음).

external_id: YUMC-{no}   (no 는 정수, 프로필 URL did 와 동일 → 개별 조회 가능)
"""
import re
import asyncio
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

from app.crawlers._schedule_rules import is_clinic_cell

logger = logging.getLogger(__name__)

BASE_URL = "https://www.yumc.ac.kr"
JSON_LIST_URL = f"{BASE_URL}/yumc/JsonPSearch.do"
TIMETABLE_URL = f"{BASE_URL}/medical/timetable.do"
PROFILE_URL = f"{BASE_URL}/medical/profile.do"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

# 진료과 코드 → 이름 (PSearch dropdown 기준, 전문센터는 대부분 진료과와 의사 공유)
DEPT_CLUBS: dict[str, str] = {
    "NIM697GM": "가정의학과",
    "INF225MD": "감염내과",
    "NLE611MG": "류마티스내과",
    "LGW556AE": "내분비대사내과",
    "WEN989LA": "소화기내과",
    "AEE872NE": "심장내과",
    "MAG138LA": "신장내과",
    "GNE795BW": "혈액종양내과",
    "BML259ET": "호흡기알레르기내과",
    "GEM726EE": "비뇨의학과",
    "EIE675MI": "산부인과",
    "EWM698WE": "성형외과",
    "EBG835EG": "소아청소년과",
    "EWW657IW": "신경과",
    "MTE156IM": "신경외과",
    "ALN770WG": "안센터",
    "GSHZZZZZ": "간담췌외과",
    "GSCZZZZZ": "대장항문외과",
    "LIB472IA": "소아외과",
    "GSGZZZZZ": "위장관외과",
    "GSBZZZZZ": "유방내분비외과",
    "GSVZZZZZ": "혈관외과",
    "GSAGSAGS": "외과",
    "AAAAAAAA": "중환자외상외과",
    "ETE432AT": "이비인후과",
    "GGB481EW": "재활의학과",
    "EEB396TE": "정신건강의학과",
    "LWI164EB": "정형외과",
    "NNL173IE": "심장혈관흉부외과",
    "MNE754MI": "치과",
    "NIM935NI": "피부과",
    "LEM247NB": "핵의학과",
    "ALA889BB": "방사선종양학과",
    "NWW536AT": "마취통증의학과",
    "LIT656WE": "병리과",
    "BEE834EM": "영상의학과",
    "MIM808NN": "응급의학과",
    "AWE812EE": "직업환경의학과",
    "EMM465EW": "진단검사의학과",
    "TNN626EA": "건강증진센터",
}


class YumcCrawler:
    """영남대학교병원 크롤러 — JsonPSearch (의사 목록) + timetable.do (HTML 시간표)"""

    def __init__(self):
        self.hospital_code = "YUMC"
        self.hospital_name = "영남대학교병원"
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Referer": f"{BASE_URL}/",
        }
        self._cached_data: list[dict] | None = None
        self._timetable_cache: dict[str, str] = {}

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        )

    # ─── 공개 인터페이스 ───

    async def get_departments(self) -> list[dict]:
        return [{"code": code, "name": name} for code, name in DEPT_CLUBS.items()]

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
        """개별 교수 조회 — 해당 교수 1명만 네트워크 요청.

        external_id (YUMC-{no}) 에서 no 만 있으면 JsonPSearch 로 메타를 얻고,
        해당 교수의 p_club_id 로 timetable.do 한 장만 파싱한다.
        """
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }

        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return self._to_schedule_dict(d)
            return empty

        prefix = "YUMC-"
        raw_id = staff_id[len(prefix):] if staff_id.startswith(prefix) else staff_id
        if not raw_id.isdigit():
            return empty
        target_no = int(raw_id)

        async with self._make_client() as client:
            # 전체 의사 JSON 은 한 번에 내려오고 파싱 비용도 저렴하므로
            # 여기서 fetch 후 해당 1명만 필터링 (개별 의사 상세 URL 이 없음).
            all_doctors_json = await self._fetch_json_list(client)
            target = None
            for it in all_doctors_json:
                if int(it.get("no") or 0) == target_no:
                    target = it
                    break
            if target is None:
                return empty

            meta = self._item_to_doc(target)
            # 해당 의사 진료과의 timetable 1장만 parse — 다른 교수 페이지는 조회하지 않음
            schedules = await self._fetch_timetable(client, meta["p_club_id"], meta["ocs_dr_id"])
            meta["schedules"] = schedules

        return self._to_schedule_dict(meta)

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

    # ─── 내부: 전체 크롤링 ───

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with self._make_client() as client:
            items = await self._fetch_json_list(client)
            logger.info(f"[YUMC] JsonPSearch 의사 {len(items)}명 수신")

            docs = [self._item_to_doc(it) for it in items]
            docs = [d for d in docs if d]

            # 진료과별로 timetable 1장씩 병렬 fetch → ocs_dr_id 매칭으로 의사별 schedules 채움
            # 교수가 없는 센터 club 은 건너뛰고, 실제 의사의 p_club_id 만 수집
            club_ids: set[str] = set()
            for d in docs:
                if d["p_club_id"]:
                    club_ids.add(d["p_club_id"])

            sem = asyncio.Semaphore(8)

            async def fill_club(club_id: str):
                async with sem:
                    try:
                        html = await self._get_timetable_html(client, club_id)
                    except Exception as e:
                        logger.warning(f"[YUMC] timetable 실패 club={club_id}: {e}")
                        return club_id, {}
                    return club_id, self._parse_timetable(html)

            results = await asyncio.gather(
                *[fill_club(cid) for cid in club_ids], return_exceptions=True
            )

            club_schedules: dict[str, dict[str, list[dict]]] = {}
            for r in results:
                if isinstance(r, Exception):
                    continue
                cid, by_dr = r
                club_schedules[cid] = by_dr

            for d in docs:
                by_dr = club_schedules.get(d["p_club_id"], {})
                sch = by_dr.get((d["ocs_dr_id"] or "").strip(), [])
                d["schedules"] = sch
                d["date_schedules"] = []  # 주간 패턴만 제공 (달력 없음)

        # 중복 제거 (같은 `no`)
        seen: set[str] = set()
        uniq: list[dict] = []
        for d in docs:
            if d["external_id"] in seen:
                continue
            seen.add(d["external_id"])
            uniq.append(d)

        logger.info(f"[YUMC] 총 {len(uniq)}명")
        self._cached_data = uniq
        return uniq

    async def _fetch_json_list(self, client: httpx.AsyncClient) -> list[dict]:
        """의료진 JSON 목록 — 한 번의 POST 로 전체 의사 반환."""
        resp = await client.post(
            JSON_LIST_URL,
            data={"clubid": "all", "word": ""},
            headers={
                **self.headers,
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": BASE_URL,
                "Referer": f"{BASE_URL}/yumc/PSearch.do",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        lst = data.get("list") or []
        if not isinstance(lst, list):
            return []
        return lst

    def _item_to_doc(self, it: dict) -> dict | None:
        no = it.get("no")
        if no is None:
            return None
        try:
            no_int = int(no)
        except Exception:
            return None

        name = (it.get("h_name") or "").strip()
        if not name:
            return None

        club_id = (it.get("p_club_id") or "").strip()
        club_name = (it.get("p_club_name") or "").strip()
        if not club_name or club_name == "-":
            club_name = DEPT_CLUBS.get(club_id, (it.get("p_class") or "").strip())

        orders = (it.get("orders") or "").strip()
        profession = (it.get("profession") or "").strip()
        clnc_dept = (it.get("ocs_clncDeptCde") or "").strip()
        dr_id = (it.get("ocs_dr_id") or "").strip()

        # 프로필 URL
        profile = ""
        if club_id and clnc_dept and clnc_dept != "-" and dr_id and dr_id != "-":
            profile = (
                f"{PROFILE_URL}?clubid={club_id}&did={no_int}"
                f"&clncDeptCde={clnc_dept}&dr={dr_id}"
            )
        elif club_id:
            profile = f"{BASE_URL}/medical/main.do?clubid={club_id}"

        # 사진 (pic_show: "파일명|w|h" 또는 pic: "파일명")
        photo = ""
        pic_show = (it.get("pic_show") or "").strip()
        pic_raw = (it.get("pic") or "").strip()
        fname = ""
        if pic_show:
            fname = pic_show.split("|", 1)[0].strip()
        if not fname and pic_raw:
            fname = pic_raw
        if fname:
            photo = f"{BASE_URL}/data/face/professor/{fname}"

        # 경력은 너무 길면 잘라서 notes 에 저장
        notes_src = (it.get("experience") or "").strip()
        notes = notes_src[:500] if notes_src else ""

        ext_id = f"YUMC-{no_int}"
        return {
            "staff_id": ext_id,
            "external_id": ext_id,
            "no": no_int,
            "p_club_id": club_id,
            "ocs_dr_id": dr_id,
            "ocs_clncDeptCde": clnc_dept,
            "name": name,
            "department": club_name or "미분류",
            "position": orders,
            "specialty": profession,
            "profile_url": profile,
            "photo_url": photo,
            "notes": notes,
            "schedules": [],
            "date_schedules": [],
        }

    # ─── 내부: timetable ───

    async def _get_timetable_html(self, client: httpx.AsyncClient, club_id: str) -> str:
        if club_id in self._timetable_cache:
            return self._timetable_cache[club_id]
        resp = await client.get(TIMETABLE_URL, params={"clubid": club_id})
        resp.raise_for_status()
        html = resp.text
        self._timetable_cache[club_id] = html
        return html

    def _parse_timetable(self, html: str) -> dict[str, list[dict]]:
        """timetable.do HTML → { ocs_dr_id: [schedules...] } 매핑.

        구조:
          <tr>
            <th id="doc-name-N" mdr="ordDr:DRID" rowspan='3'> ... </th>
            <td rowspan='3'> 진료과목 </td>
            <td rowspan='3'> 직위 </td>
            <th> 오전 </th> <td yoil_1/> ... <td yoil_6/> <td rowspan='3'>예약</td>
          </tr>
          <tr>
            <th> 오후 </th> <td yoil_1/> ... <td yoil_6/>
          </tr>
          <tr>  (colspan=7 공지 행 — skip) </tr>
        """
        soup = BeautifulSoup(html, "html.parser")
        result: dict[str, list[dict]] = {}

        for th in soup.select("th[id^='doc-name-'][mdr]"):
            mdr = th.get("mdr", "")
            m = re.match(r"ordDr:(.+)", mdr)
            if not m:
                continue
            dr_id = m.group(1).strip()
            if not dr_id:
                continue

            doc_row = th.find_parent("tr")
            if doc_row is None:
                continue

            # 오전 행 = doc_row, 오후 행 = doc_row.find_next_sibling("tr")
            am_row = doc_row
            pm_row = doc_row.find_next_sibling("tr")

            schedules = self._parse_am_pm_rows(am_row, pm_row, th.get("id", ""))
            if dr_id in result:
                result[dr_id].extend(schedules)
            else:
                result[dr_id] = schedules
        return result

    @staticmethod
    def _headers_tokens(cell) -> list[str]:
        """td/th 의 headers 속성을 토큰 리스트로 반환 (bs4 는 list 또는 str 반환)."""
        h = cell.get("headers") or []
        if isinstance(h, str):
            return h.split()
        return list(h)

    def _parse_am_pm_rows(self, am_row, pm_row, doc_id: str) -> list[dict]:
        """오전/오후 행 2개에서 월~토 6칸을 읽어 schedules 리스트 반환."""
        schedules: list[dict] = []
        for slot, row in (("morning", am_row), ("afternoon", pm_row)):
            if row is None:
                continue
            for cell in row.find_all("td"):
                tokens = self._headers_tokens(cell)
                # yoil_{1..6} 토큰이 있어야 요일 셀
                yoil_tok = next((t for t in tokens if t.startswith("yoil_")), None)
                if not yoil_tok:
                    continue
                try:
                    dow = int(yoil_tok.split("_", 1)[1]) - 1  # yoil_1=월=0
                except Exception:
                    continue
                if dow < 0 or dow > 5:
                    continue
                # 같은 테이블에 여러 의사가 있으므로 doc_id 로 필터
                if doc_id and doc_id not in tokens:
                    continue

                text = cell.get_text(" ", strip=True)
                # 시트 구조상 <em>예약가능</em>● 처럼 마크가 찍혀 있음.
                # 빈 셀/휴진 셀은 is_clinic_cell 이 걸러냄.
                if not is_clinic_cell(text):
                    continue
                start, end = TIME_RANGES[slot]
                schedules.append({
                    "day_of_week": dow,
                    "time_slot": slot,
                    "start_time": start,
                    "end_time": end,
                    "location": "",
                })

        # 중복 제거 + 정렬
        uniq = {}
        for s in schedules:
            key = (s["day_of_week"], s["time_slot"])
            uniq[key] = s
        return sorted(uniq.values(), key=lambda s: (s["day_of_week"],
                                                    0 if s["time_slot"] == "morning" else 1))

    async def _fetch_timetable(self, client: httpx.AsyncClient, club_id: str, dr_id: str) -> list[dict]:
        """개별 교수용: 진료과 timetable 1장 parse → 특정 dr_id 행만 뽑기."""
        if not club_id or not dr_id:
            return []
        try:
            html = await self._get_timetable_html(client, club_id)
        except Exception as e:
            logger.warning(f"[YUMC] 개별 timetable 실패 club={club_id} dr={dr_id}: {e}")
            return []
        by_dr = self._parse_timetable(html)
        return by_dr.get(dr_id.strip(), [])

    # ─── 유틸 ───

    def _to_schedule_dict(self, d: dict) -> dict:
        return {
            "staff_id": d.get("staff_id", d.get("external_id", "")),
            "name": d.get("name", ""),
            "department": d.get("department", ""),
            "position": d.get("position", ""),
            "specialty": d.get("specialty", ""),
            "profile_url": d.get("profile_url", ""),
            "notes": d.get("notes", ""),
            "schedules": d.get("schedules", []),
            "date_schedules": d.get("date_schedules", []),
        }
