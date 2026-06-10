from app.application.search.ports.search_cache import SearchCache
from app.application.search.ports.transaction_reader import TransactionReader
from app.application.search.ports.transaction_searcher import TransactionSearcher
from app.domain.entities.transaction import Transaction
from app.domain.value_objects.ids import TransactionId, UserId


class SearchTransactionsUseCase:
    def __init__(
        self,
        cache: SearchCache,
        searcher: TransactionSearcher,
        tx_reader: TransactionReader,
    ) -> None:
        self._cache = cache
        self._searcher = searcher
        self._tx_reader = tx_reader

    async def __call__(self, user_id: UserId, query: str, limit: int = 20) -> list[Transaction]:
        cached_ids = await self._cache.get(user_id, query)
        if cached_ids is not None:
            ids = [TransactionId(uid) for uid in cached_ids[:limit]]
            return await self._tx_reader.get_by_ids(ids, user_id)

        transactions = await self._searcher.search(user_id, query, limit)
        await self._cache.set(user_id, query, [tx.id_.value for tx in transactions])
        return transactions
