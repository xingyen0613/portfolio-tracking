"""indexes for /api/holdings hot path

Revision ID: 008
Revises: 007
Create Date: 2026-05-10

get_holdings() 的 SQL 用兩層 correlated subquery 找每個 account 的最新 source_run +
最新 snapshot_date。這幾個欄位以前沒索引，每次都做 Seq Scan，累積下來測試帳號
就要 17 秒（前端 axios timeout 10s 直接打掛畫面）。

補三個 B-tree 索引把那兩個 SubPlan 從 O(n) 降到 O(log n)。
"""
from alembic import op


revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_nh_source_run_snapshot "
        "ON normalized_holdings (source_run_id, snapshot_date)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_source_runs_account_status_started "
        "ON source_runs (account_id, status, started_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_accounts_user_id "
        "ON accounts (user_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_accounts_user_id")
    op.execute("DROP INDEX IF EXISTS idx_source_runs_account_status_started")
    op.execute("DROP INDEX IF EXISTS idx_nh_source_run_snapshot")
