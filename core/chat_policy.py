"""Private-chat and /start language rules."""

SUPPORTED_LANGS = {"en", "ru", "de", "fr", "es"}


def is_private_chat(chat_type) -> bool:
    value = getattr(chat_type, "value", chat_type)
    return str(value or "") == "private"


def language_for_start(saved_lang: str, payload: str) -> tuple[str, bool]:
    """Keep a saved language. A subscribe_<lang> deep link may change it.

    Returns (language, should_persist).
    """
    saved = saved_lang if saved_lang in SUPPORTED_LANGS else "en"
    normalized = str(payload or "").strip().lower()
    if normalized.startswith("subscribe_"):
        requested = normalized.removeprefix("subscribe_")
        if requested in SUPPORTED_LANGS:
            return requested, True
        return saved, False
    return saved, False
