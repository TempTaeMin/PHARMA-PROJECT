"""중앙대병원 크롤러

HTML 파싱 기반 크롤러 (JSON API 없음).
페이지:
  진료과 목록: GET /home/medical/deptAllIntro.do → deptNo 파싱
  의료진 목록: POST /home/medical/profList.do (deptNo 파라미터) → 의사 카드 + 스케줄 테이블 파싱
  의료진 상세: GET /home/medical/profView.do?deptNo=X&profNo=Y&empNo=Z

스케줄 테이블 구조 (profList 내 doctor card):
  행: 오전 / 오후
  열: 월 화 수 목 금 토
  진료 표시: <img ...ico_cir_col05.png> 또는 <img ...ico_outpatient.png> 아이콘 존재 시 진료
"""
import re
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://ch.cauhs.or.kr"
TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}
DAY_CHAR_MAP = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5}


class CauCrawler:
    def __init__(self):
        self.hospital_code = "CAU"
        self.hospital_name = "중앙대병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Referer": BASE_URL,
        }
        self._cached_data = None
        self._cached_depts = None

    # ─── 진료과 목록 ───

    async def _fetch_departments(self):
        """진료과 목록을 deptAllIntro 페이지에서 파싱"""
        if self._cached_depts is not None:
            return self._cached_depts
        async with httpx.AsyncClient(headers=self.headers, timeout=30, follow_redirects=True) as client:
            try:
                resp = await client.get(f"{BASE_URL}/home/medical/deptAllIntro.do")
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")

                depts = []
                seen = set()

                # deptProf{deptNo}.do 또는 deptIntro{deptNo}.do 패턴 링크에서 deptNo 추출
                for a_tag in soup.select("a[href]"):
                    href = a_tag.get("href", "")
                    name = a_tag.get_text(strip=True)

                    # /home/medical/deptProf220.do 또는 deptIntro220.do 패턴
                    m = re.search(r'deptProf(\d+)\.do|deptIntro(\d+)\.do', href)
                    if m and name:
                        dept_no = m.group(1) or m.group(2)
                        if dept_no not in seen:
                            seen.add(dept_no)
                            # 이름에서 불필요한 텍스트 제거
                            clean_name = re.sub(r'\s+', ' ', name).strip()
                            if clean_name and len(clean_name) <= 20:
                                depts.append({"code": dept_no, "name": clean_name})

                    # deptNo= 파라미터 패턴도 확인
                    m2 = re.search(r'deptNo=(\d+)', href)
                    if m2 and name:
                        dept_no = m2.group(1)
                        if dept_no not in seen:
                            seen.add(dept_no)
                            clean_name = re.sub(r'\s+', ' ', name).strip()
                            if clean_name and len(clean_name) <= 20:
                                depts.append({"code": dept_no, "name": clean_name})

                # 폴백: 알려진 진료과 목록 (deptAllIntro는 카테고리만 표시)
                if len(depts) < 10:
                    known_depts = [
                        ("190", "가정의학과"), ("191", "감염내과"), ("192", "구강악안면외과"),
                        ("193", "내분비내과"), ("195", "류마티스내과"), ("196", "마취통증의학과"),
                        ("197", "응급의학과"), ("198", "이비인후과"), ("200", "방사선종양학과"),
                        ("201", "재활의학과"), ("202", "정신건강의학과"), ("203", "정형외과"),
                        ("204", "중환자의학과"), ("205", "진단검사의학과"), ("206", "치과보철과"),
                        ("207", "병리과"), ("208", "치과교정과"), ("209", "치과보존과"),
                        ("210", "비뇨의학과"), ("211", "피부과"), ("212", "핵의학과"),
                        ("213", "산부인과"), ("214", "혈액종양내과"), ("215", "호흡기알레르기내과"),
                        ("216", "성형외과"), ("217", "소아청소년과"), ("218", "심장혈관흉부외과"),
                        ("219", "소화기내과"), ("220", "순환기내과"), ("221", "신경과"),
                        ("222", "신경외과"), ("223", "신장내과"), ("224", "안과"),
                        ("225", "영상의학과"), ("226", "외과"), ("425", "치주과"),
                    ]
                    depts = [{"code": c, "name": n} for c, n in known_depts]

                logger.info(f"[CAU] 진료과 {len(depts)}개")
                self._cached_depts = depts
                return depts
            except Exception as e:
                logger.error(f"[CAU] 진료과 실패: {e}")
                self._cached_depts = []
                return []

    # ─── 의료진 목록 (페이지별 파싱) ───

    async def _fetch_prof_list_page(self, client: httpx.AsyncClient, dept_code: str = None, page: int = 1) -> tuple[list[dict], int]:
        """profList.do 페이지에서 의사 카드 파싱. (doctors, total_pages) 반환"""
        try:
            form_data = {
                "sitePath": "home",
                "page": str(page),
                "list_show_cnt": "10",
                "sortOrder": "HAN",
                "searchYn": "Y",
                "cate1": "",
                "deptNo": dept_code or "",
                "deptNm": "",
                "tabCd": "",
                "publicYear": "",
                "prevYearYn": "",
                "workType": "",
                "initialText": "",
                "profInitKorNm": "",
                "searchfield": "",
                "searchword": "",
            }

            resp = await client.post(
                f"{BASE_URL}/home/medical/profList.do",
                data=form_data,
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            logger.error(f"[CAU] profList 페이지 {page} 실패: {e}")
            return [], 0

        doctors = []

        # 의사 카드 파싱: fn_DeatilPop('home', deptNo, profNo, empNo) 패턴
        # 의사 카드에는 이름, 진료과, 전문분야, 스케줄 테이블이 포함됨
        html_text = str(soup)

        # fn_DeatilPop 호출에서 의사 ID 추출
        detail_pattern = re.compile(
            r"fn_DeatilPop\s*\(\s*'([^']*)'\s*,\s*'?(\d+)'?\s*,\s*'?(\d+)'?\s*,\s*'?(\w+)'?\s*\)"
        )

        # fn_DeatilPop 호출 모두 찾기
        detail_calls = detail_pattern.findall(html_text)

        if not detail_calls:
            # 대체 패턴: fn_DeatilPop(sitePath, deptNo, profNo, empNo)
            detail_pattern2 = re.compile(
                r"fn_DeatilPop\s*\([^)]*?(\d+)[^)]*?(\d+)[^)]*?(\w+)\s*\)"
            )
            for m in detail_pattern2.finditer(html_text):
                detail_calls.append(("home", m.group(1), m.group(2), m.group(3)))

        # fn_DeatilPop 호출이 포함된 <a> 태그의 부모 컨테이너에서 의사 정보 추출
        for site_path, dept_no, prof_no, emp_no in detail_calls:
            doctor = self._parse_doctor_from_page(soup, dept_no, prof_no, emp_no)
            if doctor:
                doctors.append(doctor)

        # 전체 페이지 수 계산
        total_pages = 1
        page_links = soup.select("a[href*='G_MovePage']")
        for link in page_links:
            href = link.get("href", "") + link.get("onclick", "")
            m = re.search(r'G_MovePage\s*\(\s*(\d+)\s*\)', href)
            if m:
                p = int(m.group(1))
                if p > total_pages:
                    total_pages = p

        # 페이지네이션 텍스트에서도 확인
        for el in soup.select(".paging, .pagination, nav"):
            text = el.get_text()
            nums = re.findall(r'\d+', text)
            for n in nums:
                p = int(n)
                if p > total_pages and p < 100:
                    total_pages = p

        return doctors, total_pages

    def _parse_doctor_card(self, card, detail_info: tuple = None) -> dict | None:
        """의사 카드 HTML에서 정보 추출"""
        name = ""
        dept_name = ""
        position = ""
        specialty = ""
        dept_no = ""
        prof_no = ""
        emp_no = ""

        if detail_info:
            _, dept_no, prof_no, emp_no = detail_info

        # 이름 추출
        for sel in ("h4", "h3", "strong.name", "span.name", "a.name"):
            el = card.select_one(sel)
            if el:
                name = el.get_text(strip=True)
                if name and len(name) <= 10:
                    break
                name = ""

        # 진료과 추출
        for sel in ("h5", "span.dept", "p.dept"):
            el = card.select_one(sel)
            if el:
                dept_name = el.get_text(strip=True)
                if dept_name and "전문분야" not in dept_name:
                    break
                dept_name = ""

        # 전문분야 추출
        spec_section = card.select_one("div.specialties p, div.specialty p, p.specialty")
        if spec_section:
            specialty = spec_section.get_text(strip=True)

        # 스케줄 파싱
        schedules = self._parse_schedule_table(card)

        if not name:
            return None

        ext_id = f"CAU-{emp_no}" if emp_no else f"CAU-{prof_no}" if prof_no else f"CAU-{name}"
        return {
            "staff_id": ext_id,
            "external_id": ext_id,
            "name": name,
            "department": dept_name,
            "position": position,
            "specialty": specialty,
            "profile_url": f"{BASE_URL}/home/medical/profView.do?deptNo={dept_no}&profNo={prof_no}&empNo={emp_no}" if prof_no else "",
            "notes": "",
            "schedules": schedules,
            "dept_no": dept_no,
            "prof_no": prof_no,
            "emp_no": emp_no,
        }

    def _parse_doctor_from_page(self, soup, dept_no: str, prof_no: str, emp_no: str) -> dict | None:
        """fn_DeatilPop 호출이 포함된 링크의 부모 컨테이너에서 의사 정보 + 스케줄 추출"""
        # fn_DeatilPop 호출이 포함된 <a> 태그 찾기
        for a_tag in soup.select("a"):
            href_text = a_tag.get("href", "") + a_tag.get("onclick", "")
            if prof_no not in href_text or emp_no not in href_text:
                continue
            if "fn_DeatilPop" not in href_text:
                continue

            # 이 링크의 부모 컨테이너 찾기
            # fn_DeatilPop 링크는 ul.doc_sche_btn_wrap > li 안에 있으므로
            # 가장 가까운 li가 아닌 li.doc_sche_list를 찾아야 함
            card = a_tag.find_parent("li", class_=re.compile(r"doc_sche|doctor|prof|card"))
            if not card:
                # li 두 단계: fn_DeatilPop의 li → ul → li.doc_sche_list
                inner_li = a_tag.find_parent("li")
                if inner_li:
                    card = inner_li.find_parent("li") or inner_li.find_parent("div", class_=re.compile(r"doc_|doctor|prof"))
            if not card:
                card = a_tag.find_parent("div", class_=re.compile(r"doc_|doctor|prof")) or a_tag.find_parent("tr")
            if not card:
                card = a_tag.parent

            # 이름 추출: h4 (실제 HTML: <div class="doc_name"><h4>강기운</h4>)
            name = ""
            if card:
                h4 = card.select_one("div.doc_name h4, h4")
                if h4:
                    name = h4.get_text(strip=True)

            # 이름 폴백: img alt (e.g. "강기운 이미지")
            if not name and card:
                img = card.select_one("img[alt]")
                if img:
                    alt = img.get("alt", "").strip()
                    alt_clean = re.sub(r'\s*(이미지|교수|전문의|과장|원장)$', '', alt).strip()
                    if alt_clean and 2 <= len(alt_clean) <= 10 and re.search(r'[가-힣]', alt_clean):
                        name = alt_clean

            # 진료과: h5.doc_part (e.g. "[순환기내과]")
            dept_name = ""
            if card:
                dept_el = card.select_one("h5.doc_part")
                if dept_el:
                    dept_name = dept_el.get_text(strip=True).strip("[]")

            # 전문분야: h5.doc_explain
            specialty = ""
            if card:
                spec_el = card.select_one("h5.doc_explain")
                if spec_el:
                    specialty = spec_el.get_text(strip=True)

            # 스케줄: 카드 내 테이블에서 파싱
            schedules = self._parse_schedule_table(card) if card else []

            ext_id = f"CAU-{emp_no}" if emp_no else f"CAU-{prof_no}" if prof_no else f"CAU-{name}"
            return {
                "staff_id": ext_id,
                "external_id": ext_id,
                "name": name,
                "department": dept_name,
                "position": "",
                "specialty": specialty,
                "profile_url": f"{BASE_URL}/home/medical/profView.do?deptNo={dept_no}&profNo={prof_no}&empNo={emp_no}" if prof_no else "",
                "notes": "",
                "schedules": schedules,
                "dept_no": dept_no,
                "prof_no": prof_no,
                "emp_no": emp_no,
            }

        # 링크를 찾지 못한 경우 기본 정보만 반환
        ext_id = f"CAU-{emp_no}" if emp_no else f"CAU-{prof_no}"
        return {
            "staff_id": ext_id,
            "external_id": ext_id,
            "name": "",
            "department": "",
            "position": "",
            "specialty": "",
            "profile_url": f"{BASE_URL}/home/medical/profView.do?deptNo={dept_no}&profNo={prof_no}&empNo={emp_no}",
            "notes": "",
            "schedules": [],
            "dept_no": dept_no,
            "prof_no": prof_no,
            "emp_no": emp_no,
        }

    @staticmethod
    def _parse_schedule_table(container) -> list[dict]:
        """의사 카드 내 스케줄 테이블 파싱

        테이블 구조:
          <tr><th>구분</th><th>월</th>...<th>토</th></tr>
          <tr><td>오전</td><td><img src="...ico_cir_col05.png"></td>...</tr>
          <tr><td>오후</td><td>...</td>...</tr>
        """
        schedules = []
        seen = set()

        tables = container.select("table") if hasattr(container, 'select') else []
        for table in tables:
            # 헤더에서 요일 칼럼 매핑
            col_to_dow = {}
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

            # 오전/오후 행 파싱
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

                    # 진료 여부: 아이콘 이미지 존재, O 마크, 텍스트 등
                    has_schedule = bool(cell.select("img"))
                    if not has_schedule:
                        cell_text = cell.get_text(strip=True)
                        has_schedule = bool(cell_text and cell_text not in ("-", "X", "x", "휴진", ""))

                    if has_schedule:
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

    # ─── 전체 크롤링 (전체 목록 페이지네이션) ───

    async def _fetch_all(self):
        """전체 의료진 크롤링.

        profList.do의 deptNo 파라미터가 무시되고 항상 전체 목록(가나다순)이 반환되므로,
        deptNo 없이 전체 페이지를 순회합니다. 각 카드의 h5.doc_part에서 진료과를 추출.
        """
        if self._cached_data is not None:
            return self._cached_data

        all_doctors = {}  # ext_id → doctor dict

        async with httpx.AsyncClient(headers=self.headers, timeout=60, follow_redirects=True) as client:
            page = 1
            while True:
                try:
                    doctors, total_pages = await self._fetch_prof_list_page(client, dept_code=None, page=page)
                except Exception as e:
                    logger.error(f"[CAU] 페이지 {page} 실패: {e}")
                    break

                for doc in doctors:
                    ext_id = doc["external_id"]
                    # 이름이 비어있으면 profView에서 보충
                    if not doc["name"] and doc.get("prof_no"):
                        try:
                            info, view_schedules = await self._fetch_prof_schedule(
                                client, doc["dept_no"], doc["prof_no"], doc["emp_no"]
                            )
                            if info.get("name"):
                                doc["name"] = info["name"]
                            if info.get("specialty"):
                                doc["specialty"] = info["specialty"]
                            if not doc["schedules"] and view_schedules:
                                doc["schedules"] = view_schedules
                        except Exception:
                            pass
                    if ext_id not in all_doctors:
                        all_doctors[ext_id] = doc

                logger.info(f"[CAU] 페이지 {page}/{total_pages}: {len(doctors)}명")

                if page >= total_pages or not doctors:
                    break
                page += 1

        result = list(all_doctors.values())
        logger.info(f"[CAU] 총 {len(result)}명")
        self._cached_data = result
        return result

    # ─── 개별 의사 프로필 페이지에서 스케줄 파싱 ───

    async def _fetch_prof_schedule(self, client: httpx.AsyncClient, dept_no: str, prof_no: str, emp_no: str) -> tuple[dict, list[dict]]:
        """profView.do 페이지에서 의사 정보 + 스케줄 파싱"""
        try:
            resp = await client.get(
                f"{BASE_URL}/home/medical/profView.do",
                params={"deptNo": dept_no, "profNo": prof_no, "empNo": emp_no},
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            logger.error(f"[CAU] profView 실패 (profNo={prof_no}): {e}")
            return {}, []

        info = {"name": "", "department": "", "position": "", "specialty": ""}

        # 이름, 진료과, 직위, 전문분야 추출
        for h_tag in soup.select("h2, h3, h4"):
            text = h_tag.get_text(strip=True)
            if text and len(text) <= 10 and not info["name"]:
                info["name"] = text

        # 전문분야
        for dt in soup.select("dt, th"):
            text = dt.get_text(strip=True)
            if "전문" in text or "진료분야" in text:
                dd = dt.find_next_sibling("dd") or dt.find_next_sibling("td")
                if dd:
                    info["specialty"] = dd.get_text(strip=True)

        # 스케줄: 월간 달력 또는 주간 테이블에서 파싱
        schedules = self._parse_schedule_table(soup)

        return info, schedules

    # ─── 공개 인터페이스 ───

    async def get_departments(self):
        return await self._fetch_departments()

    async def crawl_doctor_list(self, department=None):
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]
        return [{k: d[k] for k in ("staff_id", "external_id", "name", "department", "position", "specialty", "profile_url", "notes")} for d in data]

    async def crawl_doctor_schedule(self, staff_id):
        empty = {"staff_id": staff_id, "name": "", "department": "", "position": "",
                 "specialty": "", "profile_url": "", "notes": "", "schedules": []}
        if self._cached_data:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return {k: d.get(k, "") for k in ("staff_id", "name", "department", "position", "specialty", "profile_url", "notes", "schedules")}

        # 개별 조회: profView.do 페이지에서 스케줄 가져오기
        prefix = "CAU-"
        raw_id = staff_id.replace(prefix, "") if staff_id.startswith(prefix) else staff_id

        async with httpx.AsyncClient(headers=self.headers, timeout=30, follow_redirects=True) as client:
            # raw_id가 empNo인 경우 - profList에서 profNo를 찾아야 함
            # 전체 크롤링 후 캐시에서 조회
            await self._fetch_all()
            if self._cached_data:
                for d in self._cached_data:
                    if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                        return {k: d.get(k, "") for k in ("staff_id", "name", "department", "position", "specialty", "profile_url", "notes", "schedules")}

        return empty

    async def crawl_doctors(self, department=None):
        from app.schemas.schemas import CrawlResult, CrawledDoctor
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]
        doctors = [CrawledDoctor(name=d["name"], department=d["department"], position=d["position"],
                                 specialty=d["specialty"], profile_url=d["profile_url"],
                                 external_id=d["external_id"], notes="", schedules=d["schedules"]) for d in data]
        return CrawlResult(hospital_code=self.hospital_code, hospital_name=self.hospital_name,
                           status="success" if doctors else "partial", doctors=doctors, crawled_at=datetime.utcnow())
