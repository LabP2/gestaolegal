"""Data e hora: convenção do sistema.

Regra:

- **Instantes** (quando algo aconteceu: criação, saída da fila, ponto,
  execuções do DJEN, auditoria) são gravados em **UTC**, como datetime naive.
  Use `agora_utc()`. O provedor JSON do Flask escreve datetime naive como GMT,
  e o navegador converte para o fuso de quem está vendo.
- **Dias de calendário** (o "hoje" da fila, a data da notificação, a janela de
  datas do DJEN) são dias de **Brasília**. Use `hoje_brasilia()`, nunca
  `date.today()`: o servidor roda em UTC, e depois das 21h o dia já virou.
- **Horários agendados por pessoas** (data e hora de eventos e audiências, a
  janela de inscrição do plantão) ficam como foram digitados, em horário de
  Brasília, e são comparados com `agora_brasilia()`.

Para filtrar instantes por um dia de Brasília, use `intervalo_utc_do_dia()`.
"""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

FUSO_BRASILIA = ZoneInfo("America/Sao_Paulo")


def agora_utc() -> datetime:
    """Instante atual em UTC, como datetime naive (o formato das colunas)."""
    return datetime.now(UTC).replace(tzinfo=None)


def agora_utc_iso() -> str:
    """Instante atual em UTC como ISO 8601 com fuso, para gravar dentro de JSON.

    Sem o "+00:00", o navegador leria o texto como hora local.
    """
    return datetime.now(UTC).isoformat()


def agora_brasilia() -> datetime:
    """Data/hora atual em Brasília, naive. Só para comparar com horário agendado."""
    return datetime.now(FUSO_BRASILIA).replace(tzinfo=None)


def hoje_brasilia() -> date:
    return agora_brasilia().date()


def brasilia_para_utc(valor: datetime) -> datetime:
    """Horário de parede de Brasília (naive) → instante UTC (naive)."""
    return valor.replace(tzinfo=FUSO_BRASILIA).astimezone(UTC).replace(tzinfo=None)


def utc_para_brasilia(valor: datetime) -> datetime:
    """Instante UTC (naive) → horário de parede de Brasília (naive)."""
    return valor.replace(tzinfo=UTC).astimezone(FUSO_BRASILIA).replace(tzinfo=None)


def intervalo_utc_do_dia(dia: date) -> tuple[datetime, datetime]:
    """Início (inclusivo) e fim (exclusivo), em UTC, de um dia de Brasília."""
    return (
        brasilia_para_utc(datetime.combine(dia, time.min)),
        brasilia_para_utc(datetime.combine(dia + timedelta(days=1), time.min)),
    )


def dia_util_anterior(referencia: date | None = None) -> date:
    """Último dia útil antes da referência (padrão: hoje em Brasília).

    Segunda-feira volta para a sexta anterior e domingo para a sexta; nos demais
    dias é simplesmente a véspera.
    """
    referencia = referencia or hoje_brasilia()
    # date.weekday(): segunda = 0 ... domingo = 6
    dias_atras = {0: 3, 6: 2}.get(referencia.weekday(), 1)
    return referencia - timedelta(days=dias_atras)
