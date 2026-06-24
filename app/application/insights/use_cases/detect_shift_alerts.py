import structlog

from app.application.insights.ports.alert_writer import AlertWriter
from app.application.insights.ports.budget_summary_reader import BudgetSummaryReader
from app.domain.services.behavioral_shift_detector import BehavioralShiftDetector
from app.domain.services.monthly_aggregator import (
    MonthlyAggregation,
    TransactionRow,
    aggregate,
)
from app.domain.value_objects.ids import UserId

logger = structlog.get_logger(__name__)

_N_HISTORY_MONTHS = 3


class DetectShiftAlertsUseCase:
    """Deterministic behavioral-shift alert generation.

    Aggregates the period + its history from SQL, runs shift detection, and writes
    alerts. Depends only on ports + domain services, so it is fully unit-testable
    with fakes and never touches OpenAI.
    """

    def __init__(
        self,
        budget_reader: BudgetSummaryReader,
        alert_writer: AlertWriter,
        detector: BehavioralShiftDetector | None = None,
    ) -> None:
        self._budget = budget_reader
        self._alert_writer = alert_writer
        self._detector = detector or BehavioralShiftDetector()

    async def __call__(self, user_id: UserId, year: int, month: int) -> None:
        current_rows = await self._budget.read_month(user_id, year, month)
        if not current_rows:
            return

        current_aggs = aggregate(
            year,
            month,
            [
                TransactionRow(
                    amount=r.amount,
                    currency=r.currency,
                    type_=r.type_,
                    category_label=r.category_label,
                    day_of_month=r.day_of_month,
                )
                for r in current_rows
            ],
        )

        history_raw = await self._budget.read_history_months(
            user_id, year, month, _N_HISTORY_MONTHS
        )
        history_aggs: list[MonthlyAggregation] = []
        for (hy, hm), hrows in sorted(history_raw.items()):
            if hrows:
                history_aggs.extend(
                    aggregate(
                        hy,
                        hm,
                        [
                            TransactionRow(
                                amount=r.amount,
                                currency=r.currency,
                                type_=r.type_,
                                category_label=r.category_label,
                                day_of_month=r.day_of_month,
                            )
                            for r in hrows
                        ],
                    )
                )

        if not current_aggs or len(history_aggs) < 2:
            return

        primary = current_aggs[0]
        same_currency_history = [h for h in history_aggs if h.currency == primary.currency]
        shifts = self._detector.detect(primary, same_currency_history)
        if not shifts:
            return

        await self._alert_writer.write_shift_alerts(user_id, year, month, shifts)
