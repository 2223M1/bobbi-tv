"""Real CookieJar directory rotation; synthetic HTTPS only, no live accounts."""
from copy import deepcopy
from email.message import Message
from functools import partial
import io
import json
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from urllib.request import HTTPSHandler, HTTPCookieProcessor, ProxyHandler, build_opener
from urllib.response import addinfourl

import pytest

from bobbi_platform.pan_accounts import PanAccounts, PanError
from bobbi_platform.pan_baidu import Client
from bobbi_platform.pan_http import NoRedirect, Session, credentials
from bobbi_platform.pan_service import PanService
from test_ce2096_pan_accounts import saved as web_saved


LIST_URL = 'https://pan.baidu.com/api/list'
OLD_BDUSS = 'synthetic-old-' + 'a' * 128
NEW_BDUSS = 'synthetic-rotated-' + 'b' * 128


def saved(subject='123', bduss=OLD_BDUSS):
    return dict(provider='baidu', subject=subject, cookies=[
        dict(name='BDUSS', value=bduss, domain='.baidu.com', path='/')])


def auxiliary(**changes):
    return dict(dict(name='DIRECTORY_HINT', value='', domain='.baidu.com', path='/'), **changes)


def cookie_line(name, value, extra=''):
    return name + '=' + value + '; Domain=.baidu.com; Path=/; Secure; HttpOnly' + extra


@pytest.fixture
def directory(tmp_path):
    """Exercise PanService -> actual adapter -> actual Session/CookieJar."""
    accounts = PanAccounts(tmp_path / 'accounts.json', {'baidu': partial(credentials, 'baidu')})
    expected = accounts.install(saved(), accounts.snapshot('baidu'))
    fixture = SimpleNamespace(accounts=accounts, expected=expected, set_cookies=[],
                              calls=[], sessions=[], before_reply=lambda: None)

    class MemoryHTTPS(HTTPSHandler):
        def https_open(self, request):
            parsed = urlsplit(request.full_url)
            assert parsed.scheme == 'https' and parsed.netloc == 'pan.baidu.com'
            assert parsed.path == '/api/list'
            query = parse_qs(parsed.query)
            assert query['dir'] == ['/'] and query['num'] == ['10'] and query['page'] == ['1']
            assert request.get_header('User-agent') == 'pan.baidu.com'
            fixture.calls.append(request.get_header('Cookie', ''))
            fixture.before_reply()
            headers = Message()
            for value in fixture.set_cookies:
                headers.add_header('Set-Cookie', value)
            rows = [dict(fs_id=index, isdir=1, size=0,
                         server_filename='fixture-' + str(index), path='/fixture-' + str(index))
                    for index in range(1, 11)]
            raw = json.dumps(dict(errno=0, list=rows)).encode()
            headers.add_header('Content-Length', str(len(raw)))
            reply = addinfourl(io.BytesIO(raw), headers, request.full_url, 200)
            reply.msg = 'OK'
            return reply

    def client_factory(provider, value):
        assert provider == 'baidu'
        session = Session(provider, value)
        session.opener = build_opener(ProxyHandler({}), NoRedirect(),
                                     HTTPCookieProcessor(session.jar), MemoryHTTPS())
        fixture.sessions.append(session)
        return Client(session=session)

    fixture.service = PanService(tmp_path, SimpleNamespace(snapshot=lambda:
        dict(account_id='', epoch=0, authenticated=False)), accounts=accounts,
        client_factory=client_factory)
    return fixture


def list_root(fixture):
    return fixture.service.dispatch('pan_list_files', dict(expected=fixture.expected,
        parent='/', page=1, operation_id='c' * 32))


def test_directory_empty_auxiliary_cookie_is_saved_and_restored_as_empty(directory):
    directory.set_cookies = [cookie_line('DIRECTORY_HINT', '')]
    result = list_root(directory)
    assert len(result['items']) == 10 and result['has_more'] is True
    assert len(directory.calls) == 1 and 'BDUSS=' + OLD_BDUSS in directory.calls[0]
    assert directory.accounts.snapshot('baidu') == directory.expected
    value = directory.accounts.credentials(directory.expected)
    assert auxiliary() in value['cookies']
    # Persist an actual empty value, not a deleted cookie or invented token.
    restarted = PanAccounts(directory.accounts.path, directory.accounts.validators)
    restored = Session('baidu', restarted.credentials(directory.expected))
    assert 'DIRECTORY_HINT=' in restored.cookie_header(LIST_URL).split('; ')
    assert 'BDUSS=' + OLD_BDUSS in restored.cookie_header(LIST_URL)
    assert not restored.cookie_header('https://example.test/')
    public = json.dumps(dict(result=result, status=directory.service.status()))
    assert OLD_BDUSS not in public and 'DIRECTORY_HINT' not in public


