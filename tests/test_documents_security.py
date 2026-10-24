import pytest

from tests.helpers import assert_problem, generate
from tests.security_support import ESCAPES

pytestmark = pytest.mark.timeout(60)

API_PAYLOADS = {
    "dunder-class": ESCAPES["dunder-class"],
    "lipsum-globals": ESCAPES["lipsum-globals"],
    "open-builtin": ESCAPES["open-builtin"],
    "include-absolute": '{% include "/etc/passwd" %}',
    "range-bomb": "{% for i in range(100000000) %}x{% endfor %}",
    "infinite-recursion": "{% macro m() %}{{ m() }}{% endmacro %}{{ m() }}",
    "division-by-zero": "{{ 1 / 0 }}",
}


@pytest.mark.parametrize("payload", API_PAYLOADS.values(), ids=API_PAYLOADS.keys())
def test_hostile_template_returns_template_error(api, acme, make_template, payload):
    make_template(acme.tenant, "hostile", html=f"<p>{payload}</p>", schema={"type": "object"})
    resp = generate(api, acme.key.raw, slug="hostile", data={"customer": {"name": "x"}})
    assert_problem(resp, 422, "template_error")
    assert "Traceback" not in resp.text
    assert "site-packages" not in resp.text
    assert "root:" not in resp.text


def test_stored_template_cannot_make_the_server_connect_out(api, acme, make_template, canary):
    html = f'<img src="http://{canary.host}/x.png">' f'<link rel="stylesheet" href="http://{canary.host}/x.css"><p>hi</p>'
    make_template(acme.tenant, "ssrf", html=html, schema={"type": "object"})
    resp = generate(api, acme.key.raw, slug="ssrf", data={})
    if resp.status_code != 200:
        assert_problem(resp, 422, "template_error")
    assert canary.connections == 0
