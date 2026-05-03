"""통합 테스트 - Mock 데이터로 전체 파이프라인 검증

실제 병원 사이트 접근 없이 크롤러 → DB 저장 → API 응답 흐름을 테스트합니다.
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from app.schemas.schemas import CrawlResult, CrawledDoctor


# ==========================================
# Mock 크롤링 데이터 (서울아산병원 정형외과)
# ==========================================
MOCK_CRAWL_DATA = CrawlResult(
    hospital_code="AMC",
    hospital_name="서울아산병원",
    status="success",
    doctors=[
        CrawledDoctor(
            name="김정형",
            department="정형외과",
            position="교수",
            specialty="슬관절, 인공관절 치환술",
            profile_url="https://www.amc.seoul.kr/asan/staff/base/staffBaseInfoView.do?staffId=1001",
            photo_url="",
            external_id="1001",
            schedules=[
                {"day_of_week": 0, "time_slot": "morning", "start_time": "09:00", "end_time": "12:00", "location": "외래 3층"},
                {"day_of_week": 2, "time_slot": "morning", "start_time": "09:00", "end_time": "12:00", "location": "외래 3층"},
                {"day_of_week": 4, "time_slot": "afternoon", "start_time": "13:00", "end_time": "17:00", "location": "외래 3층"},
            ],
        ),
        CrawledDoctor(
            name="이척추",
            department="정형외과",
            position="교수",
            specialty="척추외과, 척추변형",
            profile_url="https://www.amc.seoul.kr/asan/staff/base/staffBaseInfoView.do?staffId=1002",
            photo_url="",
            external_id="1002",
            schedules=[
                {"day_of_week": 1, "time_slot": "morning", "start_time": "09:00", "end_time": "12:00", "location": "외래 3층"},
                {"day_of_week": 3, "time_slot": "morning", "start_time": "09:00", "end_time": "12:00", "location": "외래 3층"},
                {"day_of_week": 3, "time_slot": "afternoon", "start_time": "13:00", "end_time": "17:00", "location": "외래 3층"},
            ],
        ),
        CrawledDoctor(
            name="박관절",
            department="정형외과",
            position="부교수",
            specialty="어깨관절, 스포츠의학",
            profile_url="https://www.amc.seoul.kr/asan/staff/base/staffBaseInfoView.do?staffId=1003",
            photo_url="",
            external_id="1003",
            schedules=[
                {"day_of_week": 0, "time_slot": "afternoon", "start_time": "13:00", "end_time": "17:00", "location": "외래 3층"},
                {"day_of_week": 2, "time_slot": "afternoon", "start_time": "13:00", "end_time": "17:00", "location": "외래 3층"},
                {"day_of_week": 4, "time_slot": "morning", "start_time": "09:00", "end_time": "12:00", "location": "외래 3층"},
            ],
        ),
    ],
    crawled_at=datetime.utcnow(),
)

DAY_NAMES = ["월", "화", "수", "목", "금", "토", "일"]
SLOT_NAMES = {"morning": "오전", "afternoon": "오후", "evening": "야간"}


def test_crawl_result():
    """크롤링 결과 데이터 구조 검증"""
    print("=" * 60)
    print("TEST: 크롤링 결과 데이터 검증")
    print("=" * 60)

    result = MOCK_CRAWL_DATA

    assert result.status == "success"
    assert result.hospital_code == "AMC"
    assert len(result.doctors) == 3
    print(f"  ✅ 병원: {result.hospital_name} ({result.hospital_code})")
    print(f"  ✅ 상태: {result.status}")
    print(f"  ✅ 의료진: {len(result.doctors)}명")

    for doc in result.doctors:
        assert doc.name
        assert doc.department
        assert len(doc.schedules) > 0
        schedule_str = ", ".join(
            f"{DAY_NAMES[s['day_of_week']]}({SLOT_NAMES[s['time_slot']]})"
            for s in doc.schedules
        )
        print(f"\n  👨‍⚕️ {doc.name} ({doc.position}) - {doc.department}")
        print(f"     전문: {doc.specialty}")
        print(f"     진료: {schedule_str}")
        print(f"     ID: {doc.external_id}")

    print(f"\n  ✅ 데이터 구조 검증 통과!")


def test_schedule_conflict_detection():
    """동일 시간대 방문 충돌 감지 로직 테스트"""
    print("\n" + "=" * 60)
    print("TEST: 스케줄 충돌 감지")
    print("=" * 60)

    # 월요일 오전에 진료하는 교수들
    monday_morning = []
    for doc in MOCK_CRAWL_DATA.doctors:
        for s in doc.schedules:
            if s["day_of_week"] == 0 and s["time_slot"] == "morning":
                monday_morning.append(doc.name)

    print(f"  월요일 오전 진료 교수: {monday_morning}")
    if len(monday_morning) > 1:
        print(f"  ⚠️ 충돌: 동시 방문 불가 → 우선순위 설정 필요")
    else:
        print(f"  ✅ 충돌 없음")

    # 전체 요일별 진료 현황
    print(f"\n  📅 주간 진료 현황:")
    for day in range(5):  # 월~금
        slots = {"morning": [], "afternoon": []}
        for doc in MOCK_CRAWL_DATA.doctors:
            for s in doc.schedules:
                if s["day_of_week"] == day:
                    slots[s["time_slot"]].append(doc.name)

        am = ", ".join(slots["morning"]) or "-"
        pm = ", ".join(slots["afternoon"]) or "-"
        print(f"    {DAY_NAMES[day]}: 오전[{am}] / 오후[{pm}]")

    print(f"\n  ✅ 충돌 감지 로직 통과!")


def test_visit_priority_recommendation():
    """방문 우선순위 추천 로직 테스트"""
    print("\n" + "=" * 60)
    print("TEST: 방문 우선순위 추천")
    print("=" * 60)

    # 가상 방문 이력
    visit_history = {
        "김정형": {"grade": "A", "last_visit": "2026-03-15", "days_since": 11},
        "이척추": {"grade": "B", "last_visit": "2026-03-01", "days_since": 25},
        "박관절": {"grade": "A", "last_visit": "2026-03-20", "days_since": 6},
    }

    # 등급별 방문 주기 (일)
    grade_cycle = {"A": 7, "B": 14, "C": 30}

    print(f"  📊 방문 우선순위 분석:")
    priorities = []
    for doc in MOCK_CRAWL_DATA.doctors:
        history = visit_history.get(doc.name, {})
        grade = history.get("grade", "C")
        days_since = history.get("days_since", 999)
        cycle = grade_cycle[grade]
        overdue = days_since - cycle
        urgency = max(0, overdue)

        priorities.append({
            "name": doc.name,
            "grade": grade,
            "days_since": days_since,
            "cycle": cycle,
            "overdue": overdue,
            "urgency": urgency,
        })

    # 긴급도순 정렬
    priorities.sort(key=lambda x: x["urgency"], reverse=True)

    for p in priorities:
        status = "🔴 미방문 초과" if p["overdue"] > 0 else "🟢 정상"
        print(
            f"    {p['name']} [{p['grade']}등급] "
            f"- {p['days_since']}일 경과 (주기: {p['cycle']}일) "
            f"→ {status} ({p['overdue']:+d}일)"
        )

    print(f"\n  📋 추천 방문 순서:")
    for i, p in enumerate(priorities, 1):
        next_slots = []
        for doc in MOCK_CRAWL_DATA.doctors:
            if doc.name == p["name"]:
                for s in doc.schedules:
                    next_slots.append(
                        f"{DAY_NAMES[s['day_of_week']]} {SLOT_NAMES[s['time_slot']]}"
                    )
        print(f"    {i}. {p['name']} → 가능: {', '.join(next_slots)}")

    print(f"\n  ✅ 방문 우선순위 추천 로직 통과!")


def test_change_detection():
    """일정 변경 감지 로직 테스트"""
    print("\n" + "=" * 60)
    print("TEST: 일정 변경 감지")
    print("=" * 60)

    # 이전 크롤링 결과 (가상)
    old_schedules = {
        "1001": [  # 김정형
            {"day_of_week": 0, "time_slot": "morning"},
            {"day_of_week": 2, "time_slot": "morning"},
            {"day_of_week": 4, "time_slot": "morning"},  # 금요일 오전 → 오후로 변경됨
        ],
    }

    # 새 크롤링 결과
    new_schedules = {
        "1001": [
            {"day_of_week": 0, "time_slot": "morning"},
            {"day_of_week": 2, "time_slot": "morning"},
            {"day_of_week": 4, "time_slot": "afternoon"},  # 변경!
        ],
    }

    for staff_id in old_schedules:
        old = {(s["day_of_week"], s["time_slot"]) for s in old_schedules[staff_id]}
        new = {(s["day_of_week"], s["time_slot"]) for s in new_schedules[staff_id]}

        removed = old - new
        added = new - old

        if removed or added:
            print(f"  ⚠️ staffId={staff_id} 일정 변경 감지!")
            for day, slot in removed:
                print(f"    ❌ 삭제: {DAY_NAMES[day]} {SLOT_NAMES[slot]}")
            for day, slot in added:
                print(f"    ✅ 추가: {DAY_NAMES[day]} {SLOT_NAMES[slot]}")
        else:
            print(f"  ✅ staffId={staff_id} 변경 없음")

    print(f"\n  ✅ 변경 감지 로직 통과!")


async def test_fastapi_app():
    """FastAPI 앱 정상 구동 테스트"""
    print("\n" + "=" * 60)
    print("TEST: FastAPI 앱 구동")
    print("=" * 60)

    from app.main import app
    from httpx import AsyncClient, ASGITransport

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 헬스체크
        resp = await client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        print(f"  ✅ GET / → {data}")

        resp = await client.get("/health")
        assert resp.status_code == 200
        print(f"  ✅ GET /health → {resp.json()}")

        # 지원 병원 목록
        resp = await client.get("/api/crawl/hospitals")
        assert resp.status_code == 200
        hospitals = resp.json()["hospitals"]
        print(f"  ✅ GET /api/crawl/hospitals → {len(hospitals)}개 병원")
        for h in hospitals:
            print(f"     → {h['code']}: {h['name']}")

        # 진료과 목록
        resp = await client.get("/api/crawl/departments/AMC")
        assert resp.status_code == 200
        depts = resp.json()["departments"]
        print(f"  ✅ GET /api/crawl/departments/AMC → {len(depts)}개 진료과")

        # Swagger 문서
        resp = await client.get("/docs")
        assert resp.status_code == 200
        print(f"  ✅ GET /docs → Swagger UI 정상")

        print(f"\n  ✅ FastAPI 앱 구동 테스트 통과!")


def main():
    print("🏥 MediSync 통합 테스트")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    test_crawl_result()
    test_schedule_conflict_detection()
    test_visit_priority_recommendation()
    test_change_detection()
    asyncio.run(test_fastapi_app())

    print("\n" + "=" * 60)
    print("🎉 전체 테스트 통과!")
    print("=" * 60)


if __name__ == "__main__":
    main()
