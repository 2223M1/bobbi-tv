"""Construct the selected agent independently of recording and configuration."""
from ..agent_tools import KodiTools
from .permissions import Permissions


def create_tools(profile, values, rpc, builtin=lambda value: None,
                 confirm=lambda title, message: False, sessions=None, assistant_get=None, assistant_set=None,
                 defer_ui=False, ui_context=None):
    backend = values.get('agent_backend')
    strategy = values.get('codebuddy_approval_strategy', 'request') if backend == 'codebuddy' else values['approval_strategy']
    permissions = Permissions(values['permission_level'], strategy)
    return KodiTools(rpc, builtin,
        confirm if strategy == 'request' else lambda *args: True,
        media=getattr(sessions, 'media', ()) if sessions else (), permissions=permissions,
        assistant_get=assistant_get, assistant_set=assistant_set, defer_ui=defer_ui, ui_context=ui_context, profile=profile)


def create_agent(root, profile, values, rpc, builtin=lambda value: None,
                 confirm=lambda title, message: False, sessions=None, assistant_get=None, assistant_set=None,
                 defer_ui=False, request_user_input=None, ui_context=None, tools=None):
    backend = values.get('agent_backend')
    if backend not in ('codex', 'codebuddy'):
        raise ValueError('智能体已关闭。')
    tools = tools if tools is not None else create_tools(profile, values, rpc, builtin, confirm, sessions,
        assistant_get, assistant_set, defer_ui, ui_context)
    permissions = tools.permissions
    if backend == 'codebuddy':
        from ..codebuddy_agent import CodeBuddyAgent
        from ..codebuddy_protocol import configured_proxy as buddy_proxy
        from ..codebuddy_regions import selected_model
        from ..codebuddy_resident import connection_factory as buddy_connection
        return CodeBuddyAgent(root, profile, tools, selected_model(values), values['agent_timeout'],
            proxy=buddy_proxy(values), permissions=permissions, sessions=sessions,
            confirm=confirm, request_user_input=request_user_input,
            connection_factory=buddy_connection(root, profile),
            region=values.get('codebuddy_region', 'external')), tools
    from ..codex_agent import CodexAgent
    from ..configuration.credentials import load_key
    from .resident import connection_factory
    from ..proxy import configured_proxy
    subscription = values['codex_provider'] == 'chatgpt'
    key = '' if subscription else load_key(profile, values['agent_key_file'])
    agent = CodexAgent(root, profile, key, tools, values['agent_base_url'],
        values['codex_chatgpt_model'] if subscription else values['agent_model'],
        values['agent_timeout'], provider='chatgpt' if subscription else 'deepseek',
        proxy=configured_proxy(values), permissions=permissions,
        effort=values['codex_chatgpt_effort'] if subscription else values['agent_effort'],
        api_code_mode=values.get('agent_code_mode', 'off') == 'on',
        sessions=sessions, structured=True, confirm=confirm, request_user_input=request_user_input,
        connection_factory=connection_factory(root, profile))
    return agent, tools
