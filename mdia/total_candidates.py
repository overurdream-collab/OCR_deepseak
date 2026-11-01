"""Conservative total-line selection: ignore prose explaining totals.

An explanatory sentence may contain a numeric amount (e.g., a variance)
and must never replace an independently labelled printed grand total.
"""
import re

_CURRENCIES = {"sar", "yer", "usd", "eur", "aed", "omr", "qar", "bhd",
               "kwd", "jod", "ريال", "﷼", "ر.س", "ر.ي"}


def is_isolated_total(kv):
    """True only for one numeric token, plus at most a currency token."""
    if not kv.value_words:
        return False
    count = 0
    for word in kv.value_words:
        text = word.text.strip()
        if not text:
            continue
        if text.lower().strip(":؛;") in _CURRENCIES:
            continue
        if re.fullmatch(r"[-+]?\(?[0-9٠-٩۰-۹][0-9٠-٩۰-۹.,٫٬،]*\)?", text):
            count += 1
        else:
            return False
    return count == 1
