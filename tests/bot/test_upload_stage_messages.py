from librar.bot.handlers.upload import _build_stage_error_message


def test_build_stage_error_message_uses_human_readable_stage() -> None:
    message = _build_stage_error_message("index_semantic", "faiss failed")
    assert message == "Ошибка на этапе «построение поиска»: faiss failed"


def test_build_stage_error_message_falls_back_for_unknown_stage() -> None:
    message = _build_stage_error_message("something_else", None)
    assert message == "Ошибка на этапе «обработка»: Неизвестная ошибка"
