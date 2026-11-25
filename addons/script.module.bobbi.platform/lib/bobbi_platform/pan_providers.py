"""Static adapter wiring; this is not a second provider/plugin framework."""
from dataclasses import dataclass
from functools import partial
from types import MappingProxyType

from .pan_accounts import PanError
from .pan_http import credentials
from .pan_quark_uc import Client, QuarkLogin, UCLogin
from .pan_baidu import Client as BaiduClient, Login as BaiduLogin
from .pan_aliyun import Client as AliyunClient, Login as AliyunLogin, credentials as aliyun_credentials
from .pan_123 import Client as Cloud123Client, Login as Cloud123Login, credentials as cloud123_credentials
from .pan_device import Login as DeviceLogin, credentials as device_credentials
from .pan_guangya import Client as GuangyaClient
from .pan_xunlei import Client as XunleiClient
from .pan_mobile import Client as MobileClient, Login as MobileLogin, credentials as mobile_credentials
from .pan_tianyi import Client as TianyiClient, Login as TianyiLogin
from .pan_115 import Client as Cloud115Client
from .server_plex import Client as PlexClient
from .server_emby import Client as EmbyClient


@dataclass(frozen=True)
class Provider:
    client: object
    login: object
    validator: object
    root: str = '0'
    pagination: str = 'page'
    parent_field: str = 'file_id'
    cookie_rotation: bool = False
    capabilities: tuple = ('qr_login', 'list_files', 'personal_play')
    verification: str = 'not_device_verified'
    proof_contract: str = 'page_total'

    def public(self):
        return dict(root=self.root, pagination=self.pagination, parent_field=self.parent_field,
                    capabilities=list(self.capabilities), verification=self.verification)


DESCRIPTORS = MappingProxyType({
    'plex': Provider(PlexClient, None, None, root='root',
        capabilities=('list_files', 'personal_play'), verification='media_server_experimental',
        proof_contract='page_optional_total'),
    'jellyfin': Provider(partial(EmbyClient, 'jellyfin'), None, None, root='root',
        capabilities=('list_files', 'personal_play'), verification='media_server_experimental',
        proof_contract='page_total'),
    'emby': Provider(partial(EmbyClient, 'emby'), None, None, root='root',
        capabilities=('list_files', 'personal_play'), verification='media_server_experimental',
        proof_contract='page_total'),
    '115': Provider(Cloud115Client, None, None,
        capabilities=('qr_login', 'share_play', 'list_files', 'personal_play'),
        verification='native_index_experimental', proof_contract='page_total'),
    'quark': Provider(partial(Client, 'quark'), QuarkLogin, partial(credentials, 'quark'),
        cookie_rotation=True, proof_contract='page_total'),
    'uc': Provider(partial(Client, 'uc'), UCLogin, partial(credentials, 'uc'),
        cookie_rotation=True, proof_contract='page_total'),
    'baidu': Provider(BaiduClient, BaiduLogin, partial(credentials, 'baidu'),
        root='/', parent_field='path', cookie_rotation=True, proof_contract='page_probe'),
    'aliyun': Provider(AliyunClient, AliyunLogin, aliyun_credentials,
        pagination='cursor', proof_contract='cursor'),
    '123': Provider(Cloud123Client, Cloud123Login, cloud123_credentials,
        proof_contract='page_optional_total'),
    '189': Provider(TianyiClient, TianyiLogin, partial(credentials, '189'),
        cookie_rotation=True, proof_contract='page_optional_total'),
    '139': Provider(MobileClient, MobileLogin, mobile_credentials,
        pagination='cursor', proof_contract='cursor'),
    'guangya': Provider(GuangyaClient, partial(DeviceLogin, 'guangya'), partial(device_credentials, 'guangya'),
        proof_contract='page_optional_total'),
    'xunlei': Provider(XunleiClient, partial(DeviceLogin, 'xunlei'), partial(device_credentials, 'xunlei'),
        pagination='cursor', proof_contract='cursor'),
})


def descriptor(provider):
    try:
        return DESCRIPTORS[provider]
    except (KeyError, TypeError):
        raise PanError('PAN_PROVIDER_INVALID') from None
