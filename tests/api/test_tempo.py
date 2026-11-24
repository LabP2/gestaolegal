"""Convenção de data e hora (gestaolegal/utils/tempo.py)."""

from datetime import date, datetime

from gestaolegal.utils.tempo import (
    brasilia_para_utc,
    intervalo_utc_do_dia,
    utc_para_brasilia,
)


def test_brasilia_para_utc_e_volta():
    assert brasilia_para_utc(datetime(2026, 11, 24, 15, 30)) == datetime(2026, 11, 24, 18, 30)
    assert utc_para_brasilia(datetime(2026, 11, 25, 1, 0)) == datetime(2026, 11, 24, 22, 0)


def test_horario_de_verao_antigo_e_respeitado():
    # Dezembro de 2018 tinha horário de verão (UTC-2).
    assert brasilia_para_utc(datetime(2018, 12, 3, 12, 0)) == datetime(2018, 12, 3, 14, 0)


def test_intervalo_do_dia_de_brasilia_em_utc():
    assert intervalo_utc_do_dia(date(2026, 11, 24)) == (
        datetime(2026, 11, 24, 3, 0),
        datetime(2026, 11, 25, 3, 0),
    )
