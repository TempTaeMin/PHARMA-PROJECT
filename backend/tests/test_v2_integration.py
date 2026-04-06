"""PharmScheduler v0.2.0 통합 테스트

추가 테스트:
- Celery 태스크 구조 검증
- WebSocket 알림 매니저 검증
- 알림 API 검증
- 스케줄러 API 검증
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime


def test_celery_task_structure():
    """Celery 태스크 모듈 import 및 구조 검증"""
    print("=" * 60)
    print("TEST: Celery 태스크 구조 검증")
    print("=" * 60)

    from app.tasks.crawl_tasks import (
        crawl_all_hospitals,
        crawl_single_hospital,
        crawl_single_doctor,
        check_registered_doctors,
    )

    tasks = [
        ("crawl_all_hospitals", crawl_all_hospitals),
        ("crawl_single_hospital", crawl_single_hospital),
        ("crawl_single_doctor", crawl_single_doctor),
        ("check_registered_doctors", check_registered_doctors),
    ]

    for name, task in tasks:
        assert task.name == f"app.tasks.crawl_tasks.{name}"
        print(f"  ✅ {name} → task_name: {task.name}")

    from app.tasks.notification_tasks import (
        send_schedule_change_notification,
        send_visit_reminder,
        send_overdue_warning,
    )

    notif_tasks = [
        ("send_schedule_change_notification", send_schedule_change_notification),
        ("send_visit_reminder", send_visit_reminder),
        ("send_overdue_warning", send_overdue_warning),
    ]

    for name, task in notif_tasks:
        assert task.name == f"app.tasks.notification_tasks.{name}"
        print(f"  ✅ {name} → task_name: {task.name}")

    print(f"\n  ✅ 총 {len(tasks) + len(notif_tasks)}개 태스크 구조 검증 통과!")


def test_celery_beat_schedule():
    """Beat 스케줄 설정 검증"""
    print("\n" + "=" * 60)
    print("TEST: Celery Beat 스케줄 검증")
    print("=" * 60)

    from app.tasks.celery_app import celery_app

    beat = celery_app.conf.beat_schedule
    assert "crawl-all-hospitals-daily" in beat
    assert "check-schedule-changes" in beat

    daily = beat["crawl-all-hospitals-daily"]
    print(f"  ✅ 전체 크롤링: task={daily['task']}")
    print(f"     스케줄: 매일 {daily['schedule']._orig_hour}시 {daily['schedule']._orig_minute}분")
    print(f"     큐: {daily['options']['queue']}")

    check = beat["check-schedule-changes"]
    print(f"  ✅ 변경 체크: task={check['task']}")
    print(f"     스케줄: {check['schedule']._orig_minute}분 간격")
    print(f"     큐: {check['options']['queue']}")

    # 큐 라우팅 검증
    routes = celery_app.conf.task_routes
    assert "app.tasks.crawl_tasks.*" in routes
    assert "app.tasks.notification_tasks.*" in routes
    print(f"\n  ✅ 큐 라우팅:")
    for pattern, route in routes.items():
        print(f"     {pattern} → {route['queue']}")

    print(f"\n  ✅ Beat 스케줄 검증 통과!")


async def test_notification_manager():
    """알림 매니저 기능 검증"""
    print("\n" + "=" * 60)
    print("TEST: 알림 매니저 검증")
    print("=" * 60)

    from app.notifications.manager import NotificationManager

    # 새 인스턴스로 테스트
    manager = NotificationManager()

    assert manager.active_count == 0
    print(f"  ✅ 초기 연결 수: {manager.active_count}")

    # 동기 브로드캐스트 (Celery 태스크 시뮬레이션)
    test_change = {
        "type": "schedule_change",
        "data": {
            "doctor_name": "김정형",
            "change_type": "removed",
            "day": "월",
            "time_slot": "오전",
            "message": "김정형 교수 월 오전 진료 취소",
        },
    }
    manager.broadcast_sync(test_change)
    print(f"  ✅ 동기 브로드캐스트 성공 (Celery 시뮬레이션)")

    # 히스토리 확인
    history = manager.get_history(limit=10)
    assert len(history) == 1
    assert history[0]["type"] == "schedule_change"
    print(f"  ✅ 히스토리 저장: {len(history)}건")

    # 추가 알림
    for i in range(5):
        manager.broadcast_sync({
            "type": "visit_reminder",
            "data": {"message": f"테스트 알림 {i+1}"},
        })

    history = manager.get_history(limit=10)
    assert len(history) == 6
    print(f"  ✅ 히스토리 누적: {len(history)}건")

    # 미읽은 알림
    unread = manager.get_history(limit=10, unread_only=True)
    assert len(unread) == 6
    print(f"  ✅ 미읽은 알림: {len(unread)}건")

    # 읽음 처리
    nid = history[0]["id"]
    result = manager.mark_as_read(nid)
    assert result is True
    unread = manager.get_history(limit=10, unread_only=True)
    assert len(unread) == 5
    print(f"  ✅ 읽음 처리 후 미읽은: {len(unread)}건")

    # 전체 읽음
    manager.mark_all_as_read()
    unread = manager.get_history(limit=10, unread_only=True)
    assert len(unread) == 0
    print(f"  ✅ 전체 읽음 처리 후: {len(unread)}건")

    print(f"\n  ✅ 알림 매니저 검증 통과!")


async def test_fastapi_v2():
    """FastAPI v0.2.0 앱 + 새 엔드포인트 테스트"""
    print("\n" + "=" * 60)
    print("TEST: FastAPI v0.2.0 API 검증")
    print("=" * 60)

    from app.main import app
    from httpx import AsyncClient, ASGITransport

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 헬스체크 (버전 확인)
        resp = await client.get("/")
        data = resp.json()
        assert data["version"] == "0.2.0"
        assert "features" in data
        print(f"  ✅ GET / → v{data['version']}, features: {len(data['features'])}개")

        # 기존 API 유지 확인
        resp = await client.get("/api/crawl/hospitals")
        assert resp.status_code == 200
        print(f"  ✅ GET /api/crawl/hospitals → 정상")

        resp = await client.get("/api/crawl/departments/AMC")
        assert resp.status_code == 200
        print(f"  ✅ GET /api/crawl/departments/AMC → 정상")

        # 새 API: 스케줄러 상태
        resp = await client.get("/api/scheduler/status")
        assert resp.status_code == 200
        sched = resp.json()
        print(f"  ✅ GET /api/scheduler/status → celery: {sched['celery_connected']}, schedule: {sched['schedule']}")

        # 새 API: 알림 목록
        resp = await client.get("/api/notifications/")
        assert resp.status_code == 200
        notifs = resp.json()
        print(f"  ✅ GET /api/notifications/ → {notifs['count']}건, unread: {notifs['unread_count']}")

        # 새 API: 알림 상태
        resp = await client.get("/api/notifications/status")
        assert resp.status_code == 200
        status = resp.json()
        print(f"  ✅ GET /api/notifications/status → ws연결: {status['active_connections']}")

        # 새 API: 테스트 알림 발송
        resp = await client.post("/api/notifications/test?message=통합테스트알림")
        assert resp.status_code == 200
        test_notif = resp.json()
        print(f"  ✅ POST /api/notifications/test → {test_notif['status']}")

        # 알림이 쌓였는지 확인
        resp = await client.get("/api/notifications/?unread_only=true")
        notifs = resp.json()
        assert notifs["unread_count"] >= 1
        print(f"  ✅ 테스트 알림 저장 확인 → unread: {notifs['unread_count']}")

        # 전체 읽음 처리
        resp = await client.post("/api/notifications/read-all")
        assert resp.status_code == 200
        print(f"  ✅ POST /api/notifications/read-all → {resp.json()['status']}")

        # Swagger 문서
        resp = await client.get("/docs")
        assert resp.status_code == 200
        print(f"  ✅ GET /docs → Swagger UI 정상")

        # OpenAPI 스키마에서 엔드포인트 수 확인
        resp = await client.get("/openapi.json")
        schema = resp.json()
        paths = list(schema["paths"].keys())
        print(f"\n  📋 전체 API 엔드포인트 ({len(paths)}개):")
        for path in sorted(paths):
            methods = list(schema["paths"][path].keys())
            print(f"     {', '.join(m.upper() for m in methods):10s} {path}")

    print(f"\n  ✅ FastAPI v0.2.0 검증 통과!")


def main():
    print("🏥 PharmScheduler v0.2.0 통합 테스트")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    test_celery_task_structure()
    test_celery_beat_schedule()
    asyncio.run(test_notification_manager())
    asyncio.run(test_fastapi_v2())

    print("\n" + "=" * 60)
    print("🎉 v0.2.0 전체 테스트 통과!")
    print("=" * 60)


if __name__ == "__main__":
    main()
