# AMC (서울아산병원) 크롤러 참조 구현

AMC는 MR 스케줄러의 표준 참조 크롤러. 대부분의 대형 병원이 이 다단계 구조를 따름.

## 특징
- 3단계 구조: 진료과 목록 → 의사 목록 → 스케줄 상세
- 1~2단계: requests 정적 HTML 파싱 가능
- 3단계(스케줄): JS 렌더링 가능성 높음 → 확인 필요
- 의사 식별자: `doct` 파라미터 (암호화된 base64 문자열)

## URL 구조
```
진료과 목록: https://www.amc.seoul.kr/asan/departments/deptListTypeA.do
의사 목록:   https://www.amc.seoul.kr/asan/staff/base/staffBaseInfoList.do?searchHpCd={deptCode}
의사 상세:   https://www.amc.seoul.kr/asan/staff/base/staffBaseInfoDetail.do (doct 파라미터 필요)
```

## 1단계: 진료과 코드 추출

HTML에서 `searchHpCd=D006` 형태의 링크를 파싱.

```python
def get_departments(self) -> List[Dict]:
    resp = requests.get(
        "https://www.amc.seoul.kr/asan/departments/deptListTypeA.do",
        headers=self.HEADERS
    )
    soup = BeautifulSoup(resp.text, "html.parser")
    
    departments = []
    # 진료과 링크: staffBaseInfoList.do?searchHpCd=D006
    for link in soup.select("a[href*='searchHpCd=']"):
        href = link.get("href", "")
        match = re.search(r'searchHpCd=(\w+)', href)
        if match:
            deptcd = match.group(1)  # e.g. "D006"
            dept_name = link.text.strip()
            if deptcd and dept_name:
                departments.append({"deptcd": deptcd, "dept_name": dept_name})
    
    # 중복 제거
    seen = set()
    result = []
    for d in departments:
        if d["deptcd"] not in seen:
            seen.add(d["deptcd"])
            result.append(d)
    return result
```

## 2단계: 의사 목록 추출

```python
def get_doctors(self, deptcd: str) -> List[Dict]:
    resp = requests.get(
        "https://www.amc.seoul.kr/asan/staff/base/staffBaseInfoList.do",
        params={"searchHpCd": deptcd},
        headers=self.HEADERS
    )
    soup = BeautifulSoup(resp.text, "html.parser")
    
    doctors = []
    for item in soup.select(".staff_list li, .doc_list li"):  # 실제 클래스명 확인 필요
        name_tag = item.select_one("a.name, strong.name")
        detail_link = item.select_one("a[href*='staffBaseInfoDetail']")
        
        if not name_tag or not detail_link:
            continue
        
        href = detail_link.get("href", "")
        # doct 파라미터 추출 (암호화된 의사 식별자)
        match = re.search(r'doct=([^&"]+)', href)
        drcd = match.group(1) if match else None
        
        if drcd:
            doctors.append({
                "drcd": drcd,
                "doctor_name": name_tag.text.strip(),
            })
    return doctors
```

## 3단계: 스케줄 조회 (JS 렌더링 여부 확인 필요)

스케줄 상세 페이지가 JS 렌더링인 경우 Playwright 사용:

```python
async def get_schedule_with_playwright(self, drcd: str) -> List[Dict]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(
            f"https://www.amc.seoul.kr/asan/staff/base/staffBaseInfoDetail.do?doct={drcd}",
            wait_until="networkidle"
        )
        await page.wait_for_selector(".schedule_wrap, .tbl_schedule", timeout=10000)
        
        content = await page.content()
        await browser.close()
        
        soup = BeautifulSoup(content, "html.parser")
        return self._parse_schedule(soup)
```

## 주의사항

- AMC는 진료과 외에 **암병원, 어린이병원, 심장병원** 등 별도 카테고리 있음
  - `deptListTypeH.do` (암병원), `deptListTypeF.do` (어린이병원) 등 추가 크롤링 필요
- `doct` 파라미터가 암호화된 문자열이라 `deptcd + drcd` 패턴 대신 **`deptcd + doct`를 고유키**로 사용
- 요청 간 `time.sleep(1.0)` 권장 (AMC는 트래픽에 민감)
- 의사 상세 URL이 로그인 없이 접근 가능한지 사전 확인 필요
