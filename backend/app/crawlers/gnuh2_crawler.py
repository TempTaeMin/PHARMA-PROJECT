"""경상국립대학교병원(GNUH2) 크롤러

경남 진주시 강남로 79 / www.gnuh.co.kr (진주 본원)
* 분원 창원경상대학교병원(gnuch.co.kr)은 별도. 본 크롤러는 진주 본원만.
* HOSPITAL_CODE 가 GNUH2 인 이유: 전북대 GNUH 와 코드 충돌을 피하려고 메인이 'GNUH2' 로 정함.

⚠️ httpx / aiohttp 비호환:
  GNUH 서버는 비표준 응답 헤더 'Referrer Policy: strict-origin-when-cross-origin'
  (공백, 표준은 'Referrer-Policy') 를 내려보낸다. httpx 의 h11 파서뿐 아니라
  aiohttp 도 'Invalid header token' 으로 거부한다. 그래서 본 크롤러는
  asyncio.create_subprocess_exec('curl', ...) 로 HTTP 요청을 수행한다.

구조 (정적 HTML, /gnuh/...do):
  1) 진료과 목록
       /gnuh/treat/list.do?rbsIdx=54
       → ul#_list 의 <a href="info.do?rbsIdx=54&code={진료과코드}"> 에서 코드/이름 추출
  2) 진료과별 의료진 목록
       /gnuh/treat/docList.do?rbsIdx=55&code={진료과코드}
       → ul#_docList li.gallery3_Wrap 의 카드에서 이름/사진/dno/전문분야 추출
       → docInfo.do?rbsIdx=55&code={dept}&dno={dno}
  3) 의사 개별 상세 + 시간표
       /gnuh/treat/docInfo.do?rbsIdx=55&code={dept}&dno={dno}
       → table.tbTypeB 행에 진료 마크 <img alt="진료"> 가 들어있음

스케줄:
  - 주간 패턴: thead 가 월~금, 각 요일 colspan=2 (오전/오후) 구조
  - 진료 셀 = <img ... alt="진료"> 또는 alt="외래" 가 포함된 <img>
  - 모바일 일정표(mobile_schedule)는 5일치 날짜만 보여 date_schedules 로는 부족 → 미사용
  - 휴진 일정 표는 별도 (3개월치) 이지만 schedules 가 주 패턴이므로 본 크롤러는 schedules 만 반환

external_id 포맷: GNUH2-{dept}-{dno}
  (dept 는 단독 조회 URL 에 필수. 슬래시 없이 하이픈으로 결합.)
"""
from __future__ import annotations

import re
import asyncio
import logging
from datetime import datetime

from bs4 import BeautifulSoup

from app.crawlers._schedule_rules import is_clinic_cell

logger = logging.getLogger(__name__)

BASE_URL = "https://www.gnuh.co.kr"
DEPT_LIST_URL = f"{BASE_URL}/gnuh/treat/list.do?rbsIdx=54"
DOC_LIST_URL_FMT = f"{BASE_URL}/gnuh/treat/docList.do?rbsIdx=55&code={{dept}}"
DOC_INFO_URL_FMT = f"{BASE_URL}/gnuh/treat/docInfo.do?rbsIdx=55&code={{dept}}&dno={{dno}}"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}
DAY_KO = ("월", "화", "수", "목", "금", "토", "일")
DAY_INDEX = {ko: i for i, ko in enumerate(DAY_KO)}

# fetch 동시성 제한
_DEPT_SEM_LIMIT = 4
_DOC_SEM_LIMIT = 6
_CURL_TIMEOUT_SEC = 25
_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


