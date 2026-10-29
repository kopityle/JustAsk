from app.services.query_expansion import parse_expanded_queries, should_expand_query


def _chunk(distance):
    return {"document": "doc", "page": 1, "text": "text", "distance": distance}


def test_should_expand_only_for_empty_abbreviation_query():
    assert should_expand_query("Сформулируй требования 1НФ", []) is True
    assert should_expand_query("Сформулируй требования 1НФ", [_chunk(None)]) is False
    assert should_expand_query("Сформулируй требования 1НФ", [_chunk(0.4)]) is False
    assert should_expand_query("Закон Фарадея", []) is False


def test_parse_expanded_queries_strips_numbering_and_deduplicates():
    raw = "1. первая нормальная форма\n- вторая нормальная форма\n• первая нормальная форма\n"
    assert parse_expanded_queries(raw) == [
        "первая нормальная форма",
        "вторая нормальная форма",
    ]
