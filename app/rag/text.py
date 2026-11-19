"""Russian tokenization for BM25: normalization, stop words and stemming."""

import re

import snowballstemmer

WORD_RE = re.compile(r"\w+")
STRESS_MARK = "́"

# Own list: prepositions, conjunctions, particles, pronouns, auxiliary verbs
# and question words that carry no topic in a user question.
STOPWORDS = frozenset(
    """
    а без более бы был была были было быть в вам вас ведь весь во вот все всего
    всех вы где да даже для до его ее ей ему если есть еще же за зачем и из или
    им их к как какая какие каким какими каких какой какое какую когда кто ли
    либо лишь мне мной мы на над надо не него нее нет ни них но ну о об однако
    он она они оно от очень по под при про с сам свой себя со так также такой
    там те тем то того тоже той только том ты у уже хотя чего чей чем что
    чтобы чье эта эти это этого этой этом этот я почему сколько откуда куда
    можно ли нужно нужен нужна нужны
    """.split()
)


def normalize(text: str) -> str:
    """Lowercase text, replace ё with е and drop stress marks.

    Args:
        text: Arbitrary text.

    Returns:
        Normalized text suitable for word extraction.
    """
    return text.lower().replace("ё", "е").replace(STRESS_MARK, "")


def tokenize(
    text: str, *, stem: bool = True, remove_stopwords: bool = True
) -> list[str]:
    """Split text into BM25 tokens.

    Args:
        text: Question or fragment text.
        stem: Apply the Russian Snowball stemmer to each word.
        remove_stopwords: Drop words from ``STOPWORDS`` before stemming.

    Returns:
        Tokens in text order; repeated words are kept.
    """
    words = WORD_RE.findall(normalize(text))
    if remove_stopwords:
        words = [word for word in words if word not in STOPWORDS]
    if stem:
        words = snowballstemmer.stemmer("russian").stemWords(words)
    return words
