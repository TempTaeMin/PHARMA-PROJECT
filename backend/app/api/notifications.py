"""알림 API + WebSocket 엔드포인트"""
import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from app.notifications.manager import notification_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/notifications", tags=["알림"])


# ==============================
# WebSocket 엔드포인트
# ==============================
@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, user_id: str = Query("default")):
    """실시간 알림 WebSocket 연결
    
    연결: ws://localhost:8000/api/notifications/ws?user_id=mr_001
    
    수신 메시지 형식:
    {
        "type": "schedule_change" | "visit_reminder" | "overdue_warning",
        "data": { ... },
        "created_at": "2026-03-26T10:00:00",
        "read": false
    }
    
    클라이언트 → 서버 메시지:
    {"action": "mark_read", "notification_id": "notif_1"}
    {"action": "mark_all_read"}
    {"action": "ping"}
    """
    await notification_manager.connect(websocket, user_id)

    try:
        while True:
            # 클라이언트 메시지 수신
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                action = message.get("action")

                if action == "mark_read":
                    nid = message.get("notification_id")
                    notification_manager.mark_as_read(nid)
                    await websocket.send_json({"action": "marked_read", "id": nid})

                elif action == "mark_all_read":
                    notification_manager.mark_all_as_read()
                    await websocket.send_json({"action": "all_marked_read"})

                elif action == "ping":
                    await websocket.send_json({"action": "pong"})

                elif action == "get_history":
                    limit = message.get("limit", 20)
                    unread = message.get("unread_only", False)
                    history = notification_manager.get_history(limit, unread)
                    await websocket.send_json({
                        "action": "history",
                        "data": history,
                        "count": len(history),
                    })

            except json.JSONDecodeError:
                await websocket.send_json({"error": "Invalid JSON"})

    except WebSocketDisconnect:
        await notification_manager.disconnect(websocket, user_id)


# ==============================
# REST API 엔드포인트
# ==============================
@router.get("/", summary="알림 목록 조회")
async def get_notifications(
    limit: int = Query(20, ge=1, le=100),
    unread_only: bool = Query(False),
):
    """알림 히스토리를 조회합니다."""
    notifications = notification_manager.get_history(limit, unread_only)
    unread_count = len([n for n in notification_manager.get_history(100) if not n.get("read")])

    return {
        "notifications": notifications,
        "count": len(notifications),
        "unread_count": unread_count,
    }


@router.post("/{notification_id}/read", summary="알림 읽음 처리")
async def mark_notification_read(notification_id: str):
    """특정 알림을 읽음 처리합니다."""
    success = notification_manager.mark_as_read(notification_id)
    if not success:
        return {"status": "not_found", "id": notification_id}
    return {"status": "read", "id": notification_id}


@router.post("/read-all", summary="전체 알림 읽음 처리")
async def mark_all_read():
    """모든 알림을 읽음 처리합니다."""
    notification_manager.mark_all_as_read()
    return {"status": "all_read"}


@router.get("/status", summary="알림 시스템 상태")
async def notification_status():
    """WebSocket 연결 현황 및 알림 시스템 상태를 확인합니다."""
    return {
        "active_connections": notification_manager.active_count,
        "total_notifications": len(notification_manager.get_history(100)),
        "unread_count": len([
            n for n in notification_manager.get_history(100) if not n.get("read")
        ]),
    }


@router.post("/test", summary="테스트 알림 발송")
async def send_test_notification(
    message: str = Query("테스트 알림입니다", description="알림 메시지"),
    notification_type: str = Query("schedule_change", description="알림 타입"),
):
    """테스트 알림을 발송합니다 (개발용)."""
    from datetime import datetime

    notification = {
        "type": notification_type,
        "data": {
            "message": message,
            "doctor_name": "테스트 교수",
            "hospital_code": "AMC",
            "change_type": "test",
        },
        "created_at": datetime.now().isoformat(),
        "read": False,
    }

    await notification_manager.broadcast(notification)

    return {
        "status": "sent",
        "active_connections": notification_manager.active_count,
        "notification": notification,
    }
