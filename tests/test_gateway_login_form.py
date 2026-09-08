from html.parser import HTMLParser
from importlib import resources


class Forms(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms = []

    def handle_starttag(self, tag, attrs):
        if tag == 'form':
            self.forms.append(dict(attrs))


def test_login_form_posts_even_without_javascript():
    parser = Forms()
    parser.feed(resources.files('chatshare.assets.gateway').joinpath('login.html').read_text())
    assert len(parser.forms) == 1
    assert parser.forms[0].get('method', '').lower() == 'post'
    assert parser.forms[0].get('action') == '/_chatshare/login'
