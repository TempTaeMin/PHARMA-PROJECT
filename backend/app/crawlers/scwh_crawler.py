"""성균관대학교 삼성창원병원 (SCWH) 크롤러

도메인: smc.skku.edu (성균관대 의대 시스템 — KBSMC/SMC 와는 별도 인프라)

페이지/엔드포인트:
  진료과 목록:        GET  /smc/medical/intro.do?mId=100
                      → fn_goLink('XX') 의 XX (medDept 코드) + 진료과명 추출
  진료과별 의사 목록:  POST /smc/medical/medView.do?mId=100
                      → form data: medDept={dept_code}
                      → 카드별: medDrSeq, 이름, 직위, 진료분야, 주간 시간표 테이블
  의사 상세 (월간):    POST /doctor/main/main.do?mId=1
                      → form data: medDrSeq={N}
                      → 당월(현재월) 일별 진료일정 캘린더 포함

- `schedules`(요일 패턴): 진료과 페이지의 doctor-schdule-table 에서 파싱.
- `date_schedules`(일별): 의사 상세 페이지의 schdule-table 에서 당월 1개월치만 파싱
   (next-month AJAX 는 캘린더 헤더만 반환하고 스케줄 셀은 반환하지 않아 1개월 한계).
- 활성 셀 마크: dept page = `<span class="on">`, detail page = `<span class="icon reservation"></span>`
- 회색(예약마감) 셀: `<span class="icon reservation gray"></span>` — 진료는 있지만 마감.
"""
import re
import asyncio
import logging
from datetime import datetime, timedelta

import httpx
from bs4 import BeautifulSoup

from app.crawlers._schedule_rules import is_clinic_cell

logger = logging.getLogger(__name__)

BASE_URL = "https://smc.skku.edu"
TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

# dept page 표 헤더: 구분 | 월 | 화 | 수 | 목 | 금 | 토
DAY_HEADERS = ["월", "화", "수", "목", "금", "토"]
DAY_INDEX = {h: i for i, h in enumerate(DAY_HEADERS)}

# 한글 요일 → 0=월 ~ 6=일 (detail page 의 yoil 매핑)
KOR_DOW = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}


