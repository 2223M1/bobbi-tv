import json
import pytest
from bobbi_platform.pairing import Pairing, save, load, from_export, engine_document


def test_per_user_secret_roundtrip_does_not_change_addon_tree(tmp_path):
    pair = Pairing('http://127.0.0.1:8090/', 'bobbi', 'a' * 32)
    path = tmp_path / 'userdata/pairing.json'
    assert load(path) is None
    save(path, pair)
    result = load(path)
    assert result.endpoint == 'http://127.0.0.1:8090'
    assert result.password == pair.password
    assert pair.password not in repr(pair)


@pytest.mark.parametrize('endpoint', ['http://example.com:8090', 'http://user:pass@127.0.0.1:8090',
    'http://127.0.0.1', 'http://127.0.0.1:8090/anything', 'http://127.0.0.1:8090/?token=x'])
def test_pairing_endpoint_cannot_forward_control_auth(endpoint):
    with pytest.raises(ValueError):
        Pairing(endpoint, 'bobbi', 'x' * 32)


def test_corrupt_storage_error_hides_content(tmp_path):
    path = tmp_path / 'pairing.json'
    path.write_text('secret-value', encoding='utf-8')
    with pytest.raises(ValueError) as error:
        load(path)
    assert 'secret-value' not in str(error.value)


def exported():
    return {'schema': 'bobbi-local-engine-v1', 'engine': 'TorrServer',
            'version': 'MatriX.147', 'url': 'http://127.0.0.1:8090',
            'username': 'bobbi_' + 'a' * 12, 'password': 'b' * 48}


def test_android_export_roundtrips_without_hand_entering_credentials(tmp_path):
    value = exported()
    pairing = from_export(json.dumps(value).encode())
    path = tmp_path / 'helper.json'
    save(path, pairing)
    assert engine_document(load(path)) == value
    assert value['password'] not in repr(pairing)


@pytest.mark.parametrize('change', [
    {'url': 'http://192.168.1.2:8090'}, {'version': 'latest'}, {'engine': 'other'},
    {'username': 'bobbi'}, {'password': 'short'}, {'extra': 'not-allowed'},
])
def test_import_rejects_unsupported_helpers_without_printing_credentials(change):
    value = dict(exported(), **change)
    with pytest.raises(ValueError) as error:
        from_export(json.dumps(value))
    assert value['password'] not in str(error.value)


def test_duplicate_or_oversized_export_is_rejected():
    for value in [json.dumps(exported())[:-1] + ',"version":"MatriX.147"}', ' ' * 4097]:
        with pytest.raises(ValueError):
            from_export(value)
