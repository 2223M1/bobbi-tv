"""Permission levels are ceilings; approval policy never raises the ceiling."""
from ..data_paths import data_path
import copy
import json
from pathlib import Path

from ..storage import read_json, write_json


class Permissions:
    def __init__(self, level='settings', strategy='request'):
        if level not in ('media', 'settings', 'full') or strategy not in ('request', 'auto_review', 'full_access'):
            raise ValueError('权限或审批策略无效。')
        self.level, self.strategy = level, strategy

    @property
    def native(self):
        return self.level == 'full'

    @property
    def approval(self):
        return 'never' if self.strategy == 'full_access' else 'on-request'

    @property
    def reviewer(self):
        return 'auto_review' if self.strategy == 'auto_review' else 'user'

    @property
    def sandbox(self):
        if not self.native:
            return 'read-only'
        return 'danger-full-access' if self.strategy == 'full_access' else 'workspace-write'

    def allows(self, name):
        if name in ('system_action', 'upload_logs'):
            return self.native
        if name in ('set_setting', 'set_assistant_setting', 'library_maintenance'):
            return self.level in ('settings', 'full')
        return True

    def needs_confirmation(self, name):
        return self.strategy == 'request' and name in ('set_setting', 'set_assistant_setting', 'system_action', 'upload_logs')


def restricted_catalog(root, profile, selected_model='', standard_api=False):
    """Remove native filesystem/command surfaces from Codex's model catalog.

    Disabling shell_tool alone leaves apply_patch enabled in this Codex version.
    Supply a local model catalog with shell_type disabled, no apply_patch and
    direct tool mode, together with a read-only sandbox and closed MCP/apps.
    The runtime still dispatches all Kodi actions through the level-checked host.
    """
    source = read_json(data_path(Path(profile), 'codex-home/models_cache.json'), {})
    models = source.get('models') if isinstance(source, dict) else None
    if not models:
        source = read_json(Path(root) / 'resources/config/restricted-model-template.json', {})
        models = source.get('models')
    if not models or not all(isinstance(m, dict) and isinstance(m.get('slug'), str) for m in models):
        raise ValueError('缺少受限 Codex 模型配置，请更新完整插件包。')
    models = copy.deepcopy(models)
    if selected_model and not any(m['slug'] == selected_model for m in models):
        additional = copy.deepcopy(models[0])
        additional['slug'] = additional['display_name'] = selected_model
        additional['visibility'] = 'list'
        models.append(additional)
    for model in models:
        model.update(shell_type='disabled', apply_patch_tool_type=None, tool_mode='direct',
                     experimental_supported_tools=[], supports_search_tool=False,
                     node_repl_disabled=True,
                     include_skills_usage_instructions=False, include_plugin_usage_instructions=False,
                     include_apps_usage_instructions=False)
        if standard_api:
            # ChatGPT metadata can opt into OpenAI's Responses Lite format,
            # which moves definitions from tools into additional_tools input
            # items. Responses-compatible APIs need ordinary function tools.
            model['use_responses_lite'] = False
    path = data_path(Path(profile), 'codex-restricted-models.json')
    write_json(path, {'models': models})
    return str(path.resolve())
