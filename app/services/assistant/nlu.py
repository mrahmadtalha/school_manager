"""Matching a question to an intent: the keyword vocabulary, fuzzy matching and scoring."""

import difflib
import re
import unicodedata

from app.services import assistant_intents as catalogue


def normalize(text):
    text = unicodedata.normalize('NFKC', text or '').lower()
    text = text.replace("'", '').replace('\u2019', '')
    text = re.sub(r'[^\w\s]', ' ', text, flags=re.UNICODE)
    return re.sub(r'\s+', ' ', text).strip()


_VOCAB = None


_FUZZY_KEYS = None


_HOW_FUZZY = None


def _vocab():
    """{keyword: {intent_id: weight}} built once from the catalogue."""
    global _VOCAB, _FUZZY_KEYS, _HOW_FUZZY
    if _VOCAB is None:
        vocab = {}
        for intent in catalogue.INTENTS:
            for word, weight in intent['keywords'].items():
                vocab.setdefault(word, {})[intent['id']] = weight
        _VOCAB = vocab
        _FUZZY_KEYS = [key for key in vocab if len(key) >= 5 and key.isascii()]
        _HOW_FUZZY = [key for key in catalogue.HOW_MARKERS
                      if len(key) >= 5 and key.isascii()]
    return _VOCAB


def _match_key(token):
    """Exact keyword, else the closest keyword for a misspelt word, else None."""
    vocab = _vocab()
    if token in vocab:
        return token
    if len(token) >= 5 and token.isascii():
        close = difflib.get_close_matches(token, _FUZZY_KEYS, n=1, cutoff=0.84)
        if close:
            return close[0]
    return None


def _has_how_marker(tokens, norm):
    _vocab()
    for token in tokens:
        if token in catalogue.HOW_MARKERS:
            return True
        if len(token) >= 5 and token.isascii() and difflib.get_close_matches(
                token, _HOW_FUZZY, n=1, cutoff=0.86):
            return True
    return 'how to' in norm


def score_intents(tokens, norm, has_how):
    """Return ``{intent_id: score}`` for every intent with a non-zero score."""
    vocab = _vocab()
    scores = {}
    seen = set()
    for token in tokens:
        key = _match_key(token)
        if key is None or key in seen:
            continue
        seen.add(key)
        for intent_id, weight in vocab[key].items():
            scores[intent_id] = scores.get(intent_id, 0) + weight

    padded = ' %s ' % norm
    for intent in catalogue.INTENTS:
        for phrase, weight in intent.get('phrases', {}).items():
            if ' %s ' % phrase in padded:
                scores[intent['id']] = scores.get(intent['id'], 0) + weight

    # "How do I ...?" guides need a how-marker; data answers step back when one
    # is present and a guide matches.
    guide_ok = False
    for intent in catalogue.INTENTS:
        if not intent.get('howto'):
            continue
        if not has_how:
            scores.pop(intent['id'], None)
        elif scores.get(intent['id'], 0) >= intent['min_score']:
            guide_ok = True
    if guide_ok:
        for intent in catalogue.INTENTS:
            if not intent.get('howto') and intent['id'] in scores:
                scores[intent['id']] *= 0.4
    return scores
