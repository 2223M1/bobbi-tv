#!/usr/bin/env python3
"""Offline probe of unchanged production sample() with real saved decoder text.

Only the device I/O boundaries (state, RPC, Path.read_text) are fixtures.
The complete sample() and request_status() function ASTs execute unchanged.
No remote/device code at module top level is imported or executed.

This diagnostic confirms the retained historical overwrite behavior. It is
not a post-fix acceptance test. After repair, regression tests must assert
per-channel preservation and channel-order invariance, not these lost values.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import time


SOURCE = 'tools/ce_trial_remote.py'
EVIDENCE = 'review-evidence/ce-new-work-grand_budapest-observe-1792551462588057300.json'


def git_blob(raw):
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def checked(path, fixed, relative):
    raw = path.read_bytes()
    item = next(row for row in fixed['tree']['tree'] if row['path'] == relative)
    if git_blob(raw) != item['sha']:
        raise ValueError('Source/evidence Git identity mismatch: ' + relative)
    return raw, dict(path=relative, git_blob=git_blob(raw), sha256=hashlib.sha256(raw).hexdigest())


def load_sample(source, text):
    module = ast.parse(source)
    selected = [node for node in module.body if isinstance(node, ast.FunctionDef)
                and node.name in {'sample', 'request_status'}]
    if {node.name for node in selected} != {'sample', 'request_status'}:
        raise ValueError('Actual production functions unavailable')
    class FakePath:
        def __init__(self, value):
            if value != '/sys/class/vdec/vdec_status':
                raise ValueError('Unexpected file access')
        def read_text(self):
            return text
    def rpc(method, params=None):
        if method == 'Player.GetActivePlayers':
            return []
        if method in ('XBMC.GetInfoLabels', 'GUI.GetProperties'):
            return {}
        raise ValueError('Unexpected RPC')
    scope = dict(Path=FakePath, rpc=rpc, re=re, time=time,
                 state=lambda record: ({'desired': {}}, {}, {'phase': 'PREPARING'}))
    exec(compile(ast.Module(body=selected, type_ignores=[]), SOURCE, 'exec'), scope)
    return scope['sample']({})['decoder_counters']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True, help='Current source checkout or verified snapshot')
    parser.add_argument('--fixed-source', type=Path, required=True, help='Current fixed branch/tree metadata JSON')
    parser.add_argument('--receipt', type=Path, required=True, help='Original retained decoder observation JSON')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--old-repo', type=Path, help='Optional previous source checkout or snapshot')
    parser.add_argument('--old-fixed-source', type=Path, help='Optional previous fixed metadata; pair with --old-repo')
    args = parser.parse_args()
    if (args.old_repo is None) != (args.old_fixed_source is None):
        parser.error('--old-repo and --old-fixed-source must be supplied together')
    fixed = json.loads(args.fixed_source.read_text())
    source, source_record = checked(args.repo/SOURCE, fixed, SOURCE)
    evidence, evidence_record = checked(args.receipt, fixed, EVIDENCE)
    old_fixed = old_source = old_record = None
    if args.old_repo is not None:
        old_fixed = json.loads(args.old_fixed_source.read_text())
        old_source, old_record = checked(args.old_repo/SOURCE, old_fixed, SOURCE)
    receipt = json.loads(evidence)['result']
    raw = receipt['decoder']
    blocks = re.findall(r'(?ms)^vdec channel \d+ statistics:.*?(?=^vdec channel \d+ statistics:|\Z)', raw)
    if len(blocks) != 2:
        raise ValueError('Expected exactly two channels in real retained decoder text')
    cases = []
    for label, value in [('channel0-only-control', blocks[0]), ('original-channel-order', raw),
                         ('same-blocks-reversed', ''.join(reversed(blocks)))]:
        case = dict(case=label, actual_sample_counters=load_sample(source, value),
                    input_sha256=hashlib.sha256(value.encode()).hexdigest())
        if old_source is not None:
            case['old_sample_counters'] = load_sample(old_source, value)
        cases.append(case)
    control, full, reverse = [row['actual_sample_counters'] for row in cases]
    fields = ['drop count', 'fra err count', 'hw err count']
    if not all(control[k] == reverse[k] == 8 and full[k] == 0 for k in fields):
        raise ValueError('Observed production behavior differs from reported loss')
    def counters_expression(tree):
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'sample')
        return next(n for n in function.body if isinstance(n, ast.Assign)
                    and isinstance(n.value, ast.DictComp))
    new_expr = counters_expression(ast.parse(source))
    old_expr = counters_expression(ast.parse(old_source)) if old_source is not None else None
    identical = (ast.dump(old_expr, include_attributes=False) == ast.dump(new_expr, include_attributes=False)
                 if old_expr is not None else None)
    old_behavior_matches = (all(row['old_sample_counters'] == row['actual_sample_counters'] for row in cases)
                            if old_source is not None else None)
    result = dict(schema=1, finding='decoder channel counters overwritten by later channel',
                  head=fixed['branch']['commit']['sha'],
                  old_head=old_fixed['branch']['commit']['sha'] if old_fixed else None,
                  priority='P2',
                  regression_status=('pre-existing in previous reviewed source' if identical and old_behavior_matches
                                     else 'previous source differs; inspect comparison' if old_source is not None
                                     else 'previous source comparison not requested'),
                  probe_purpose='Confirm retained historical information loss; not post-fix acceptance',
                  post_fix_acceptance='Assert per-channel preservation and channel-order invariance; do not retain lost values as expected behavior',
                  scope='Offline complete production sample() functions; real retained decoder text; device I/O fixtures only',
                  source=source_record, old_source=old_record, evidence=evidence_record,
                  source_lines=[new_expr.lineno, new_expr.end_lineno],
                  old_source_lines=[old_expr.lineno, old_expr.end_lineno] if old_expr else None,
                  parser_AST_identical=identical, old_behavior_matches=old_behavior_matches,
                  cases=cases, current_saved_samples=[s['decoder_counters'] for s in receipt['samples']],
                  decoder_channel0_device='dvbldec', decoder_channel1_device='dveldec',
                  lost_nonzero_counters=fields, channel_order_changes_output=full!=reverse,
                  historical_counts_not_attributed_to_observation_interval=True,
                  root_cause_of_startup_failure_not_proven=True,
                  startup_failure_still_open=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['head','old_head','source_lines','old_source_lines',
        'parser_AST_identical','cases','channel_order_changes_output']}, indent=2))


if __name__ == '__main__':
    main()
