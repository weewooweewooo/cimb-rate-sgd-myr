from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CommandResponse:
    accepted: bool
    message: str


def handle_phone_command(_command_text: str) -> CommandResponse:
    return CommandResponse(
        accepted=False,
        message="Phone command handler is a placeholder in this MVP.",
    )


def handle_whatsapp_command(_command_text: str) -> CommandResponse:
    return CommandResponse(
        accepted=False,
        message="WhatsApp command support is not implemented yet.",
    )


def handle_telegram_command(_command_text: str) -> CommandResponse:
    return CommandResponse(
        accepted=False,
        message="Telegram command support is not implemented yet.",
    )
