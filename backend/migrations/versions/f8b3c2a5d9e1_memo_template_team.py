"""memo_templates: team_id 컬럼 추가 (팀 공유 템플릿)

Revision ID: f8b3c2a5d9e1
Revises: e7a2c5b9d1f0
Create Date: 2026-05-19

방문 결과 form 입력 도입과 함께 메모 템플릿을 user-scoped → user 또는 team scope
둘 다 가능하도록 team_id (nullable FK) 추가. team_id IS NULL 이면 개인 템플릿,
NOT NULL 이면 팀 owner 만 write, 같은 팀 멤버 read.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f8b3c2a5d9e1'
down_revision: Union[str, None] = 'e7a2c5b9d1f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('memo_templates') as batch:
        batch.add_column(sa.Column('team_id', sa.Integer(), nullable=True))
        batch.create_foreign_key(
            'fk_memo_templates_team_id',
            'teams',
            ['team_id'],
            ['id'],
            ondelete='CASCADE',
        )
    op.create_index('ix_memo_templates_team_id', 'memo_templates', ['team_id'])


def downgrade() -> None:
    op.drop_index('ix_memo_templates_team_id', table_name='memo_templates')
    with op.batch_alter_table('memo_templates') as batch:
        batch.drop_constraint('fk_memo_templates_team_id', type_='foreignkey')
        batch.drop_column('team_id')
