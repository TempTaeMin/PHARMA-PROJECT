"""Database connection configuration"""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.models.database import Base

DATABASE_URL = "sqlite+aiosqlite:///./pharma_scheduler.db"

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _migrate_visit_logs(conn):
    """visit_logs: doctor_id NULL 허용 + category/title 컬럼 추가."""
    res = await conn.execute(text("PRAGMA table_info(visit_logs)"))
    rows = res.fetchall()
    if not rows:
        return
    cols = {row[1]: row for row in rows}  # name -> (cid, name, type, notnull, dflt, pk)
    has_category = "category" in cols
    has_title = "title" in cols
    doctor_row = cols.get("doctor_id")
    doctor_not_null = bool(doctor_row[3]) if doctor_row else False

    need_rebuild = (not has_category) or doctor_not_null
    if need_rebuild:
        await conn.execute(text("PRAGMA foreign_keys=OFF"))
        await conn.execute(text("""
            CREATE TABLE visit_logs_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doctor_id INTEGER REFERENCES doctors(id),
                visit_date DATETIME NOT NULL,
                status VARCHAR(20),
                product VARCHAR(200),
                notes TEXT,
                next_action TEXT,
                category VARCHAR(20) DEFAULT 'professor',
                title VARCHAR(200),
                created_at DATETIME
            )
        """))
        await conn.execute(text("""
            INSERT INTO visit_logs_new
                (id, doctor_id, visit_date, status, product, notes, next_action, category, title, created_at)
            SELECT id, doctor_id, visit_date, status, product, notes, next_action,
                   'professor', NULL, created_at FROM visit_logs
        """))
        await conn.execute(text("DROP TABLE visit_logs"))
        await conn.execute(text("ALTER TABLE visit_logs_new RENAME TO visit_logs"))
        await conn.execute(text("PRAGMA foreign_keys=ON"))
    elif not has_title:
        await conn.execute(text("ALTER TABLE visit_logs ADD COLUMN title VARCHAR(200)"))


async def _migrate_memo_templates(conn):
    """memo_templates: scope / default_report_type 컬럼 추가 (있으면 skip)."""
    res = await conn.execute(text("PRAGMA table_info(memo_templates)"))
    rows = res.fetchall()
    if not rows:
        return
    existing = {row[1] for row in rows}
    if "scope" not in existing:
        await conn.execute(text(
            "ALTER TABLE memo_templates ADD COLUMN scope VARCHAR(20) NOT NULL DEFAULT 'memo'"
        ))
    if "default_report_type" not in existing:
        await conn.execute(text(
            "ALTER TABLE memo_templates ADD COLUMN default_report_type VARCHAR(20)"
        ))


async def _migrate_visit_logs_user_id(conn):
    """visit_logs 에 user_id 추가. 기존 row 는 reset_for_oauth.py 가 비움."""
    res = await conn.execute(text("PRAGMA table_info(visit_logs)"))
    rows = res.fetchall()
    if not rows:
        return
    existing = {row[1] for row in rows}
    if "user_id" not in existing:
        # SQLite ALTER 는 NOT NULL 추가 불가 → nullable 로 추가, 코드 레벨에서 NOT NULL 보장
        await conn.execute(text("ALTER TABLE visit_logs ADD COLUMN user_id INTEGER"))


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _migrate_visit_logs(conn)
        await _migrate_memo_templates(conn)
        await _migrate_visit_logs_user_id(conn)


async def get_db():
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
