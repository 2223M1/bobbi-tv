"""Read original vendor identity without selecting an Android boot slot."""
from android_identity import read_vendor_models, parse_active_slot


def read_models(super_row):
    evidence = {'method': 'read-only-vendor-identity', 'slots': {}}
    models = set()
    for slot in (0, 1):
        label = '_' + 'ab'[slot]
        try:
            found = read_vendor_models(super_row, slot=slot)
        except ValueError as exc:
            # Invalid LP/ext4 geometry or an unreadable vendor is not evidence
            # of a model. Never extend its mapping or substitute the live DTB.
            evidence['slots'][label] = {'error': str(exc)}
            continue
        evidence['slots'][label] = {'models': found}
        if not found or any(model not in ('A4111', 'A4112') for model in found):
            raise ValueError('修复读取到不支持或缺失的 Android 机型：'+label)
        models.update(found)
    if len(models) != 1:
        raise ValueError('无法从 Android vendor 唯一确认 A4111/A4112（两槽不可读或机型冲突）：'+str(evidence['slots']))
    return sorted(models), evidence


def read_models_for_environment(super_row, output):
    """Resolve identity only; normal is not an alias for either boot slot."""
    if output.strip() == 'active_slot=normal':
        models, evidence = read_models(super_row)
        evidence['persisted_active_slot'] = 'normal'
        return models, evidence
    slot = parse_active_slot(output)
    models = read_vendor_models(super_row, slot=slot)
    label = '_' + 'ab'[slot]
    return models, {'method': 'read-only-vendor-identity',
                    'persisted_active_slot': label, 'slots': {label: {'models': models}}}
