import asyncio
from collections.abc import AsyncIterator, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Any

import structlog
from dishka import Provider, Scope, from_context, provide
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool
from starlette.requests import Request

from app.application.alerts.ports.alert_repository import AlertRepository
from app.application.alerts.use_cases.clear_alerts import ClearAlertsUseCase
from app.application.alerts.use_cases.list_alerts import ListAlertsUseCase
from app.application.alerts.use_cases.mark_alert_read import MarkAlertReadUseCase
from app.application.categories.ports.category_repository import CategoryRepository
from app.application.categories.use_cases.create_category import CreateCategoryUseCase
from app.application.categories.use_cases.list_categories import ListCategoriesUseCase
from app.application.chat.ports.chat_ai_client import ChatAIClient
from app.application.chat.ports.chat_history_store import ChatHistoryStore
from app.application.chat.ports.chat_token_budget import ChatTokenBudget
from app.application.chat.ports.chat_tools import ChatTools
from app.application.chat.ports.id_generator import ChatTurnIdGenerator
from app.application.chat.ports.work_unit import ChatWorkUnitFactory
from app.application.chat.use_cases.chat_query import ChatQueryUseCase
from app.application.chat.use_cases.chat_stream import ChatStreamUseCase
from app.application.chat.use_cases.clear_chat_history import ClearChatHistoryUseCase
from app.application.chat.use_cases.list_chat_history import ListChatHistoryUseCase
from app.application.common.ports.audit_log import AuditLog
from app.application.common.ports.clock import Clock
from app.application.common.ports.flusher import Flusher
from app.application.common.ports.identity_context import IdentityContext
from app.application.common.ports.outbox_repository import OutboxRepository
from app.application.common.ports.quota_check import QuotaCheck
from app.application.common.ports.user_plan_lookup import UserPlanLookup
from app.application.ingestion.ports.image_preprocessor import ImagePreprocessor
from app.application.ingestion.ports.receipt_extractor import ReceiptExtractor
from app.application.ingestion.ports.upload_policy import UploadPolicy
from app.application.ingestion.use_cases.parse_receipt import ParseReceiptUseCase
from app.application.insights.config import InsightWorkerConfig
from app.application.insights.ports.insight_repository import InsightRepository
from app.application.insights.ports.transaction_reader import TransactionReader
from app.application.insights.ports.work_unit import InsightWorkUnitFactory
from app.application.insights.use_cases.get_insight import GetInsightUseCase
from app.application.insights.use_cases.list_insights import ListInsightsUseCase
from app.application.insights.use_cases.request_insight import RequestInsightUseCase
from app.application.insights.use_cases.stream_insight import StreamInsightUseCase
from app.application.recurring.ports.recurring_rule_repository import (
    RecurringRuleRepository as RecurringRuleRepositoryPort,
)
from app.application.recurring.use_cases.create_recurring_rule import CreateRecurringRuleUseCase
from app.application.recurring.use_cases.delete_recurring_rule import DeleteRecurringRuleUseCase
from app.application.recurring.use_cases.fire_due_rules import FireDueRulesUseCase
from app.application.recurring.use_cases.get_recurring_rule import GetRecurringRuleUseCase
from app.application.recurring.use_cases.list_recurring_rules import ListRecurringRulesUseCase
from app.application.recurring.use_cases.update_recurring_rule import UpdateRecurringRuleUseCase
from app.application.search.ports.search_cache import SearchCache
from app.application.search.ports.transaction_reader import (
    TransactionReader as SearchTransactionReader,
)
from app.application.search.ports.transaction_searcher import TransactionSearcher
from app.application.search.use_cases.search_transactions import SearchTransactionsUseCase
from app.application.transactions.ports.budget_summary_reader import (
    BudgetSummaryReader as TxBudgetSummaryReader,
)
from app.application.transactions.ports.category_list_reader import CategoryListReader
from app.application.transactions.ports.spend_trend_reader import SpendTrendReader
from app.application.transactions.ports.transaction_repository import TransactionRepository
from app.application.transactions.ports.transaction_text_parser import TransactionTextParser
from app.application.transactions.use_cases.create_transaction import CreateTransactionUseCase
from app.application.transactions.use_cases.delete_transaction import DeleteTransactionUseCase
from app.application.transactions.use_cases.get_budget_summary import GetBudgetSummaryUseCase
from app.application.transactions.use_cases.get_spend_trend import GetSpendTrendUseCase
from app.application.transactions.use_cases.get_transaction import GetTransactionUseCase
from app.application.transactions.use_cases.list_transactions import ListTransactionsUseCase
from app.application.transactions.use_cases.parse_transaction_text import (
    ParseTransactionTextUseCase,
)
from app.application.transactions.use_cases.update_transaction import UpdateTransactionUseCase
from app.application.users.ports.audit_event_reader import AuditEventReader
from app.application.users.ports.mailer import Mailer
from app.application.users.ports.password_reset_token_store import PasswordResetTokenStore
from app.application.users.ports.session_store import SessionStore
from app.application.users.ports.token_decoder import TokenDecoder
from app.application.users.ports.token_encoder import TokenEncoder
from app.application.users.ports.user_repository import UserRepository
from app.application.users.use_cases.change_password import ChangePasswordUseCase
from app.application.users.use_cases.confirm_password_reset import ConfirmPasswordResetUseCase
from app.application.users.use_cases.create_user import CreateUserUseCase
from app.application.users.use_cases.list_audit_events import ListAuditEventsUseCase
from app.application.users.use_cases.login import LoginUseCase
from app.application.users.use_cases.logout import LogoutUseCase
from app.application.users.use_cases.start_password_reset import StartPasswordResetUseCase
from app.domain.ports.id_generator import (
    CategoryIdGenerator,
    InsightIdGenerator,
    PasswordResetTokenIdGenerator,
    RecurringRuleIdGenerator,
    SessionIdGenerator,
    TransactionIdGenerator,
    UserIdGenerator,
)
from app.domain.ports.password_hasher import PasswordHasher
from app.inbound.http.auth.cookie_manager import CookieManager, CookieName, SessionTtl
from app.inbound.http.auth.identity import resolve_identity
from app.main.config.settings import (
    AppSettings,
    AuthSettings,
    ChatSettings,
    DatabaseSettings,
    IngestionSettings,
    InsightWorkerSettings,
    OpenAISettings,
    RedisSettings,
)
from app.outbound.adapters.image.preprocessor import PillowImagePreprocessor
from app.outbound.adapters.openai._gateway import (
    OpenAIGateway,
    OpenAIGatewayConfig,
    build_openai_gateway,
)
from app.outbound.adapters.openai.chat_client import OpenAIChatClient
from app.outbound.adapters.openai.receipt_extractor import OpenAIReceiptExtractor
from app.outbound.adapters.openai.transaction_text_parser import OpenAITransactionTextParser
from app.outbound.adapters.redis.chat_token_budget import RedisChatTokenBudget
from app.outbound.adapters.redis.search_cache import RedisSearchCache
from app.outbound.adapters.redis.session_store import RedisSessionStore
from app.outbound.adapters.sqla.alerts.alert_repository import SqlaAlertRepository
from app.outbound.adapters.sqla.categories.category_repository import SqlaCategoryRepository
from app.outbound.adapters.sqla.chat.chat_history_store import SqlaChatHistoryStore
from app.outbound.adapters.sqla.chat.chat_tools_reader import SqlaChatToolsReader
from app.outbound.adapters.sqla.chat.work_unit_factory import SqlaChatWorkUnitFactory
from app.outbound.adapters.sqla.common.flusher import SqlaFlusher
from app.outbound.adapters.sqla.common.outbox_repository import SqlaOutboxRepository
from app.outbound.adapters.sqla.common.quota_check import SqlaQuotaCheck
from app.outbound.adapters.sqla.insights.insight_repository import SqlaInsightRepository
from app.outbound.adapters.sqla.insights.transaction_reader import SqlaTransactionReader
from app.outbound.adapters.sqla.insights.work_unit_factory import SqlaInsightWorkUnitFactory
from app.outbound.adapters.sqla.recurring.recurring_rule_repository import (
    SqlaRecurringRuleRepository,
)
from app.outbound.adapters.sqla.search.transaction_reader import SqlaSearchTransactionReader
from app.outbound.adapters.sqla.search.transaction_searcher import SqlaTransactionSearcher
from app.outbound.adapters.sqla.transactions.category_list_reader import SqlaCategoryListReader
from app.outbound.adapters.sqla.transactions.sqla_budget_summary_reader import (
    SqlaBudgetSummaryReader as SqlaTxBudgetSummaryReader,
)
from app.outbound.adapters.sqla.transactions.sqla_spend_trend_reader import SqlaSpendTrendReader
from app.outbound.adapters.sqla.transactions.transaction_repository import (
    SqlaTransactionRepository,
)
from app.outbound.adapters.sqla.users.audit_event_reader import SqlaAuditEventReader
from app.outbound.adapters.sqla.users.audit_log import SqlaAuditLog
from app.outbound.adapters.sqla.users.password_reset_token_store import SqlaPasswordResetTokenStore
from app.outbound.adapters.sqla.users.user_plan_lookup import SqlaUserPlanLookup
from app.outbound.adapters.sqla.users.user_repository import SqlaUserRepository
from app.outbound.adapters.system.bcrypt_password_hasher import BcryptPasswordHasher
from app.outbound.adapters.system.clock import SystemClock
from app.outbound.adapters.system.config_upload_policy import ConfigUploadPolicy
from app.outbound.adapters.system.smtp_mailer import SmtpMailer
from app.outbound.adapters.system.stdout_mailer import StdoutMailer
from app.outbound.adapters.system.uuid7_id_generator import (
    Uuid7CategoryIdGenerator,
    Uuid7ChatTurnIdGenerator,
    Uuid7InsightIdGenerator,
    Uuid7PasswordResetTokenIdGenerator,
    Uuid7RecurringRuleIdGenerator,
    Uuid7SessionIdGenerator,
    Uuid7TransactionIdGenerator,
    Uuid7UserIdGenerator,
)
from app.outbound.auth.jwt import JwtCodec

# ── Infra / framework providers ───────────────────────────────────────────────


class InfraProvider(Provider):
    redis = from_context(provides=Redis, scope=Scope.APP)
    app_settings = from_context(provides=AppSettings, scope=Scope.APP)
    db_settings = from_context(provides=DatabaseSettings, scope=Scope.APP)
    redis_settings = from_context(provides=RedisSettings, scope=Scope.APP)
    auth_settings = from_context(provides=AuthSettings, scope=Scope.APP)
    openai_settings = from_context(provides=OpenAISettings, scope=Scope.APP)
    ingestion_settings = from_context(provides=IngestionSettings, scope=Scope.APP)
    chat_settings = from_context(provides=ChatSettings, scope=Scope.APP)
    insight_worker_settings = from_context(provides=InsightWorkerSettings, scope=Scope.APP)

    @provide(scope=Scope.APP)
    def insight_worker_config(self, s: InsightWorkerSettings) -> InsightWorkerConfig:
        return InsightWorkerConfig(
            min_transactions_for_insight=s.min_transactions_for_insight,
            reaper_lease_minutes=s.reaper_lease_minutes,
        )


class PersistenceProvider(Provider):
    @provide(scope=Scope.APP)
    async def engine(self, cfg: DatabaseSettings) -> AsyncIterator[AsyncEngine]:
        pool_kwargs: dict[str, Any] = (
            {"poolclass": NullPool}
            if cfg.db_use_null_pool
            else {
                "pool_pre_ping": True,
                "pool_size": cfg.db_pool_size,
                "max_overflow": cfg.db_max_overflow,
                "pool_recycle": cfg.db_pool_recycle_seconds,
            }
        )
        engine = create_async_engine(cfg.database_url, echo=False, **pool_kwargs)

        yield engine
        await engine.dispose()

    @provide(scope=Scope.APP)
    def session_factory(self, engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
        return async_sessionmaker(engine, autoflush=False, expire_on_commit=False)

    @provide(scope=Scope.REQUEST)
    async def session(
        self, factory: async_sessionmaker[AsyncSession]
    ) -> AsyncIterator[AsyncSession]:
        # Request-scoped unit of work. dishka finalizes generator providers via
        # ``agen.asend(exception)``, so the exception raised by the handler is the
        # *value* returned by ``yield`` — it is NOT re-raised inside this frame.
        # ``factory.begin()`` would therefore commit on every request, even failed
        # ones, masking the real error behind ``InFailedSQLTransactionError`` at
        # commit time. Commit only on success; roll back otherwise.
        async with factory() as session:
            exception = yield session
            if exception is None:
                await session.commit()
            else:
                await session.rollback()


class RequestProvider(Provider):
    request = from_context(provides=Request, scope=Scope.REQUEST)


# ── Common cross-cutting adapters ─────────────────────────────────────────────


class CommonAdaptersProvider(Provider):
    scope = Scope.REQUEST

    outbox_repo = provide(SqlaOutboxRepository, provides=OutboxRepository)
    flusher = provide(SqlaFlusher, provides=Flusher)

    @provide(scope=Scope.APP)
    def clock(self) -> Clock:
        return SystemClock()

    @provide(scope=Scope.APP)
    async def openai_gateway(self, cfg: OpenAISettings) -> AsyncIterator[OpenAIGateway]:
        gateway_cfg = OpenAIGatewayConfig(
            api_key=cfg.openai_api_key,
            max_connections=cfg.openai_max_connections,
            max_keepalive_connections=cfg.openai_max_keepalive_connections,
            connect_timeout_seconds=cfg.openai_connect_timeout_seconds,
            read_timeout_chat_seconds=cfg.openai_read_timeout_chat_seconds,
            max_retries=cfg.openai_max_retries,
            rpm_per_endpoint=cfg.openai_rpm_per_endpoint,
            max_queue=cfg.openai_limiter_max_queue,
            circuit_fail_max=cfg.openai_circuit_fail_max,
            circuit_reset_seconds=cfg.openai_circuit_reset_seconds,
        )
        gateway, http_client = await build_openai_gateway(gateway_cfg)
        try:
            yield gateway
        finally:
            await http_client.aclose()

    @provide(scope=Scope.REQUEST)
    def quota_check(self, session: AsyncSession) -> QuotaCheck:
        return SqlaQuotaCheck(session=session)

    @provide(scope=Scope.APP)
    def cookie_name(self, cfg: AuthSettings) -> CookieName:
        return CookieName(cfg.cookie_name)

    @provide(scope=Scope.APP)
    def session_ttl(self, cfg: AuthSettings) -> SessionTtl:
        return SessionTtl(timedelta(minutes=cfg.session_expire_minutes))

    cookie_manager = provide(CookieManager, scope=Scope.REQUEST)

    @provide(scope=Scope.REQUEST)
    async def identity_context(
        self,
        cookie_manager: CookieManager,
        decoder: TokenDecoder,
        session_store: SessionStore,
    ) -> IdentityContext:
        return await resolve_identity(cookie_manager, decoder, session_store)


# ── Users ─────────────────────────────────────────────────────────────────────


class UsersAdaptersProvider(Provider):
    scope = Scope.REQUEST

    user_repo = provide(SqlaUserRepository, provides=UserRepository)
    user_plan_lookup = provide(SqlaUserPlanLookup, provides=UserPlanLookup)
    audit_log = provide(SqlaAuditLog, provides=AuditLog)
    audit_event_reader = provide(SqlaAuditEventReader, provides=AuditEventReader)
    token_store = provide(SqlaPasswordResetTokenStore, provides=PasswordResetTokenStore)
    session_store = provide(RedisSessionStore, provides=SessionStore)

    @provide(scope=Scope.APP)
    def mailer(self, cfg: AppSettings) -> Mailer:
        if cfg.smtp_host:
            if not cfg.smtp_from_email:
                raise RuntimeError(
                    "SMTP_FROM_EMAIL must be set when SMTP_HOST is configured. "
                    "Set a sender address or clear SMTP_HOST to fall back to StdoutMailer."
                )
            return SmtpMailer(
                host=cfg.smtp_host,
                port=cfg.smtp_port,
                username=cfg.smtp_username,
                password=cfg.smtp_password,
                from_email=cfg.smtp_from_email,
                use_starttls=cfg.smtp_starttls,
                timeout=cfg.smtp_timeout_seconds,
            )
        if not cfg.debug:
            structlog.get_logger(__name__).warning(
                "stdout_mailer_in_use",
                note="StdoutMailer is active in a non-debug environment. "
                "Password-reset emails are written to the log, not delivered. "
                "Set SMTP_HOST before going to production.",
            )
        return StdoutMailer()

    user_id_gen = provide(Uuid7UserIdGenerator, provides=UserIdGenerator)
    session_id_gen = provide(Uuid7SessionIdGenerator, provides=SessionIdGenerator)
    token_id_gen = provide(
        Uuid7PasswordResetTokenIdGenerator, provides=PasswordResetTokenIdGenerator
    )

    @provide(scope=Scope.APP)
    def hasher(self, cfg: AppSettings) -> PasswordHasher:
        pool = ThreadPoolExecutor(
            max_workers=cfg.hasher_thread_pool_size, thread_name_prefix="bcrypt"
        )
        return BcryptPasswordHasher(thread_pool=pool)

    @provide(scope=Scope.APP)
    def jwt_codec(self, cfg: AuthSettings) -> JwtCodec:
        return JwtCodec(
            signing_key=cfg.jwt_secret,
            algorithm=cfg.jwt_algorithm,
            verification_keys=cfg.jwt_verification_key_list,
        )

    @provide(scope=Scope.APP)
    def token_decoder(self, cfg: AuthSettings) -> TokenDecoder:
        return JwtCodec(
            signing_key=cfg.jwt_secret,
            algorithm=cfg.jwt_algorithm,
            verification_keys=cfg.jwt_verification_key_list,
        )

    @provide(scope=Scope.APP)
    def token_encoder(self, cfg: AuthSettings) -> TokenEncoder:
        return JwtCodec(
            signing_key=cfg.jwt_secret,
            algorithm=cfg.jwt_algorithm,
            verification_keys=cfg.jwt_verification_key_list,
        )

    # Use cases
    create_user = provide(CreateUserUseCase)
    logout = provide(LogoutUseCase)
    change_password = provide(ChangePasswordUseCase)
    start_reset = provide(StartPasswordResetUseCase)
    confirm_reset = provide(ConfirmPasswordResetUseCase)
    list_audit_events = provide(ListAuditEventsUseCase)

    @provide
    def login(
        self,
        user_repo: UserRepository,
        hasher: PasswordHasher,
        session_store: SessionStore,
        session_id_gen: SessionIdGenerator,
        audit_log: AuditLog,
        cfg: AuthSettings,
    ) -> LoginUseCase:
        return LoginUseCase(
            user_repo=user_repo,
            password_hasher=hasher,
            session_store=session_store,
            session_id_generator=session_id_gen,
            audit_log=audit_log,
            session_ttl=timedelta(minutes=cfg.session_expire_minutes),
        )


# ── Transactions ──────────────────────────────────────────────────────────────


class TransactionsAdaptersProvider(Provider):
    scope = Scope.REQUEST

    transaction_repo = provide(SqlaTransactionRepository, provides=TransactionRepository)
    category_list_reader = provide(SqlaCategoryListReader, provides=CategoryListReader)
    tx_budget_summary_reader = provide(SqlaTxBudgetSummaryReader, provides=TxBudgetSummaryReader)
    spend_trend_reader = provide(SqlaSpendTrendReader, provides=SpendTrendReader)
    transaction_id_gen = provide(Uuid7TransactionIdGenerator, provides=TransactionIdGenerator)

    @provide(scope=Scope.APP)
    def transaction_text_parser(
        self, gateway: OpenAIGateway, cfg: OpenAISettings
    ) -> TransactionTextParser:
        return OpenAITransactionTextParser(
            gateway=gateway,
            model=cfg.openai_model_chat,
            read_timeout_seconds=cfg.openai_read_timeout_chat_seconds,
        )

    # Use cases
    create_transaction = provide(CreateTransactionUseCase)
    list_transactions = provide(ListTransactionsUseCase)
    get_transaction = provide(GetTransactionUseCase)
    delete_transaction = provide(DeleteTransactionUseCase)
    update_transaction = provide(UpdateTransactionUseCase)
    get_budget_summary = provide(GetBudgetSummaryUseCase)
    get_spend_trend = provide(GetSpendTrendUseCase)
    parse_transaction_text = provide(ParseTransactionTextUseCase)


# ── Categories ────────────────────────────────────────────────────────────────


class CategoriesAdaptersProvider(Provider):
    scope = Scope.REQUEST

    category_repo = provide(SqlaCategoryRepository, provides=CategoryRepository)
    category_id_gen = provide(Uuid7CategoryIdGenerator, provides=CategoryIdGenerator)

    create_category = provide(CreateCategoryUseCase)
    list_categories = provide(ListCategoriesUseCase)


# ── Insights ──────────────────────────────────────────────────────────────────


class InsightsAdaptersProvider(Provider):
    scope = Scope.REQUEST

    insight_repo = provide(SqlaInsightRepository, provides=InsightRepository)
    insight_id_gen = provide(Uuid7InsightIdGenerator, provides=InsightIdGenerator)
    transaction_reader = provide(SqlaTransactionReader, provides=TransactionReader)

    @provide
    def request_insight(
        self,
        insight_repo: InsightRepository,
        outbox_repo: OutboxRepository,
        transaction_reader: TransactionReader,
        id_generator: InsightIdGenerator,
        user_plan_lookup: UserPlanLookup,
        quota_check: QuotaCheck,
        settings: InsightWorkerConfig,
    ) -> RequestInsightUseCase:
        return RequestInsightUseCase(
            insight_repo=insight_repo,
            outbox_repo=outbox_repo,
            transaction_reader=transaction_reader,
            id_generator=id_generator,
            user_plan_lookup=user_plan_lookup,
            quota_check=quota_check,
            settings=settings,
        )

    get_insight = provide(GetInsightUseCase)
    list_insights = provide(ListInsightsUseCase)

    @provide(scope=Scope.APP)
    def insight_work_unit_factory(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> InsightWorkUnitFactory:
        return SqlaInsightWorkUnitFactory(session_factory)

    @provide(scope=Scope.REQUEST)
    def stream_insight(self, factory: InsightWorkUnitFactory) -> StreamInsightUseCase:
        # StreamInsightUseCase has keyword-only ctor args with defaults that dishka
        # would otherwise try (and fail) to resolve, so build it explicitly.
        return StreamInsightUseCase(factory)


# ── Chat ──────────────────────────────────────────────────────────────────────


class ChatAdaptersProvider(Provider):
    scope = Scope.REQUEST

    history_store = provide(SqlaChatHistoryStore, provides=ChatHistoryStore)
    chat_turn_id_gen = provide(
        Uuid7ChatTurnIdGenerator, provides=ChatTurnIdGenerator, scope=Scope.APP
    )

    @provide(scope=Scope.APP)
    def chat_token_budget(self, redis: Redis, cfg: ChatSettings) -> ChatTokenBudget:  # type: ignore[type-arg]
        return RedisChatTokenBudget(redis=redis, daily_token_limit=cfg.chat_daily_token_limit)

    @provide(scope=Scope.REQUEST)
    def chat_ai_client(
        self,
        gateway: OpenAIGateway,
        settings: OpenAISettings,
        chat_cfg: ChatSettings,
    ) -> ChatAIClient:
        return OpenAIChatClient(
            gateway=gateway,
            model=settings.openai_model_chat,
            read_timeout_seconds=settings.openai_read_timeout_chat_seconds,
            max_tool_iterations=chat_cfg.chat_max_tool_iterations,
        )

    @provide(scope=Scope.APP)
    def chat_work_unit_factory(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> ChatWorkUnitFactory:
        return SqlaChatWorkUnitFactory(session_factory)

    @provide(scope=Scope.APP)
    def chat_tools(
        self, session_factory: async_sessionmaker[AsyncSession], clock: Clock
    ) -> ChatTools:
        # APP-scoped, like the work-unit factory: SqlaChatToolsReader opens a fresh
        # short session per tool call, so it never pins the REQUEST session across
        # the OpenAI tool-selection round-trips (ARCHITECTURE §10.4 / bug B14).
        return SqlaChatToolsReader(session_factory=session_factory, clock=clock)

    @provide(scope=Scope.REQUEST)
    def chat_query(
        self,
        work_unit_factory: ChatWorkUnitFactory,
        ai_client: ChatAIClient,
        token_budget: ChatTokenBudget,
        id_generator: ChatTurnIdGenerator,
        clock: Clock,
        chat_tools: ChatTools,
    ) -> ChatQueryUseCase:
        return ChatQueryUseCase(
            work_unit_factory=work_unit_factory,
            ai_client=ai_client,
            token_budget=token_budget,
            id_generator=id_generator,
            clock=clock,
            chat_tools=chat_tools,
        )

    @provide(scope=Scope.REQUEST)
    def chat_stream(
        self,
        work_unit_factory: ChatWorkUnitFactory,
        ai_client: ChatAIClient,
        token_budget: ChatTokenBudget,
        id_generator: ChatTurnIdGenerator,
        clock: Clock,
        chat_tools: ChatTools,
    ) -> ChatStreamUseCase:
        return ChatStreamUseCase(
            work_unit_factory=work_unit_factory,
            ai_client=ai_client,
            token_budget=token_budget,
            id_generator=id_generator,
            clock=clock,
            chat_tools=chat_tools,
        )

    list_chat_history = provide(ListChatHistoryUseCase)
    clear_chat_history = provide(ClearChatHistoryUseCase)


# ── Search ────────────────────────────────────────────────────────────────────


class SearchAdaptersProvider(Provider):
    scope = Scope.REQUEST

    search_tx_reader = provide(SqlaSearchTransactionReader, provides=SearchTransactionReader)
    transaction_searcher = provide(SqlaTransactionSearcher, provides=TransactionSearcher)

    @provide(scope=Scope.REQUEST)
    def search_cache(self, redis: Redis, cfg: RedisSettings) -> SearchCache:  # type: ignore[type-arg]
        return RedisSearchCache(redis=redis, ttl=cfg.search_cache_ttl_seconds)

    search_transactions = provide(SearchTransactionsUseCase)


# ── Alerts ────────────────────────────────────────────────────────────────────


class AlertsAdaptersProvider(Provider):
    scope = Scope.REQUEST

    alert_repo = provide(SqlaAlertRepository, provides=AlertRepository)
    list_alerts = provide(ListAlertsUseCase)
    mark_alert_read = provide(MarkAlertReadUseCase)
    clear_alerts = provide(ClearAlertsUseCase)


# ── Recurring ─────────────────────────────────────────────────────────────────


class RecurringAdaptersProvider(Provider):
    @provide(scope=Scope.APP)
    def recurring_rule_id_generator(self) -> RecurringRuleIdGenerator:
        return Uuid7RecurringRuleIdGenerator()

    @provide(scope=Scope.REQUEST)
    def recurring_rule_repo(self, session: AsyncSession) -> RecurringRuleRepositoryPort:
        return SqlaRecurringRuleRepository(session)

    @provide(scope=Scope.REQUEST)
    def create_recurring_rule(
        self,
        repo: RecurringRuleRepositoryPort,
        id_gen: RecurringRuleIdGenerator,
    ) -> CreateRecurringRuleUseCase:
        return CreateRecurringRuleUseCase(repo=repo, id_generator=id_gen)

    @provide(scope=Scope.REQUEST)
    def get_recurring_rule(self, repo: RecurringRuleRepositoryPort) -> GetRecurringRuleUseCase:
        return GetRecurringRuleUseCase(repo=repo)

    @provide(scope=Scope.REQUEST)
    def list_recurring_rules(self, repo: RecurringRuleRepositoryPort) -> ListRecurringRulesUseCase:
        return ListRecurringRulesUseCase(repo=repo)

    @provide(scope=Scope.REQUEST)
    def update_recurring_rule(
        self, repo: RecurringRuleRepositoryPort
    ) -> UpdateRecurringRuleUseCase:
        return UpdateRecurringRuleUseCase(repo=repo)

    @provide(scope=Scope.REQUEST)
    def delete_recurring_rule(
        self, repo: RecurringRuleRepositoryPort
    ) -> DeleteRecurringRuleUseCase:
        return DeleteRecurringRuleUseCase(repo=repo)

    @provide(scope=Scope.REQUEST)
    def fire_due_rules(
        self,
        repo: RecurringRuleRepositoryPort,
        create_tx: CreateTransactionUseCase,
    ) -> FireDueRulesUseCase:
        return FireDueRulesUseCase(repo=repo, create_transaction=create_tx)


# ── Ingestion ─────────────────────────────────────────────────────────────────


class IngestionAdaptersProvider(Provider):
    @provide(scope=Scope.APP)
    def upload_policy(self, cfg: IngestionSettings) -> UploadPolicy:
        return ConfigUploadPolicy(max_bytes=cfg.ingestion_max_upload_size_mb * 1024 * 1024)

    @provide(scope=Scope.APP)
    def image_thread_pool(self) -> Iterator[ThreadPoolExecutor]:
        pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="image-preprocess")
        try:
            yield pool
        finally:
            pool.shutdown(wait=True)

    @provide(scope=Scope.APP)
    def image_preprocessor(
        self, cfg: IngestionSettings, thread_pool: ThreadPoolExecutor
    ) -> ImagePreprocessor:
        return PillowImagePreprocessor(
            semaphore=asyncio.Semaphore(cfg.ingestion_image_processing_concurrency),
            max_dimension=cfg.ingestion_max_image_dimension,
            jpeg_quality=cfg.ingestion_jpeg_quality,
            thread_pool=thread_pool,
        )

    @provide(scope=Scope.APP)
    def receipt_extractor(self, gateway: OpenAIGateway, cfg: IngestionSettings) -> ReceiptExtractor:
        return OpenAIReceiptExtractor(
            gateway=gateway,
            model=cfg.ingestion_vision_model,
            timeout_seconds=cfg.ingestion_vision_timeout_seconds,
        )

    parse_receipt = provide(ParseReceiptUseCase, scope=Scope.REQUEST)


def all_providers() -> tuple[Provider, ...]:
    # Dishka resolves across providers, so order is for readability only.
    return (
        # Framework / infra
        InfraProvider(),
        PersistenceProvider(),
        RequestProvider(),
        # Cross-cutting
        CommonAdaptersProvider(),
        # Bounded contexts
        UsersAdaptersProvider(),
        TransactionsAdaptersProvider(),
        CategoriesAdaptersProvider(),
        InsightsAdaptersProvider(),
        ChatAdaptersProvider(),
        SearchAdaptersProvider(),
        AlertsAdaptersProvider(),
        RecurringAdaptersProvider(),
        IngestionAdaptersProvider(),
    )