async def _curl_get(url: str, referer: str | None = None) -> str:
    """asyncio subprocess curl 으로 GET. 비표준 헤더로 인한 httpx/aiohttp 실패 회피."""
    args = [
        "curl", "-sk",
        "-A", _DEFAULT_UA,
        "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "-H", "Accept-Language: ko-KR,ko;q=0.9,en;q=0.8",
        "--connect-timeout", "10",
        "--max-time", str(_CURL_TIMEOUT_SEC),
    ]
    if referer:
        args.extend(["-H", f"Referer: {referer}"])
    args.append(url)
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=_CURL_TIMEOUT_SEC + 5)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        raise RuntimeError(f"curl timeout: {url}")
    if proc.returncode != 0:
        raise RuntimeError(
            f"curl failed rc={proc.returncode} url={url}: {err.decode('utf-8', 'ignore')[:200]}"
        )
    # 페이지가 cp949 일 가능성도 있으나 메타에 utf-8 선언되어 있어 utf-8 우선
    try:
        return out.decode("utf-8")
    except UnicodeDecodeError:
        return out.decode("cp949", errors="replace")


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


class Gnuh2Crawler:
    """경상국립대학교병원(진주 본원) 크롤러."""

    def __init__(self) -> None:
        self.hospital_code = "GNUH2"
        self.hospital_name = "경상국립대학교병원"
        self._cached_data: list[dict] | None = None
        self._dept_map: dict[str, str] | None = None

    # ───────────────────── 진료과 목록 ─────────────────────

    async def _fetch_dept_map(self) -> dict[str, str]:
        if self._dept_map is not None:
            return self._dept_map
        try:
            html = await _curl_get(DEPT_LIST_URL, referer=f"{BASE_URL}/gnuh/main/main.do?rbsIdx=1")
        except Exception as e:
            logger.error(f"[GNUH2] 진료과 목록 로드 실패: {e}")
            self._dept_map = {}
            return self._dept_map

        soup = BeautifulSoup(html, "html.parser")
        result: dict[str, str] = {}
        ul = soup.find("ul", id="_list")
        if ul is None:
            # fallback: 전체 anchor 스캔
            anchors = soup.find_all("a", href=True)
        else:
            anchors = ul.find_all("a", href=True)

        for a in anchors:
            href = a["href"]
            m = re.search(r"info\.do\?[^\"']*?code=([A-Za-z0-9]+)", href)
            if not m:
                continue
            code = m.group(1)
            name = _clean(a.get_text(" ", strip=True))
            # icon 링크 alt(blind 텍스트) 제외
            if not name or "진료과 소개" in name or "의료진 보기" in name:
                continue
            if code in result:
                # 처음 들어온 이름 유지 (대개 본문 메뉴의 정식 명칭)
                continue
            result[code] = name

        self._dept_map = result
        logger.info(f"[GNUH2] 진료과 {len(result)}개 추출")
        return result

    # ───────────────────── 시간표 파싱 ─────────────────────

    @staticmethod
    def _img_is_clinic(img) -> bool:
        """<img alt='진료'/외래'> 같은 진료 마크 판정."""
        if img is None:
            return False
        alt = (img.get("alt") or "").strip()
        if not alt:
            return False
        # 마크 alt 텍스트도 _schedule_rules 로 통일 판정
        if any(kw in alt for kw in ("진료", "외래", "예약", "격주", "순환")):
            return True
        return False

    @classmethod
    def _is_active_cell(cls, td) -> bool:
        if td is None:
            return False
        # img alt 마크 우선
        for img in td.find_all("img"):
            if cls._img_is_clinic(img):
                return True
        text = td.get_text(" ", strip=True)
        if not text:
            return False
        return is_clinic_cell(text)

    def _parse_schedule_table(self, table) -> list[dict]:
        """docInfo 페이지의 진료일정 테이블 파싱.

        구조:
          thead row1: 의료진명(rowspan=3), 전문진료분야(rowspan=3), 진료일정(colspan=10)
          thead row2: 월(colspan=2) 화 ... 금
          thead row3: 오전 오후 ...
          tbody row : <td>이름</td><td>전문분야</td>(<td>오전</td><td>오후</td>) × 5
        """
        if table is None:
            return []
        thead = table.find("thead")
        if thead is None:
            return []
        rows = thead.find_all("tr")
        if not rows:
            return []

        # 두 번째 thead 행에서 요일 추출 (colspan=2 인 th 들)
        day_order: list[int] = []
        if len(rows) >= 2:
            for th in rows[1].find_all("th"):
                t = _clean(th.get_text())
                if t in DAY_INDEX:
                    day_order.append(DAY_INDEX[t])
        if not day_order:
            return []

        results: list[dict] = []
        tbody = table.find("tbody")
        if tbody is None:
            return results

        # body 의 각 tr 은 의사 한 명씩. 의료진명/전문분야 td 두 개를 건너뛰고
        # 그 뒤 (오전/오후) × len(day_order) 개의 셀을 본다.
        for tr in tbody.find_all("tr", recursive=False):
            tds = tr.find_all("td", recursive=False)
            if len(tds) < 2 + 2 * len(day_order):
                # 이름·분야 colspan 또는 rowspan 으로 인해 부족할 수 있음
                # 첫 두 칸 + 슬롯 칸 합계가 안 맞으면 건너뜀
                continue

            slot_tds = tds[2:]
            for di, day_idx in enumerate(day_order):
                m_idx = di * 2
                a_idx = di * 2 + 1
                if a_idx >= len(slot_tds):
                    break
                if self._is_active_cell(slot_tds[m_idx]):
                    s, e = TIME_RANGES["morning"]
                    results.append({
                        "day_of_week": day_idx,
                        "time_slot": "morning",
                        "start_time": s,
                        "end_time": e,
                        "location": "",
                    })
                if self._is_active_cell(slot_tds[a_idx]):
                    s, e = TIME_RANGES["afternoon"]
                    results.append({
                        "day_of_week": day_idx,
                        "time_slot": "afternoon",
                        "start_time": s,
                        "end_time": e,
                        "location": "",
                    })

        # 동일 의사 페이지에 같은 진료과 다른 의사도 표에 같이 나오는 경우가 있어
        # 첫 의사 행만 본다 (호출자가 단일 의사 페이지에서 호출하는 전제)
        # → 위 루프에서 모든 행을 합쳐도 동일 진료과의 다른 의사 데이터가 섞이지 않도록
        #   _parse_doctor_info_table 가 row 를 한 개만 찾도록 별도 처리한다.
        return results

    def _parse_doctor_row(self, table, doctor_name: str) -> list[dict]:
        """docInfo 의 진료일정 표에서 특정 의사 이름의 행 1개만 골라 스케줄 파싱."""
        if table is None or not doctor_name:
            return []
        thead = table.find("thead")
        if thead is None:
            return []
        rows = thead.find_all("tr")
        day_order: list[int] = []
        if len(rows) >= 2:
            for th in rows[1].find_all("th"):
                t = _clean(th.get_text())
                if t in DAY_INDEX:
                    day_order.append(DAY_INDEX[t])
        if not day_order:
            return []

        tbody = table.find("tbody")
        if tbody is None:
            return []

        target_tr = None
        for tr in tbody.find_all("tr", recursive=False):
            name_cell = tr.find("td")
            if name_cell is None:
                continue
            name_text = _clean(name_cell.get_text(" ", strip=True))
            if doctor_name and doctor_name in name_text:
                target_tr = tr
                break
        # 행을 못 찾으면 단일 의사 페이지일 가능성이 높으므로 첫 행 사용
        if target_tr is None:
            trs = tbody.find_all("tr", recursive=False)
            target_tr = trs[0] if trs else None
        if target_tr is None:
            return []

        tds = target_tr.find_all("td", recursive=False)
        if len(tds) < 2 + 2 * len(day_order):
            return []

        slot_tds = tds[2:]
        out: list[dict] = []
        for di, day_idx in enumerate(day_order):
            m_idx = di * 2
            a_idx = di * 2 + 1
            if a_idx >= len(slot_tds):
                break
            if self._is_active_cell(slot_tds[m_idx]):
                s, e = TIME_RANGES["morning"]
                out.append({
                    "day_of_week": day_idx, "time_slot": "morning",
                    "start_time": s, "end_time": e, "location": "",
                })
            if self._is_active_cell(slot_tds[a_idx]):
                s, e = TIME_RANGES["afternoon"]
                out.append({
                    "day_of_week": day_idx, "time_slot": "afternoon",
                    "start_time": s, "end_time": e, "location": "",
                })
        return out

    # ───────────────────── 의사 카드 / 상세 ─────────────────────

    def _parse_doctor_card(self, li, dept_code: str, dept_name: str) -> dict | None:
        """진료과 docList 의 li (gallery3_Wrap) 1개 파싱 — 시간표는 미포함."""
        cont = li.find("div", class_="cont")
        if cont is None:
            return None
        subj_el = cont.find("strong", class_="subject")
        if subj_el is None:
            return None
        subj_text = _clean(subj_el.get_text(" ", strip=True))
        # "[내분비내과] 김수경" 형태
        m = re.match(r"^\s*\[([^\]]+)\]\s*(.+?)\s*$", subj_text)
        if m:
            sub_dept = _clean(m.group(1))
            name = _clean(m.group(2))
        else:
            sub_dept = dept_name
            name = subj_text
        if not name:
            return None

        specialty = ""
        for p in cont.find_all("p"):
            t = _clean(p.get_text(" ", strip=True))
            if t.startswith("[진료분야]"):
                specialty = _clean(t.replace("[진료분야]", ""))
                break

        photo_url = ""
        img = li.find("img")
        if img and img.get("src"):
            src = img["src"]
            if src.startswith("http"):
                photo_url = src
            elif src.startswith("/"):
                photo_url = BASE_URL + src
            else:
                photo_url = f"{BASE_URL}/gnuh/treat/{src}"

        dno = ""
        for a in cont.find_all("a", href=True):
            mm = re.search(r"dno=(\d+)", a["href"])
            if mm:
                dno = mm.group(1)
                break
        if not dno:
            return None

        external_id = f"{self.hospital_code}-{dept_code}-{dno}"
        profile_url = DOC_INFO_URL_FMT.format(dept=dept_code, dno=dno)

        return {
            "staff_id": external_id,
            "external_id": external_id,
            "name": name,
            "department": sub_dept or dept_name,
            "position": "",
            "specialty": specialty,
            "profile_url": profile_url,
            "photo_url": photo_url,
            "notes": "",
            "schedules": [],
            "date_schedules": [],
            "_dept": dept_code,
            "_dno": dno,
        }

    async def _fetch_dept_doctors(self, dept_code: str, dept_name: str) -> list[dict]:
        url = DOC_LIST_URL_FMT.format(dept=dept_code)
        try:
            html = await _curl_get(url, referer=DEPT_LIST_URL)
        except Exception as e:
            logger.warning(f"[GNUH2] 의사목록 로드 실패 dept={dept_code}: {e}")
            return []

        soup = BeautifulSoup(html, "html.parser")
        doc_list = soup.find("ul", id="_docList")
        if doc_list is None:
            return []
        results: list[dict] = []
        for li in doc_list.find_all("li", recursive=False):
            try:
                doc = self._parse_doctor_card(li, dept_code, dept_name)
                if doc:
                    results.append(doc)
            except Exception as e:
                logger.debug(f"[GNUH2] 카드 파싱 오류 dept={dept_code}: {e}")
                continue
        return results

    @staticmethod
    def _extract_position_from_career(career_text: str) -> str:
        """주요경력 텍스트의 '현]' 라인에서 직위를 추출."""
        if not career_text:
            return ""
        for line in career_text.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("현]") or line.startswith("현 ]") or line.startswith("[현]"):
                # ex) "현] 경상대학교병원 내분비내과 기금교수"
                tail = line.split("]", 1)[-1].strip()
                # 마지막 토큰이 '...교수/전문의/임상강사' 류
                m = re.search(r"([가-힣A-Za-z]*(교수|전문의|임상강사|전임의|과장|소장|센터장|원장|부원장))", tail)
                if m:
                    return m.group(1)
                return tail.split()[-1] if tail else ""
        return ""

    async def _fetch_doctor_detail(self, doc: dict) -> dict:
        """개별 의사 상세(docInfo) 로드 → schedules / position / 보강."""
        dept = doc["_dept"]
        dno = doc["_dno"]
        url = DOC_INFO_URL_FMT.format(dept=dept, dno=dno)
        try:
            html = await _curl_get(url, referer=DOC_LIST_URL_FMT.format(dept=dept))
        except Exception as e:
            logger.warning(f"[GNUH2] 상세 로드 실패 {doc['external_id']}: {e}")
            return doc

        soup = BeautifulSoup(html, "html.parser")

        # 이름 / 진료과
        name_el = soup.find("h5", class_="doctor_name")
        if name_el:
            full_text = _clean(name_el.get_text(" ", strip=True))
            # "김수경 [내분비내과]"
            m = re.match(r"^(.+?)\s*\[([^\]]+)\]\s*$", full_text)
            if m:
                doc["name"] = _clean(m.group(1))
                doc["department"] = _clean(m.group(2))
            else:
                doc["name"] = full_text or doc["name"]

        # 전문진료분야
        for li in soup.find_all("li", class_="title"):
            label = _clean(li.find(text=True, recursive=False) or "")
            if "전문진료분야" in label:
                span = li.find("span")
                if span:
                    doc["specialty"] = _clean(span.get_text(" ", strip=True))
                break
        # 위 셀렉터가 안 잡히면 fallback
        if not doc.get("specialty"):
            for li in soup.select("ul li.title"):
                text = _clean(li.get_text(" ", strip=True))
                if "전문진료분야" in text:
                    doc["specialty"] = _clean(text.replace("전문진료분야", ""))
                    break

        # 직위 (주요경력)
        career_p = soup.find("p", id="eduCareerContents")
        if career_p:
            career_text = career_p.get_text("\n", strip=True)
            pos = self._extract_position_from_career(career_text)
            if pos:
                doc["position"] = pos

        # 시간표 — table.tbTypeB summary 에 '진료일정' 들어있는 것
        schedules: list[dict] = []
        for table in soup.find_all("table", class_="tbTypeB"):
            summary = (table.get("summary") or "")
            if "진료일정" in summary or "외래 진료" in summary or "진료시간" in summary:
                schedules = self._parse_doctor_row(table, doc.get("name", ""))
                if schedules:
                    break
        if not schedules:
            # caption fallback
            for table in soup.find_all("table"):
                cap = table.find("caption")
                cap_text = cap.get_text(" ", strip=True) if cap else ""
                if "외래 진료 시간표" in cap_text or "진료일정" in cap_text:
                    schedules = self._parse_doctor_row(table, doc.get("name", ""))
                    if schedules:
                        break
        doc["schedules"] = schedules
        doc["profile_url"] = url

        # 사진 url 갱신 (큰 사이즈)
        prof_img = soup.select_one("div.profile div.photo img")
        if prof_img and prof_img.get("src"):
            src = prof_img["src"]
            if src.startswith("/"):
                doc["photo_url"] = BASE_URL + src
            elif src.startswith("http"):
                doc["photo_url"] = src
            else:
                doc["photo_url"] = f"{BASE_URL}/gnuh/treat/{src}"

        return doc

    # ───────────────────── 전체 크롤링 ─────────────────────

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        dept_map = await self._fetch_dept_map()
        if not dept_map:
            self._cached_data = []
            return self._cached_data

        dept_sem = asyncio.Semaphore(_DEPT_SEM_LIMIT)
        doc_sem = asyncio.Semaphore(_DOC_SEM_LIMIT)

        async def _dept_job(code: str, name: str) -> list[dict]:
            async with dept_sem:
                return await self._fetch_dept_doctors(code, name)

        dept_tasks = [_dept_job(c, n) for c, n in dept_map.items()]
        dept_results = await asyncio.gather(*dept_tasks, return_exceptions=True)

        all_docs: dict[str, dict] = {}
        flat: list[dict] = []
        for res in dept_results:
            if isinstance(res, Exception):
                logger.warning(f"[GNUH2] 진료과 크롤링 예외: {res}")
                continue
            for doc in res:
                eid = doc["external_id"]
                if eid not in all_docs:
                    all_docs[eid] = doc
                    flat.append(doc)

        async def _detail_job(d: dict):
            async with doc_sem:
                try:
                    return await self._fetch_doctor_detail(d)
                except Exception as e:
                    logger.warning(f"[GNUH2] 상세 예외 {d.get('external_id')}: {e}")
                    return d

        await asyncio.gather(*[_detail_job(d) for d in flat])

        result_list = list(all_docs.values())
        # 노출 직전 내부키 제거 + 빈 schedules 도 그대로 둠
        for d in result_list:
            d.pop("_dept", None)
            d.pop("_dno", None)
        self._cached_data = result_list
        logger.info(f"[GNUH2] 총 의사 {len(result_list)}명 수집")
        return result_list

    # ───────────────────── 표준 인터페이스 ─────────────────────

    async def get_departments(self) -> list[dict]:
        dept_map = await self._fetch_dept_map()
        return [{"code": c, "name": n} for c, n in dept_map.items()]

    async def crawl_doctor_list(self, department: str | None = None) -> list[dict]:
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d.get("department") == department]
        return [
            {
                "staff_id": d["staff_id"],
                "external_id": d["external_id"],
                "name": d["name"],
                "department": d.get("department", ""),
                "position": d.get("position", ""),
                "specialty": d.get("specialty", ""),
                "profile_url": d.get("profile_url", ""),
                "photo_url": d.get("photo_url", ""),
                "notes": d.get("notes", ""),
            }
            for d in data
        ]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 의사 1명만 네트워크 조회 — _fetch_all 호출 금지.

        external_id 포맷: GNUH2-{dept}-{dno}
        """
        empty = {
            "staff_id": staff_id,
            "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "photo_url": "",
            "notes": "",
            "schedules": [], "date_schedules": [],
        }

        # 동일 인스턴스 캐시 우선
        if self._cached_data is not None:
            for d in self._cached_data:
                if d.get("staff_id") == staff_id or d.get("external_id") == staff_id:
                    return {
                        "staff_id": staff_id,
                        "name": d.get("name", ""),
                        "department": d.get("department", ""),
                        "position": d.get("position", ""),
                        "specialty": d.get("specialty", ""),
                        "profile_url": d.get("profile_url", ""),
                        "photo_url": d.get("photo_url", ""),
                        "notes": d.get("notes", ""),
                        "schedules": d.get("schedules", []),
                        "date_schedules": d.get("date_schedules", []),
                    }
            return empty

        prefix = f"{self.hospital_code}-"
        raw = staff_id[len(prefix):] if staff_id.startswith(prefix) else staff_id
        parts = raw.split("-", 1)
        if len(parts) != 2 or not parts[0] or not parts[1]:
            logger.warning(f"[GNUH2] external_id 형식 오류: {staff_id}")
            return empty
        dept_code, dno = parts[0], parts[1]

        # 1명 조회 — docInfo 만 호출
        seed = {
            "staff_id": staff_id,
            "external_id": staff_id,
            "name": "",
            "department": "",
            "position": "",
            "specialty": "",
            "profile_url": DOC_INFO_URL_FMT.format(dept=dept_code, dno=dno),
            "photo_url": "",
            "notes": "",
            "schedules": [],
            "date_schedules": [],
            "_dept": dept_code,
            "_dno": dno,
        }
        try:
            updated = await self._fetch_doctor_detail(seed)
        except Exception as e:
            logger.error(f"[GNUH2] 개별 조회 실패 {staff_id}: {e}")
            return empty

        return {
            "staff_id": staff_id,
            "name": updated.get("name", ""),
            "department": updated.get("department", ""),
            "position": updated.get("position", ""),
            "specialty": updated.get("specialty", ""),
            "profile_url": updated.get("profile_url", ""),
            "photo_url": updated.get("photo_url", ""),
            "notes": updated.get("notes", ""),
            "schedules": updated.get("schedules", []),
            "date_schedules": [],
        }

    async def crawl_doctors(self, department: str | None = None):
        from app.schemas.schemas import CrawlResult, CrawledDoctor

        data = await self._fetch_all()
        if department:
            data = [d for d in data if d.get("department") == department]

        doctors = [
            CrawledDoctor(
                name=d["name"],
                department=d.get("department", ""),
                position=d.get("position", ""),
                specialty=d.get("specialty", ""),
                profile_url=d.get("profile_url", ""),
                photo_url=d.get("photo_url", ""),
                external_id=d["external_id"],
                notes=d.get("notes", ""),
                schedules=d.get("schedules", []),
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
