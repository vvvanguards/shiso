from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

from shiso.scraper.database import Base
from shiso.scraper.models.accounts import (
    AccountSnapshot,
    AccountStatement,
    FinancialAccount,
    FinancialAccountIdentifier,
    FinancialAccountLogin,
    FinancialAccountType,
    ImportCandidate,
    ImportSession,
    PromoAprPeriod,
    ProviderMapping,
    RewardsBalance,
    RewardsProgram,
    ScraperLogin,
    ScraperLoginSyncRun,
)
from shiso.scraper.models.sync_type import SyncTypeRecord
from shiso.scraper.models.tools import (
    ProviderPlaybookRecord,
    ToolRunOutput,
    WorkflowDefinitionRecord,
    WorkflowRevisionSuggestionRecord,
)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()
