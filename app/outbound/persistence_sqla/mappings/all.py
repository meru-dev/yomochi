_mapped: bool = False


def map_tables() -> None:
    global _mapped
    if _mapped:
        return
    _mapped = True

    from app.outbound.persistence_sqla.mappings.category import map_category
    from app.outbound.persistence_sqla.mappings.insight import map_insight
    from app.outbound.persistence_sqla.mappings.recurring_rule import map_recurring_rule
    from app.outbound.persistence_sqla.mappings.transaction import map_transaction
    from app.outbound.persistence_sqla.mappings.user import map_user

    map_user()
    map_transaction()
    map_category()
    map_insight()
    map_recurring_rule()
