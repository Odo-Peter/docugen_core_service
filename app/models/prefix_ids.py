from sqlalchemy import String
from sqlalchemy.orm import MappedColumn, mapped_column
from ulid import ULID

def prefixed_id_column(prefix: str) -> MappedColumn[str]:
    """Primary key holding `<prefix><ULID>`, generated in the application."""
    return mapped_column(
        String(50),
        primary_key=True,
        default=lambda: f"{prefix}{ULID()}",
    )