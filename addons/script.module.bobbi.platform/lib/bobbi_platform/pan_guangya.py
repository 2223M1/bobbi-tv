"""Guangya read-only personal files; exact selection recheck before resolution."""
from .pan_accounts import PanError
from .pan_device import RenewableClient
from .pan_http import USER_AGENT
from .pan_tokens import identifier, listing, number, original_url, page_number, text

API = 'https://api.guangyapan.com'


def entry(row):
    if type(row) is not dict or type(row.get('resType')) is not int or row['resType'] not in (1, 2):
        raise PanError('PAN_REPLY_INVALID')
    return dict(file_id=identifier(row.get('fileId')), name=text(row.get('fileName')),
        size=number(row.get('fileSize')), directory=row['resType'] == 2,
        modified=number(row.get('utime')))


class Client(RenewableClient):
    def __init__(self, value, **kwargs):
        super().__init__('guangya', value, **kwargs)

    def _call(self, path, body):
        value = self.session.request(API + path, body=body, headers={
            'Authorization': 'Bearer ' + self.saved['access_token'],
            'Did': self.saved['device_id'], 'Dt': '4'})
        if type(value.get('code')) is not int or value['code'] != 0:
            raise PanError('PAN_API_REJECTED')
        if type(value.get('data')) is not dict:
            raise PanError('PAN_REPLY_INVALID')
        return value['data']

    def list_files(self, parent='0', page=1, size=10):
        page_number(page, size)
        value = self._call('/userres/v1/file/get_file_list', dict(
            parentId='' if parent == '0' else identifier(parent), page=page-1,
            pageSize=size, orderBy=3, sortType=1))
        result = listing(value.get('list'), value.get('total'), page, size, entry)
        for item in result['items']:
            if not item['directory']:
                item['listing'] = dict(parent=parent, page=page, size=size)
        return result

    def resolve_original(self, selected):
        if (type(selected) is not dict or set(selected) !=
                {'file_id', 'name', 'size', 'directory', 'modified', 'listing'}
                or selected['directory'] is not False):
            raise PanError('PAN_SELECTION_INVALID')
        fid = identifier(selected['file_id'])
        number(selected['size'], 1)
        location = selected['listing']
        if type(location) is not dict or set(location) != {'parent', 'page', 'size'}:
            raise PanError('PAN_SELECTION_INVALID')
        rows = self.list_files(**location)['items']
        matches = [row for row in rows if row['file_id'] == fid]
        if len(matches) != 1 or matches[0] != selected:
            raise PanError('PAN_FILE_CHANGED')
        value = self._call('/nd.bizuserres.s/v1/get_res_download_url', {'fileId': fid})
        url = original_url(value.get('signedURL') or value.get('downloadUrl'), ('guangyapan.com', 'aliyuncs.com'))
        return dict(url=url, size=selected['size'], original=True, headers={'User-Agent': USER_AGENT})
