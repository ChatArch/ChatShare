from html.parser import HTMLParser
import asyncio

import httpx

from chatshare.gateway import create_app


class Forms(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms = []

    def handle_starttag(self, tag, attrs):
        if tag == 'form':
            self.forms.append(dict(attrs))


def test_login_form_posts_even_without_javascript(tmp_path):
    app = create_app(
        root=tmp_path,
        upstream="http://127.0.0.1:5000",
        public_url="https://share.example",
        transport=httpx.MockTransport(lambda request: httpx.Response(200)),
    )

    async def fetch():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="https://share.example",
        ) as client:
            return await client.get("/_chatshare/login")

    response = asyncio.run(fetch())
    parser = Forms()
    parser.feed(response.text)
    assert len(parser.forms) == 1
    assert parser.forms[0].get('method', '').lower() == 'post'
    assert parser.forms[0].get('action') == '/_chatshare/login'
    assert '/_chatshare/assets/login.js' in response.text
    assert 'data-session-url="/_chatshare/session"' in response.text
