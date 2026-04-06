"""Windows용 서버 실행 스크립트

reload=False로 실행해야 Windows에서 Playwright가 동작합니다.
(reload 모드는 자식 프로세스를 새로 만들어서 이벤트 루프 정책이 초기화됨)

코드 수정 후에는 Ctrl+C → python run.py로 재시작하세요.
"""
import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )
