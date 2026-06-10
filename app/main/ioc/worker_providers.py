from collections.abc import AsyncIterator
from typing import Any

from dishka import Provider, Scope, from_context, provide
from faststream.kafka import KafkaBroker
from redis.asyncio import Redis
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.application.alerts.ports.alert_repository import AlertRepository
from app.application.common.ports.consumer_idempotency_store import ConsumerIdempotencyStore
from app.application.common.ports.event_publisher import EventPublisher
from app.application.common.ports.metrics_recorder import MetricsRecorder
from app.application.common.ports.outbox_repository import OutboxRepository
from app.application.common.ports.quota_check import QuotaCheck
from app.application.common.ports.text_embedder import TextEmbedder
from app.application.common.ports.user_plan_lookup import UserPlanLookup
from app.application.insights.ports.ai_insight_client import AIInsightClient
from app.application.insights.ports.alert_writer import AlertWriter
from app.application.insights.ports.budget_summary_reader import BudgetSummaryReader
from app.application.insights.ports.chunk_retriever import ChunkRetriever
from app.application.insights.ports.chunk_writer import ChunkWriter
from app.application.insights.ports.dirty_period_repository import DirtyPeriodRepository
from app.application.insights.ports.insight_repository import InsightRepository
from app.application.insights.ports.portrait_queue import PortraitQueue
from app.application.insights.ports.transaction_reader import TransactionReader
from app.application.insights.ports.work_unit import InsightWorkUnitFactory
from app.application.insights.use_cases.process_insight import ProcessInsightUseCase
from app.application.recurring.ports.recurring_rule_repository import RecurringRuleRepository
from app.application.recurring.use_cases.fire_due_rules import FireDueRulesUseCase
from app.application.transactions.ports.category_list_reader import CategoryListReader
from app.application.transactions.ports.transaction_repository import TransactionRepository
from app.application.transactions.use_cases.create_transaction import CreateTransactionUseCase
from app.domain.ports.id_generator import InsightIdGenerator, TransactionIdGenerator
from app.domain.services.behavioral_shift_detector import BehavioralShiftDetector
from app.main.config.settings import DatabaseSettings, KafkaSettings, OpenAISettings
from app.outbound.adapters.kafka.event_publisher import KafkaEventPublisher
from app.outbound.adapters.openai._gateway import (
    OpenAIGateway,
    OpenAIGatewayConfig,
    build_openai_gateway,
)
from app.outbound.adapters.openai.insight_client import OpenAIInsightClient
from app.outbound.adapters.openai.text_embedder import OpenAITextEmbedder
from app.outbound.adapters.redis.consumer_idempotency_store import RedisConsumerIdempotencyStore
from app.outbound.adapters.sqla.alerts.alert_repository import SqlaAlertRepository
from app.outbound.adapters.sqla.alerts.alert_writer import SqlaAlertWriter
from app.outbound.adapters.sqla.common.outbox_repository import SqlaOutboxRepository
from app.outbound.adapters.sqla.insights.budget_summary_reader import SqlaBudgetSummaryReader
from app.outbound.adapters.sqla.insights.chunk_retriever import SqlaChunkRetriever
from app.outbound.adapters.sqla.insights.chunk_writer import SqlaChunkWriter
from app.outbound.adapters.sqla.insights.dirty_period_repository import SqlaDirtyPeriodRepository
from app.outbound.adapters.sqla.insights.insight_repository import SqlaInsightRepository
from app.outbound.adapters.sqla.insights.portrait_queue import SqlaPortraitQueue
from app.outbound.adapters.sqla.insights.transaction_reader import SqlaTransactionReader
from app.outbound.adapters.sqla.insights.work_unit_factory import SqlaInsightWorkUnitFactory
from app.outbound.adapters.sqla.recurring.recurring_rule_repository import (
    SqlaRecurringRuleRepository,
)
from app.outbound.adapters.sqla.transactions.category_list_reader import SqlaCategoryListReader
from app.outbound.adapters.sqla.transactions.transaction_repository import SqlaTransactionRepository
from app.outbound.adapters.sqla.users.user_plan_lookup import SqlaUserPlanLookup
from app.outbound.adapters.system.noop_quota_check import NoOpQuotaCheck
from app.outbound.adapters.system.uuid7_id_generator import (
    Uuid7InsightIdGenerator,
    Uuid7TransactionIdGenerator,
)
from app.outbound.observability.prometheus_metrics_recorder import PrometheusMetricsRecorder


class WorkerInfraProvider(Provider):
    """DB engine + session + OpenAI gateway + behavioral detector.

    Used by every worker process. Per-process gateway = per-process circuit breaker.
    Redis + KafkaBroker are passed via context only when the worker actually needs them.
    """

    db_settings = from_context(provides=DatabaseSettings, scope=Scope.APP)
    openai_settings = from_context(provides=OpenAISettings, scope=Scope.APP)

    @provide(scope=Scope.APP)
    async def engine(self, cfg: DatabaseSettings) -> AsyncIterator[AsyncEngine]:
        engine = create_async_engine(
            cfg.database_url,
            pool_pre_ping=True,
            pool_size=cfg.db_pool_size,
            max_overflow=cfg.db_max_overflow,
            pool_recycle=cfg.db_pool_recycle_seconds,
        )

        @event.listens_for(engine.sync_engine, "connect")
        def _set_hnsw_ef_search(dbapi_conn: Any, _conn_rec: Any) -> None:
            cursor = dbapi_conn.cursor()
            cursor.execute("SET hnsw.ef_search = 40")

        yield engine
        await engine.dispose()

    @provide(scope=Scope.APP)
    def session_factory(self, engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
        return async_sessionmaker(engine, autoflush=False, expire_on_commit=False)

    @provide(scope=Scope.REQUEST)
    async def session(
        self, factory: async_sessionmaker[AsyncSession]
    ) -> AsyncIterator[AsyncSession]:
        async with factory.begin() as session:
            yield session

    @provide(scope=Scope.APP)
    async def openai_gateway(self, cfg: OpenAISettings) -> AsyncIterator[OpenAIGateway]:
        gateway_cfg = OpenAIGatewayConfig(
            api_key=cfg.openai_api_key,
            max_connections=cfg.openai_max_connections,
            max_keepalive_connections=cfg.openai_max_keepalive_connections,
            connect_timeout_seconds=cfg.openai_connect_timeout_seconds,
            read_timeout_chat_seconds=cfg.openai_read_timeout_chat_seconds,
            max_retries=cfg.openai_max_retries,
            rpm=cfg.openai_rpm,
            circuit_fail_max=cfg.openai_circuit_fail_max,
            circuit_reset_seconds=cfg.openai_circuit_reset_seconds,
        )
        gateway, http_client = await build_openai_gateway(gateway_cfg)
        try:
            yield gateway
        finally:
            await http_client.aclose()

    @provide(scope=Scope.APP)
    def shift_detector(self) -> BehavioralShiftDetector:
        return BehavioralShiftDetector()


class WorkerAdaptersBaseProvider(Provider):
    """Adapters every Kafka-driven worker needs: idempotency store, DLQ publisher,
    metrics recorder. Requires Redis + KafkaBroker in the container context."""

    scope = Scope.APP

    kafka_settings = from_context(provides=KafkaSettings, scope=Scope.APP)
    redis = from_context(provides=Redis, scope=Scope.APP)
    kafka_broker = from_context(provides=KafkaBroker, scope=Scope.APP)

    idempotency_store = provide(RedisConsumerIdempotencyStore, provides=ConsumerIdempotencyStore)
    metrics = provide(PrometheusMetricsRecorder, provides=MetricsRecorder)

    @provide(scope=Scope.APP)
    def dlq_publisher(self, kafka_broker: KafkaBroker) -> EventPublisher:
        return KafkaEventPublisher(broker=kafka_broker)


class WorkerAdaptersInsightProvider(Provider):
    """OpenAI text embedder + insight chat client. Used only by insight-worker."""

    scope = Scope.APP

    @provide(scope=Scope.APP)
    def text_embedder(
        self,
        gateway: OpenAIGateway,
        cfg: OpenAISettings,
    ) -> OpenAITextEmbedder:
        return OpenAITextEmbedder(
            gateway=gateway,
            model=cfg.openai_model_embed,
            read_timeout_seconds=cfg.openai_read_timeout_embeddings_seconds,
        )

    @provide(scope=Scope.APP)
    def text_embedder_port(self, impl: OpenAITextEmbedder) -> TextEmbedder:
        return impl

    @provide(scope=Scope.APP)
    def ai_insight_client(
        self,
        gateway: OpenAIGateway,
        cfg: OpenAISettings,
    ) -> OpenAIInsightClient:
        return OpenAIInsightClient(
            gateway=gateway,
            model=cfg.openai_model_chat,
            read_timeout_seconds=cfg.openai_read_timeout_chat_seconds,
        )

    @provide(scope=Scope.APP)
    def ai_insight_client_port(self, impl: OpenAIInsightClient) -> AIInsightClient:
        return impl

    insight_id_gen = provide(Uuid7InsightIdGenerator, provides=InsightIdGenerator)


class PortraitAdaptersProvider(Provider):
    """OpenAI embedder only — portrait pipeline does not call chat.

    Cannot reuse WorkerAdaptersInsightProvider because portrait-worker has no
    Kafka context and we don't want it pulling chat-client config.
    """

    scope = Scope.APP

    @provide(scope=Scope.APP)
    def text_embedder(
        self,
        gateway: OpenAIGateway,
        cfg: OpenAISettings,
    ) -> OpenAITextEmbedder:
        return OpenAITextEmbedder(
            gateway=gateway,
            model=cfg.openai_model_embed,
            read_timeout_seconds=cfg.openai_read_timeout_embeddings_seconds,
        )

    @provide(scope=Scope.APP)
    def text_embedder_port(self, impl: OpenAITextEmbedder) -> TextEmbedder:
        return impl


class TransactionPersistenceProvider(Provider):
    """Minimal repo set for transaction-worker: only DirtyPeriodRepository."""

    scope = Scope.REQUEST

    dirty_period_repo = provide(SqlaDirtyPeriodRepository, provides=DirtyPeriodRepository)


class InsightPersistenceProvider(Provider):
    """Full insight repo set."""

    scope = Scope.REQUEST

    insight_repo = provide(SqlaInsightRepository, provides=InsightRepository)
    dirty_period_repo = provide(SqlaDirtyPeriodRepository, provides=DirtyPeriodRepository)
    chunk_writer = provide(SqlaChunkWriter, provides=ChunkWriter)
    chunk_retriever = provide(SqlaChunkRetriever, provides=ChunkRetriever)
    budget_reader = provide(SqlaBudgetSummaryReader, provides=BudgetSummaryReader)
    tx_reader = provide(SqlaTransactionReader, provides=TransactionReader)
    alert_writer = provide(SqlaAlertWriter, provides=AlertWriter)


class InsightUseCasesProvider(Provider):
    """ProcessInsightUseCase + its work-unit factory."""

    @provide(scope=Scope.APP)
    def insight_work_unit_factory(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> InsightWorkUnitFactory:
        return SqlaInsightWorkUnitFactory(session_factory)

    @provide(scope=Scope.REQUEST)
    def process_insight(
        self,
        factory: InsightWorkUnitFactory,
        embedder: TextEmbedder,
        ai_client: AIInsightClient,
        detector: BehavioralShiftDetector,
    ) -> ProcessInsightUseCase:
        return ProcessInsightUseCase(
            work_unit_factory=factory,
            embedder=embedder,
            ai_client=ai_client,
            shift_detector=detector,
        )


class SchedulerProvider(Provider):
    """Repos + use cases needed by scheduler-worker jobs.

    Scheduler jobs are system-driven (not Kafka or HTTP), so they bypass
    per-user quotas via NoOpQuotaCheck. Each job opens its own REQUEST scope,
    which yields a transactional session (see WorkerInfraProvider.session).
    """

    scope = Scope.REQUEST

    recurring_rule_repo = provide(SqlaRecurringRuleRepository, provides=RecurringRuleRepository)
    transaction_repo = provide(SqlaTransactionRepository, provides=TransactionRepository)
    outbox_repo = provide(SqlaOutboxRepository, provides=OutboxRepository)
    category_list_reader = provide(SqlaCategoryListReader, provides=CategoryListReader)
    user_plan_lookup = provide(SqlaUserPlanLookup, provides=UserPlanLookup)
    alert_repo = provide(SqlaAlertRepository, provides=AlertRepository)
    dirty_period_repo = provide(SqlaDirtyPeriodRepository, provides=DirtyPeriodRepository)
    portrait_queue = provide(SqlaPortraitQueue, provides=PortraitQueue)
    insight_repo = provide(SqlaInsightRepository, provides=InsightRepository)

    @provide(scope=Scope.APP)
    def transaction_id_generator(self) -> TransactionIdGenerator:
        return Uuid7TransactionIdGenerator()

    @provide(scope=Scope.APP)
    def quota_check(self) -> QuotaCheck:
        return NoOpQuotaCheck()

    create_transaction = provide(CreateTransactionUseCase, scope=Scope.REQUEST)

    @provide(scope=Scope.REQUEST)
    def fire_due_rules(
        self,
        repo: RecurringRuleRepository,
        create_tx: CreateTransactionUseCase,
    ) -> FireDueRulesUseCase:
        return FireDueRulesUseCase(repo=repo, create_transaction=create_tx)
