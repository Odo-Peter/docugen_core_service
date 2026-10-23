"""Dev seed: tenant + API key + an 'invoice' template. Prints the key once.

uv run python -m scripts.seed_dev
"""

import hashlib
import secrets

from sqlalchemy import select

from app.core.scopes import ApiKeyScope
from app.db import SessionLocal

from app.models.api_key import ApiKey
from app.models.template import Template
from app.models.template_version import TemplateVersion
from app.models.tenant import Tenant

TENANT_NAME = "Dev Tenant"

HTML = """<html><body>
<h1>Invoice for {{ customer.name }}</h1>
<table>
  <tr><th>Item</th><th>Qty</th><th>Price</th><th>Total</th></tr>
  {% for line in lines %}
  <tr><td>{{ line.desc }}</td><td>{{ line.qty }}</td><td>{{ line.price }}</td>
      <td>{{ line.qty * line.price }}</td></tr>
  {% endfor %}
</table>
</body></html>"""

CSS = "@page { size: A4; margin: 20mm } body { font-family: 'DejaVu Sans'; } td, th { padding: 4px 12px; }"

SCHEMA = {
    "type": "object",
    "required": ["customer", "lines"],
    "properties": {
        "customer": {
            "type": "object",
            "required": ["name"],
            "properties": {"name": {"type": "string"}},
        },
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["desc", "qty", "price"],
                "properties": {
                    "desc": {"type": "string"},
                    "qty": {"type": "number"},
                    "price": {"type": "number"},
                },
            },
        },
    },
}


def main() -> None:
    with SessionLocal() as db:
        tenant = db.scalars(select(Tenant).where(Tenant.name == TENANT_NAME, Tenant.is_active.is_(True))).first()
        if tenant is None:
            tenant = Tenant(name=TENANT_NAME)
            db.add(tenant)
            db.flush()

        # Full key = dg_<prefix>_<secret>; hex has no underscores, so the
        # parser's split("_") is safe. Hash the WHOLE string.
        prefix, secret = secrets.token_hex(4), secrets.token_hex(24)
        raw_key = f"dg_{prefix}_{secret}"
        db.add(
            ApiKey(
                tenant_id=tenant.id,
                name="dev key",
                key_prefix=prefix,
                key_hash=hashlib.sha256(raw_key.encode()).hexdigest(),
                scopes=[ApiKeyScope.DOCUMENTS_CREATE, ApiKeyScope.TEMPLATES_READ],
            )
        )

        template = db.scalars(
            select(Template).where(
                Template.tenant_id == tenant.id,
                Template.slug == "invoice",
                Template.is_active.is_(True),
            )
        ).first()
        if template is None:
            template = Template(tenant_id=tenant.id, slug="invoice", name="Invoice")
            db.add(template)
            db.flush()
            db.add(TemplateVersion(template_id=template.id, version=1, html=HTML, css=CSS, variables_schema=SCHEMA))

        db.commit()
        print(f"tenant_id: {tenant.id}")
        print(f"api key:   {raw_key}   <- shown once, not recoverable")


if __name__ == "__main__":
    main()
