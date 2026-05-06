"""multi-team + announcement 게시 기간

Revision ID: d4f8e1a3b2c5
Revises: e7a2c5b9d1f0
Create Date: 2026-05-06

1) users.active_team_id 추가 — 멀티팀에서 사용자의 "현재 활성 팀". 기존 사용자
   는 본인의 첫 TeamMember.team_id 로 backfill (없으면 NULL).
2) visit_logs.announce_start_date / announce_end_date 추가 — 업무공지 게시
   기간. 기존 announcement 행은 visit_date 의 date 부분으로 backfill (start=end).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4f8e1a3b2c5'
down_revision: Union[str, None] = 'e7a2c5b9d1f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'

    # 직전 실패 잔여 정리 (batch 임시테이블)
    if is_sqlite:
        bind.exec_driver_sql("DROP TABLE IF EXISTS _alembic_tmp_users")
        bind.exec_driver_sql("DROP TABLE IF EXISTS _alembic_tmp_visit_logs")

    # 컬럼 존재 검사 helper (재실행 안전성)
    insp = sa.inspect(bind)
    user_cols = {c['name'] for c in insp.get_columns('users')}
    visit_cols = {c['name'] for c in insp.get_columns('visit_logs')}

    # ── 1) users.active_team_id ──
    # SQLite 은 FK 추가가 batch 임시테이블 swap 으로 가는데 비동기 환경에서 깨지는 케이스가 있어
    # 단순 add_column 으로 우회. PG 는 batch 없이 직접 ALTER 가능.
    if 'active_team_id' not in user_cols:
        op.add_column('users', sa.Column('active_team_id', sa.Integer(), nullable=True))
        if not is_sqlite:
            op.create_foreign_key(
                'fk_users_active_team',
                'users', 'teams', ['active_team_id'], ['id'], ondelete='SET NULL',
            )

    # 기존 사용자: 첫 소속 팀(가장 작은 team_member id) 으로 active_team 설정
    # SQLite 는 UPDATE 에 alias 못 줘서 `users u` 대신 그대로 사용
    op.execute("""
        UPDATE users
           SET active_team_id = (
               SELECT tm.team_id
                 FROM team_members tm
                WHERE tm.user_id = users.id
                ORDER BY tm.id ASC
                LIMIT 1
           )
         WHERE EXISTS (SELECT 1 FROM team_members tm WHERE tm.user_id = users.id)
    """)

    # ── 2) visit_logs.announce_start/end ──
    if 'announce_start_date' not in visit_cols:
        op.add_column('visit_logs', sa.Column('announce_start_date', sa.String(length=10), nullable=True))
        op.create_index('ix_visit_logs_announce_start_date', 'visit_logs', ['announce_start_date'])
    if 'announce_end_date' not in visit_cols:
        op.add_column('visit_logs', sa.Column('announce_end_date', sa.String(length=10), nullable=True))
        op.create_index('ix_visit_logs_announce_end_date', 'visit_logs', ['announce_end_date'])

    # 기존 announcement 행: start=end=visit_date 의 date 로 backfill (1일 공지)
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute("""
            UPDATE visit_logs
               SET announce_start_date = TO_CHAR(visit_date, 'YYYY-MM-DD'),
                   announce_end_date   = TO_CHAR(visit_date, 'YYYY-MM-DD')
             WHERE category = 'announcement'
               AND announce_start_date IS NULL
        """)
    else:
        # SQLite: visit_date 가 'YYYY-MM-DD HH:MM:SS' 텍스트로 저장 — 앞 10자만 잘라서 사용
        op.execute("""
            UPDATE visit_logs
               SET announce_start_date = substr(visit_date, 1, 10),
                   announce_end_date   = substr(visit_date, 1, 10)
             WHERE category = 'announcement'
               AND announce_start_date IS NULL
        """)


def downgrade() -> None:
    op.drop_index('ix_visit_logs_announce_end_date', table_name='visit_logs')
    op.drop_index('ix_visit_logs_announce_start_date', table_name='visit_logs')
    op.drop_column('visit_logs', 'announce_end_date')
    op.drop_column('visit_logs', 'announce_start_date')

    bind = op.get_bind()
    if bind.dialect.name != 'sqlite':
        op.drop_constraint('fk_users_active_team', 'users', type_='foreignkey')
    op.drop_column('users', 'active_team_id')
