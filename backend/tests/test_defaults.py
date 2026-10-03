from app.adapters.caldav_ops import _default_selected


def test_skips_birthday_calendars():
    assert _default_selected("Дни рождения") is False
    assert _default_selected("Holidays in Russia") is False
    assert _default_selected("Работа") is True
    assert _default_selected("Пары") is True