class ScwhCrawler:
    """성균관대학교 삼성창원병원 크롤러"""

    def __init__(self):
        self.hospital_code = "SCWH"
        self.hospital_name = "성균관대학교 삼성창원병원"
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Referer": f"{BASE_URL}/smc/medical/intro.do?mId=100",
        }
        self._cached_data = None
        self._cached_depts = None

    # ─── 진료과 목록 ────────────────────────────────────────────────────────────

    async def _fetch_departments(self) -> list[dict]:
        if self._cached_depts is not None:
            return self._cached_depts

        url = f"{BASE_URL}/smc/medical/intro.do?mId=100"
        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False
        ) as client:
            try:
                resp = await client.get(url)
                resp.raise_for_status()
            except Exception as e:
                logger.error(f"[SCWH] 진료과 목록 실패: {e}")
                self._cached_depts = []
                return []

        text = resp.content.decode("utf-8", errors="replace")
        # fn_goLink('IG') 와 같은 onclick 핸들러에서 진료과 코드 추출
        # 같은 카드 내 <strong>진료과명</strong> 도 함께
        depts = []
        seen = set()
        # 카드 단위로 파싱
        soup = BeautifulSoup(text, "html.parser")
        for area in soup.select("div.index-department-area"):
            a = area.find("a", onclick=True)
            if not a:
                continue
            m = re.search(r"fn_goLink\(\s*['\"]([A-Za-z0-9]+)['\"]", a.get("onclick", ""))
            if not m:
                continue
            code = m.group(1)
            if code in seen:
                continue
            seen.add(code)
            strong = area.find("strong")
            name = strong.get_text(strip=True) if strong else f"진료과{code}"
            depts.append({"code": code, "name": name})

        logger.info(f"[SCWH] 진료과 {len(depts)}개")
        self._cached_depts = depts
        return depts

    # ─── 진료과별 의사 목록 + 주간 스케줄 ──────────────────────────────────────

    async def _fetch_dept_doctors(
        self, client: httpx.AsyncClient, dept_code: str, dept_name: str
    ) -> list[dict]:
        url = f"{BASE_URL}/smc/medical/medView.do?mId=100"
        try:
            resp = await client.post(url, data={"medDept": dept_code})
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[SCWH] {dept_name}({dept_code}) 의사 목록 실패: {e}")
            return []

        text = resp.content.decode("utf-8", errors="replace")
        soup = BeautifulSoup(text, "html.parser")

        doctors: list[dict] = []
        for card in soup.select("div.doctor-information-wrapper"):
            info = card.select_one("div.doctor-information")
            if not info:
                continue

            # 이름 + 직위
            name_el = info.find("strong", attrs={"onclick": True}) or info.find("strong")
            if not name_el:
                continue
            # 이름 = <span class="point-color03">이름</span>, 그 뒤 텍스트 = 직위
            name_span = name_el.find("span")
            name = name_span.get_text(strip=True) if name_span else ""
            if not name:
                # fallback: strong 전체에서 한글 2~5자 추출
                full = name_el.get_text(" ", strip=True)
                mm = re.match(r"([가-힣]{2,5})", full)
                if mm:
                    name = mm.group(1)
            if not name:
                continue

            # 직위: strong 의 마지막 텍스트 노드 (이름 뒤)
            position = ""
            pos_text = name_el.get_text(" ", strip=True)
            if name and pos_text.startswith(name):
                position = pos_text[len(name):].strip()
            position = position[:30]

            # medDrSeq 추출 — onclick="fn_goDtl('39'); return false;"
            med_seq = ""
            for el in info.find_all(attrs={"onclick": True}):
                onc = el.get("onclick", "")
                m = re.search(r"fn_goDtl\(\s*['\"](\d+)['\"]", onc)
                if m:
                    med_seq = m.group(1)
                    break
            if not med_seq:
                # btn-reservation: fn_goRsrvByDr('IG', '39', 'N')
                for el in info.find_all(attrs={"onclick": True}):
                    onc = el.get("onclick", "")
                    m = re.search(
                        r"fn_goRsrvByDr\(\s*['\"][^'\"]*['\"]\s*,\s*['\"](\d+)['\"]",
                        onc,
                    )
                    if m:
                        med_seq = m.group(1)
                        break
            if not med_seq:
                continue

            # 진료분야 (specialty)
            specialty = ""
            for dl in info.find_all("dl"):
                dt = dl.find("dt")
                if dt and "진료분야" in dt.get_text(strip=True):
                    dd = dl.find("dd")
                    if dd:
                        # "더보기" 버튼 제거
                        for btn in dd.find_all("button"):
                            btn.decompose()
                        specialty = dd.get_text(" ", strip=True)
                    break

            # 주간 스케줄 (doctor-schdule-table)
            schedules = self._parse_weekly_table(card)

            ext_id = f"SCWH-{med_seq}"
            doctors.append({
                "staff_id": ext_id,
                "external_id": ext_id,
                "name": name,
                "department": dept_name,
                "position": position or "교수",
                "specialty": specialty,
                "profile_url": f"{BASE_URL}/doctor/main/main.do?mId=1&medDrSeq={med_seq}",
                "notes": "",
                "schedules": schedules,
                "date_schedules": [],
                "_med_seq": med_seq,
                "_dept_code": dept_code,
            })

        logger.info(f"[SCWH] {dept_name}: {len(doctors)}명")
        return doctors

    @staticmethod
    def _parse_weekly_table(card_soup) -> list[dict]:
        """진료과 페이지 카드 내 doctor-schdule-table 에서 요일별 오전/오후 스케줄 추출.

        구조:
          thead: 구분 | 월 | 화 | 수 | 목 | 금 | 토
          tbody:
            <tr><th>오전</th> <td>...</td> ...</tr>
            <tr><th>오후</th> <td>...</td> ...</tr>
          활성 셀: <span class="on"></span>  또는 텍스트(예약/검진 등)
          비활성: 빈 td 또는 "순번" 같은 텍스트 (외래 진료 아님)
        """
        out: list[dict] = []
        tbl = card_soup.select_one("div.doctor-schdule-table table")
        if not tbl:
            return out

        # 헤더에서 요일 컬럼 매핑
        header_cells = []
        thead = tbl.find("thead")
        if thead:
            ths = thead.find_all("th")
            header_cells = [th.get_text(strip=True) for th in ths]
        # header_cells[0] == "구분", header_cells[1..6] == 월~토

        col_to_dow: dict[int, int] = {}
        for ci, htxt in enumerate(header_cells):
            for kor, dow in KOR_DOW.items():
                if dow > 5:
                    continue
                if kor == htxt:
                    col_to_dow[ci] = dow
                    break
        if not col_to_dow:
            # fallback: 표준 순서 가정
            for i in range(6):
                col_to_dow[i + 1] = i

        tbody = tbl.find("tbody")
        if not tbody:
            return out

        for tr in tbody.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            if not cells:
                continue
            slot_text = cells[0].get_text(strip=True)
            if "오전" in slot_text:
                slot = "morning"
            elif "오후" in slot_text:
                slot = "afternoon"
            else:
                continue

            for ci, cell in enumerate(cells):
                if ci == 0:
                    continue
                if ci not in col_to_dow:
                    continue

                # 활성 마크
                has_on = cell.select_one("span.on") is not None
                cell_text = cell.get_text(" ", strip=True)
                cell_text = re.sub(r"\s+", " ", cell_text)

                # 빈 셀이면 skip
                if not has_on and not cell_text:
                    continue

                # is_clinic_cell 로 텍스트 판정 (마크 단독으로도 충분)
                # "순번"(접수 순번제) 은 외래 진료가 아니므로 제외
                if cell_text and not has_on:
                    if not is_clinic_cell(cell_text):
                        # "순번" 같은 텍스트는 외래 아님
                        continue

                start, end = TIME_RANGES[slot]
                out.append({
                    "day_of_week": col_to_dow[ci],
                    "time_slot": slot,
                    "start_time": start,
                    "end_time": end,
                    "location": "",
                })

        # dedup
        seen = set()
        unique = []
        for s in out:
            key = (s["day_of_week"], s["time_slot"])
            if key not in seen:
                seen.add(key)
                unique.append(s)
        return unique

    # ─── 의사 상세 페이지에서 당월 일별 스케줄 ────────────────────────────────

    async def _fetch_doctor_detail(
        self, client: httpx.AsyncClient, med_seq: str
    ) -> dict:
        """의사 상세 페이지에서 (이름/직위/진료분야/당월 date_schedules) 추출."""
        url = f"{BASE_URL}/doctor/main/main.do?mId=1"
        try:
            resp = await client.post(url, data={"medDrSeq": med_seq})
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[SCWH] 상세페이지 실패 (medDrSeq={med_seq}): {e}")
            return {"name": "", "position": "", "specialty": "", "date_schedules": []}

        text = resp.content.decode("utf-8", errors="replace")
        soup = BeautifulSoup(text, "html.parser")

        # 이름/직위
        name = ""
        position = ""
        h2 = soup.select_one("div.doctor-information-area h2 strong")
        if h2:
            full = h2.get_text(" ", strip=True)
            mm = re.match(r"([가-힣]{2,5})\s*(.*)", full)
            if mm:
                name = mm.group(1)
                position = mm.group(2).strip()

        # 진료분야
        specialty = ""
        for dl in soup.select("div.doctor-information-area dl"):
            dt = dl.find("dt")
            if dt and "진료분야" in dt.get_text(strip=True):
                dd = dl.find("dd")
                if dd:
                    specialty = dd.get_text(" ", strip=True)
                break

        # 당월 정보 추출
        # JS 의 var year=YYYY; var month=MM; 에서 추출
        year_m = re.search(r"var\s+year\s*=\s*(\d+)", text)
        month_m = re.search(r"var\s+month\s*=\s*(\d+)", text)
        if year_m and month_m:
            cur_year = int(year_m.group(1))
            cur_month = int(month_m.group(1))
        else:
            now = datetime.now()
            cur_year = now.year
            cur_month = now.month

        # 캘린더 테이블 #tb 에서 일별 셀 파싱
        date_schedules: list[dict] = []
        tb = soup.find("table", id="tb")
        if tb:
            thead = tb.find("thead")
            tbody = tb.find("tbody")
            day_cols: list[int] = []
            if thead:
                # 첫 th = "날짜", 그 다음 each th 에 <strong>DD</strong>
                ths = thead.find_all("th")
                for th in ths[1:]:
                    strong = th.find("strong")
                    if strong:
                        day_str = strong.get_text(strip=True)
                        try:
                            day_cols.append(int(day_str))
                        except ValueError:
                            day_cols.append(0)
                    else:
                        day_cols.append(0)
            if tbody and day_cols:
                for tr in tbody.find_all("tr"):
                    cells = tr.find_all(["th", "td"])
                    if not cells:
                        continue
                    slot_text = cells[0].get_text(strip=True)
                    if "오전" in slot_text:
                        slot = "morning"
                    elif "오후" in slot_text:
                        slot = "afternoon"
                    else:
                        continue
                    for ci, cell in enumerate(cells[1:]):
                        if ci >= len(day_cols):
                            break
                        day_num = day_cols[ci]
                        if day_num <= 0:
                            continue
                        # 활성 마크: <span class="icon reservation"></span>
                        # 회색 마크: <span class="icon reservation gray"></span>
                        icons = cell.select("span.icon.reservation")
                        if not icons:
                            continue
                        has_clinic = False
                        status = "진료"
                        for ic in icons:
                            classes = ic.get("class") or []
                            if "gray" in classes:
                                has_clinic = True
                                status = "마감"
                            else:
                                has_clinic = True
                                status = "진료"
                                break  # 활성이 우선
                        if not has_clinic:
                            continue
                        try:
                            sd = datetime(cur_year, cur_month, day_num).strftime("%Y-%m-%d")
                        except ValueError:
                            continue
                        start, end = TIME_RANGES[slot]
                        date_schedules.append({
                            "schedule_date": sd,
                            "time_slot": slot,
                            "start_time": start,
                            "end_time": end,
                            "location": "",
                            "status": status,
                        })

        return {
            "name": name,
            "position": position,
            "specialty": specialty,
            "date_schedules": date_schedules,
        }

    # ─── 전체 크롤링 ──────────────────────────────────────────────────────────

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        depts = await self._fetch_departments()
        all_doctors: dict[str, dict] = {}

        async with httpx.AsyncClient(
            headers=self.headers, timeout=60, follow_redirects=True, verify=False
        ) as client:
            # 1) 부서별 의사 카드 + 주간 스케줄 수집
            for dept in depts:
                docs = await self._fetch_dept_doctors(client, dept["code"], dept["name"])
                for doc in docs:
                    ext = doc["external_id"]
                    if ext in all_doctors:
                        # 동일 의사 다른 진료과 — specialty 병합
                        existing = all_doctors[ext]
                        if doc["specialty"] and doc["specialty"] not in (existing.get("specialty") or ""):
                            existing["specialty"] = (
                                f"{existing['specialty']}, {doc['specialty']}"
                                if existing.get("specialty") else doc["specialty"]
                            )
                        continue
                    all_doctors[ext] = doc

            # 2) 의사별 상세페이지에서 date_schedules 병렬 수집
            sem = asyncio.Semaphore(8)

            async def fetch_detail(doc: dict):
                med_seq = doc.get("_med_seq", "")
                if not med_seq:
                    return
                async with sem:
                    try:
                        info = await self._fetch_doctor_detail(client, med_seq)
                        # 이름 보정 (dept 페이지에서 이미 가져왔지만 비어있으면)
                        if not doc.get("name") and info.get("name"):
                            doc["name"] = info["name"]
                        if info.get("position") and not doc.get("position"):
                            doc["position"] = info["position"]
                        if info.get("specialty") and not doc.get("specialty"):
                            doc["specialty"] = info["specialty"]
                        doc["date_schedules"] = info.get("date_schedules", [])
                    except Exception as e:
                        logger.warning(
                            f"[SCWH] {doc.get('name','')} 상세 실패: {e}"
                        )

            await asyncio.gather(*(fetch_detail(d) for d in all_doctors.values()))

        result = list(all_doctors.values())
        logger.info(f"[SCWH] 총 {len(result)}명")
        self._cached_data = result
        return result

    # ─── 공개 인터페이스 ──────────────────────────────────────────────────────

    async def get_departments(self) -> list[dict]:
        depts = await self._fetch_departments()
        return [{"code": d["code"], "name": d["name"]} for d in depts]

    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]
        return [
            {
                "staff_id": d["staff_id"],
                "external_id": d["external_id"],
                "name": d["name"],
                "department": d["department"],
                "position": d.get("position", ""),
                "specialty": d.get("specialty", ""),
                "profile_url": d.get("profile_url", ""),
                "notes": d.get("notes", ""),
            }
            for d in data
        ]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 교수 진료시간 조회 — 해당 교수 1명만 네트워크 요청.

        external_id 포맷: SCWH-{med_seq}
        med_seq 만으로 detail 페이지 + 주간 스케줄을 얻을 수 있다.
        단, 주간 스케줄은 dept 페이지에서만 제공되므로 detail 에서 date_schedules
        를 가져오고, 거기서 요일 패턴을 역산한다.
        """
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }

        # 동일 인스턴스 내 캐시 활용
        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return self._to_schedule_dict(d)
            return empty

        prefix = f"{self.hospital_code}-"
        med_seq = staff_id.replace(prefix, "") if staff_id.startswith(prefix) else staff_id
        med_seq = med_seq.split("-", 1)[0]
        if not med_seq.isdigit():
            return empty

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False
        ) as client:
            try:
                info = await self._fetch_doctor_detail(client, med_seq)
            except Exception as e:
                logger.error(f"[SCWH] 개별 조회 실패 {staff_id}: {e}")
                return empty

        # 주간 패턴 역산: date_schedules 의 (요일,슬롯) 집합
        weekly = []
        seen = set()
        for ds in info.get("date_schedules", []):
            try:
                dt = datetime.strptime(ds["schedule_date"], "%Y-%m-%d")
            except Exception:
                continue
            dow = dt.weekday()
            if dow > 5:
                continue
            slot = ds.get("time_slot", "")
            key = (dow, slot)
            if key in seen:
                continue
            seen.add(key)
            start, end = TIME_RANGES.get(slot, ("09:00", "12:00"))
            weekly.append({
                "day_of_week": dow,
                "time_slot": slot,
                "start_time": start,
                "end_time": end,
                "location": "",
            })

        return {
            "staff_id": staff_id,
            "name": info.get("name", ""),
            "department": "",
            "position": info.get("position", ""),
            "specialty": info.get("specialty", ""),
            "profile_url": f"{BASE_URL}/doctor/main/main.do?mId=1&medDrSeq={med_seq}",
            "notes": "",
            "schedules": weekly,
            "date_schedules": info.get("date_schedules", []),
        }

    @staticmethod
    def _to_schedule_dict(d: dict) -> dict:
        return {
            "staff_id": d["staff_id"],
            "name": d["name"],
            "department": d["department"],
            "position": d.get("position", ""),
            "specialty": d.get("specialty", ""),
            "profile_url": d.get("profile_url", ""),
            "notes": d.get("notes", ""),
            "schedules": d.get("schedules", []),
            "date_schedules": d.get("date_schedules", []),
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
