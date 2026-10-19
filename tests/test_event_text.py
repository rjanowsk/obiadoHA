from custom_components.obiado.event_text import format_event_text


def test_menu_visible_in_summary_and_readable_details_keep_diets():
    summary, description = format_event_text(
        "Testowy Jan",
        (
            "Danie główne 2 , dieta s - gotowany zielony groszek, zapiekanka mac and cheese",
            "Napój , dieta bez mleka - sok pomarańczowy",
        ),
    )
    assert summary == (
        "Obiad — Danie główne 2: gotowany zielony groszek, zapiekanka mac and cheese"
        " · Napój: sok pomarańczowy"
    )
    assert description == (
        "Posiłki — Testowy Jan\n\n"
        "• Danie główne 2: gotowany zielony groszek, zapiekanka mac and cheese\n"
        "  Dieta: s\n\n"
        "• Napój: sok pomarańczowy\n"
        "  Dieta: bez mleka"
    )


def test_unfamiliar_descriptions_are_preserved_without_truncation():
    meal = "Zupa z dyni, pieczywo — porcja duża " + "bardzo długi opis " * 40
    summary, description = format_event_text("Testowy Jan", (meal, "Napój"))
    normalized = " ".join(meal.split())
    assert summary == f"Obiad — {normalized} · Napój"
    assert normalized in description


def test_whitespace_and_hyphenated_diet_and_dish():
    summary, description = format_event_text(
        "Testowy Jan", ("  Zupa ,  dieta bez-mleczna - krem\n z dyni - z grzankami  ",)
    )
    assert summary == "Obiad — Zupa: krem z dyni - z grzankami"
    assert "Dieta: bez-mleczna" in description
