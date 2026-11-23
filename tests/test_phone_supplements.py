"""Existing authenticated phone review against the actual SQLite relation transaction."""
from uuid import uuid4

from test_ce2097_phone_management import phone, pair, invoke
from test_media_library_index import index, scope, ref, insert
from test_catalog_file_projection_contract import describe


def test_phone_relation_preview_apply_query_and_undo_use_original_transaction(phone, index):
    main, extra = ref(1), ref(2)
    insert(index, [main, extra]);describe(index, main, '导演剪辑')
    def rpc(action, body, **kwargs):
        if action=='pan_status':
            return dict(providers=[dict(provider='quark',account=scope())])
        assert body['expected']==scope()
        return getattr(index,action.removeprefix('catalog_'))(scope(),**{k:v for k,v in body.items() if k!='expected'})
    phone.manager.rpc=rpc;pair(phone)
    parent=invoke(phone,'catalog_item',dict(file_id=main['id']))
    assert parent['file']['observation_key']
    cmd=dict(file_id=extra['id'],expected_revision=0,action='supplement',mapping=dict(
        metadata_key='tmdb:movie:10',parent_file_id=main['id'],parent_revision=parent['revision'],
        parent_evidence=parent['file']['observation_key'],kind='interview',title='制作访谈'))
    preview=invoke(phone,'catalog_preview',dict(commands=[cmd]))
    assert preview['items'][0]['after_supplement']['title']=='制作访谈'
    receipt=invoke(phone,'catalog_apply',dict(commands=[cmd],request_id=uuid4().hex))
    assert receipt['items'][0]['status']=='applied'
    query=dict(view='supplements',parent_entity_id=main['id'])
    found=invoke(phone,'catalog_query',dict(query=query))['items'][0]
    assert found['supplement']['state']=='confirmed' and found['entity_id']==extra['id']
    assert 'file_ref' not in found and 'locator' not in repr(found)
    cmd=dict(file_id=extra['id'],expected_revision=1,action='undo',mapping=None)
    invoke(phone,'catalog_preview',dict(commands=[cmd]))
    assert invoke(phone,'catalog_apply',dict(commands=[cmd],request_id=uuid4().hex))['items'][0]['status']=='applied'
    assert invoke(phone,'catalog_query',dict(query=query))['items']==[]
