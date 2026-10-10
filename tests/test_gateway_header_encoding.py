import httpx
from starlette.responses import Response
from chatshare.gateway import _headers


def test_utf8_content_disposition_preserves_upstream_wire_bytes():
    wire = 'inline; filename="练习十二.pptx"; filename*=UTF-8\'\'%E7%BB%83%E4%B9%A0.pptx'.encode('utf-8')
    upstream = httpx.Headers([(b'content-disposition', wire), (b'content-length', b'3')])
    response = Response(b'abc', headers=_headers(upstream))
    assert dict(response.raw_headers)[b'content-disposition'] == wire


def test_latin1_header_and_hop_filtering_remain_unchanged():
    upstream = httpx.Headers([
        (b'content-disposition', b'inline; filename="caf\xe9.txt"'),
        (b'connection', b'keep-alive, x-internal'),
        (b'x-internal', b'private-hop'),
        (b'set-cookie', b'not-for-downstream'),
    ])
    response = Response(b'abc', headers=_headers(upstream, {'set-cookie'}))
    headers = dict(response.raw_headers)
    assert headers[b'content-disposition'] == b'inline; filename="caf\xe9.txt"'
    assert b'connection' not in headers
    assert b'x-internal' not in headers
    assert b'set-cookie' not in headers