def test_valid_bduss_rotation_and_auxiliary_empty_cookie_share_account_cas(directory):
    directory.set_cookies = [cookie_line('BDUSS', NEW_BDUSS), cookie_line('DIRECTORY_HINT', '')]
    result = list_root(directory)
    assert len(result['items']) == 10
    assert directory.accounts.snapshot('baidu') == directory.expected
    restarted = PanAccounts(directory.accounts.path, directory.accounts.validators)
    restored = Session('baidu', restarted.credentials(directory.expected))
    header = restored.cookie_header(LIST_URL)
    assert 'BDUSS=' + NEW_BDUSS in header and OLD_BDUSS not in header
    assert 'DIRECTORY_HINT=' in header.split('; ')


@pytest.mark.parametrize('value,extra', [('', ''), ('short', ''), ('', '; Max-Age=0')],
                         ids=['empty', 'short', 'deleted'])
def test_invalid_or_deleted_bduss_rejects_directory_without_restoring_old_jar(directory, value, extra):
    before = directory.accounts.path.read_bytes()
    directory.set_cookies = [cookie_line('BDUSS', value, extra), cookie_line('DIRECTORY_HINT', '')]
    with pytest.raises(PanError, match='^PAN_CREDENTIALS_INVALID$'):
        list_root(directory)
    session = directory.sessions[0]
    assert OLD_BDUSS not in session.cookie_header(LIST_URL)
    with pytest.raises(PanError, match='^PAN_CREDENTIALS_INVALID$'):
        session.export(subject='123')
    # No invalid rotation is committed, no directory is published, and no
    # old credential is reinserted into the response's live CookieJar.
    assert directory.accounts.path.read_bytes() == before
    assert not directory.service.directory_cache
    assert len(directory.calls) == 1


@pytest.mark.parametrize('transition', ['switch', 'relogin', 'logout'])
def test_late_cookie_rotation_never_overwrites_a_new_account_generation(directory, transition):
    directory.set_cookies = [cookie_line('BDUSS', NEW_BDUSS), cookie_line('DIRECTORY_HINT', '')]
    winning = {}

    def replace_account():
        if transition == 'logout':
            winning['scope'] = directory.accounts.logout(directory.expected)
        else:
            winning['scope'] = directory.accounts.install(
                saved(subject='456' if transition == 'switch' else '123', bduss='winner-' + 'w' * 128),
                directory.expected)
        winning['disk'] = directory.accounts.path.read_bytes()

    directory.before_reply = replace_account
    with pytest.raises(PanError, match='^PAN_ACCOUNT_CHANGED$'):
        list_root(directory)
    assert directory.accounts.snapshot('baidu') == winning['scope']
    assert directory.accounts.path.read_bytes() == winning['disk']
    assert NEW_BDUSS.encode() not in winning['disk']
    assert not directory.service.directory_cache
    assert len(directory.calls) == 1


@pytest.mark.parametrize('change', [dict(domain='.example.test'), dict(domain='.other.baidu.com'),
    dict(path='relative'), dict(path='/\n'), dict(name='bad name'), dict(value=None),
    dict(value=' '), dict(value='\n'), dict(value='中文'), dict(value='x' * 4097)])
def test_empty_auxiliary_exception_does_not_relax_cookie_schema(change):
    value = saved()
    value['cookies'].append(auxiliary(**change))
    with pytest.raises(PanError, match='^PAN_CREDENTIALS_INVALID$'):
        credentials('baidu', value)


@pytest.mark.parametrize('provider', ['quark', 'uc'])
def test_empty_auxiliary_exception_is_not_applied_to_other_providers(provider):
    value = deepcopy(web_saved(provider))
    value['cookies'].append(dict(name='DIRECTORY_HINT', value='',
                                 domain='.' + ('quark.cn' if provider == 'quark' else 'uc.cn'), path='/'))
    with pytest.raises(PanError, match='^PAN_CREDENTIALS_INVALID$'):
        credentials(provider, value)
