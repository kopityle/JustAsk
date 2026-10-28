"""Domain-agnostic BM25 index used for hybrid retrieval.

No subject-specific synonyms or rules: tokenization and scoring are generic and
work for any course language/corpus that uses Latin or Cyrillic scripts.
"""

import math
import re
from collections import Counter
from functools import lru_cache
from typing import Dict, List, Sequence, Tuple

try:
    import pymorphy3

    _MORPH = pymorphy3.MorphAnalyzer()
except Exception:  # pragma: no cover - fallback for minimal installs
    _MORPH = None

TOKEN_RE = re.compile(
    r"[A-Za-zА-Яа-яЁё0-9]+(?:[.\-_/][A-Za-zА-Яа-яЁё0-9]+)*"
)
CYRILLIC_WORD_RE = re.compile(r"[а-яё]+")
ABBREVIATION_RE = re.compile(r"\b(?:[А-ЯA-Z]{2,}|\d+[А-ЯA-Z]{1,4})\b")

# Generic function words and instruction verbs. They are language-level, not
# subject-specific, and are removed from both documents and queries so that a
# phrase like "сформулируй закон Фарадея" is not matched only by "сформулируй".
STOPWORDS = frozenset({
    "а", "без", "более", "бы", "быть", "в", "вам", "вас", "весь", "во", "вот",
    "все", "всё", "вы", "где", "да", "даже", "для", "до", "его", "ее", "её",
    "если", "есть", "еще", "ещё", "же", "за", "здесь", "и", "из", "или", "им",
    "их", "к", "как", "какой", "когда", "ко", "кого", "кому", "который", "кто",
    "ли", "либо", "лишь", "между", "менее", "мне", "можно", "мой", "мы", "на",
    "над", "надо", "нас", "наш", "не", "него", "нее", "неё", "нельзя", "нет",
    "ни", "них", "но", "ну", "нужно", "о", "об", "однако", "около", "он", "она",
    "они", "оно", "от", "перед", "по", "под", "после", "потому", "поэтому", "при",
    "правильно", "правильный", "про", "с", "себе", "себя", "сейчас", "со", "свой", "так", "также", "такой",
    "там", "те", "тем", "то", "того", "тоже", "той", "только", "том", "ты", "у",
    "уже", "хотя", "чего", "чей", "чем", "через", "что", "чтобы", "чье", "чья",
    "эта", "эти", "это", "этого", "этой", "этом", "этот", "я",
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are",
    "was", "were", "be", "by", "with", "as", "at", "from", "this", "that",
    "these", "those", "it", "its", "can", "do", "does", "how", "what", "why",
    "when", "where", "which", "who", "please",
})

TASK_VERBS = frozenset({
    "выбрать", "вывести", "выделить", "вычислить", "дать", "забыть", "записать",
    "назвать", "найти", "написать", "объяснить", "описать", "определить",
    "ответить", "охарактеризовать", "перечислить", "показать", "пояснить",
    "привести", "приготовить", "проанализировать", "раскрыть", "рассчитать",
    "рассказать", "решить", "составить", "сравнить", "сформулировать", "указать",
    "calculate", "compare", "define", "describe", "explain", "find", "give",
    "list", "show", "write",
})

WEAK_WORDS = STOPWORDS | TASK_VERBS


@lru_cache(maxsize=100_000)
def _lemma(word: str) -> str:
    if _MORPH is None:
        return word
    return _MORPH.parse(word)[0].normal_form


def _normalize_token(token: str) -> str:
    token = token.lower()
    if _MORPH is not None and CYRILLIC_WORD_RE.fullmatch(token):
        return _lemma(token)
    return token


def tokenize(text: str) -> List[str]:
    if not text:
        return []
    tokens = []
    for raw_token in TOKEN_RE.findall(text):
        token = _normalize_token(raw_token)
        if token in WEAK_WORDS:
            continue
        tokens.append(token)
    return tokens


def has_abbreviation(text: str) -> bool:
    return bool(ABBREVIATION_RE.search(text or ""))


class BM25Index:
    """Okapi BM25 over a list of documents.

    The index keeps document metadata alongside texts so the caller can map
    ranked positions back to source chunks.
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.documents: List[str] = []
        self.metadatas: List[Dict] = []
        self.doc_freqs: List[Counter] = []
        self.doc_len: List[int] = []
        self.idf: Dict[str, float] = {}
        self.avgdl = 0.0

    def build(self, documents: Sequence[str], metadatas: Sequence[Dict]) -> None:
        self.documents = list(documents)
        self.metadatas = list(metadatas)
        self.doc_freqs = [Counter(tokenize(doc)) for doc in self.documents]
        self.doc_len = [sum(freq.values()) for freq in self.doc_freqs]

        total_docs = len(self.documents)
        self.avgdl = sum(self.doc_len) / total_docs if total_docs else 0.0

        doc_frequency: Counter = Counter()
        for freqs in self.doc_freqs:
            doc_frequency.update(freqs.keys())

        # BM25+ style IDF, always positive and stable for small corpora.
        self.idf = {
            term: math.log(1.0 + (total_docs - freq + 0.5) / (freq + 0.5))
            for term, freq in doc_frequency.items()
        }

    def search(
        self,
        query: str,
        top_n: int = 20,
        min_matched_terms: int = 1,
    ) -> List[Tuple[int, float]]:
        """Return (document_index, score) pairs sorted by BM25 score."""
        if not self.documents:
            return []

        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        query_freq = Counter(query_tokens)
        avgdl = self.avgdl or 1.0
        scored: List[Tuple[int, float]] = []

        for idx, freqs in enumerate(self.doc_freqs):
            doc_len = self.doc_len[idx] or 1
            score = 0.0
            matched_terms = 0
            for term, q_tf in query_freq.items():
                tf = freqs.get(term, 0)
                if not tf:
                    continue
                matched_terms += 1
                idf = self.idf.get(term, 0.0)
                denominator = tf + self.k1 * (1.0 - self.b + self.b * doc_len / avgdl)
                score += q_tf * idf * (tf * (self.k1 + 1.0)) / denominator
            if score > 0 and matched_terms >= min_matched_terms:
                scored.append((idx, score))

        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:top_n]
