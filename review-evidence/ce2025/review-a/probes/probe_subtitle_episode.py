#!/usr/bin/env python3
"""Read-only CE2024 subtitle admission probe (stdlib only, no network/Kodi).

Usage: python probe_subtitle_episode.py --repo /path/to/bobbi-tv

Reads three actual repository files. It AST-extracts their pure filename parser,
SingleSeason/matches/from_details, and rank helpers into an in-memory package;
it does NOT import the full addon, download subtitles, or copy product source.
All filenames and metadata used below are synthetic fixtures.

Scope: the unseasoned subtitle admission contract reviewed at CE2024 commit
c4e0baca6acefa58f031979bff71e7cd1028efdf. This is not generic CI, an integration
test, a video continuation test, or evidence of a wrong subtitle on a device.
Changed source hashes are reported; a compatible fix can produce exit 0.

Exit 1: at least one of the four ambiguous filenames was admitted.
Exit 0: none was admitted, and all narrow positive/negative controls passed.
Exit 2: missing source, incompatible interface/environment, or a control failed.
JSON is emitted to stdout. No files are written, including Python bytecode.
"""
import argparse
import ast
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sys
from types import ModuleType

sys.dont_write_bytecode = True
REVIEWED_HEAD = 'c4e0baca6acefa58f031979bff71e7cd1028efdf'
PREFIX = 'addons/script.module.bobbi.core/lib/bobbi_core/'
FILES = {
    'filename_semantics': ('b48b9d6ce77f44dfdcbcade70fffa7990e787117',
                           PREFIX + 'filename_semantics.py'),
    'subtitle_episode': ('a94bdc0fda6c7e55b38a05a8e5abee8477eba922',
                         PREFIX + 'subtitle_episode.py'),
    'subtitle_candidates': ('075c027bdc7417c4e0bc87c41f9daa20372ccb8d',
                            PREFIX + 'subtitle_candidates.py'),
}


class Incompatible(Exception):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Incompatible(message)


def read_sources(root):
    trees, fingerprints = {}, []
    for name, (reviewed_blob, relative) in FILES.items():
        path = root / relative
        raw = path.read_bytes()
        if not 0 < len(raw) <= 2 * 1024 * 1024:
            raise Incompatible('Source size outside this probe scope: ' + relative)
        blob = hashlib.sha1(b'blob ' + str(len(raw)).encode('ascii') + b'\0' + raw).hexdigest()
        fingerprints.append(dict(path=relative, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                                 git_blob_sha1=blob, reviewed_blob_sha1=reviewed_blob,
                                 matches_reviewed_blob=(blob == reviewed_blob)))
        trees[name] = ast.parse(raw.decode('utf-8'), filename=relative)
    return trees, fingerprints


def extract(tree, required, filename):
    """Select real definitions/constant assignments, without executing addon IO."""
    selected, found = [], set()
    for node in tree.body:
        names = set()
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(target.id for target in node.targets if isinstance(target, ast.Name))
        if names & required:
            selected.append(node)
            found.update(names & required)
    if found != required:
        raise Incompatible('Unsupported source interface in ' + filename + ': ' +
                           ', '.join(sorted(required - found)))
    return compile(ast.Module(body=selected, type_ignores=[]), filename, 'exec')


def load_pure_contract(trees):
    package = ModuleType('bobbi_core')
    package.__path__ = []
    sys.modules['bobbi_core'] = package
    grammar = ModuleType('bobbi_core.filename_semantics')
    grammar.__dict__.update(re=re, dataclass=dataclass)
    sys.modules[grammar.__name__] = grammar
    exec(extract(trees['filename_semantics'],
                 {'STRONG', 'WEAK', 'MULTI', 'TECHNICAL', 'REVISION',
                  'FilenameSemantics', 'parse_filename'}, FILES['filename_semantics'][1]),
         grammar.__dict__)
    episode = ModuleType('bobbi_core.subtitle_episode')
    episode.__dict__.update(re=re, dataclass=dataclass, parse_filename=grammar.parse_filename)
    sys.modules[episode.__name__] = episode
    exec(extract(trees['subtitle_episode'], {'SingleSeason', 'from_details', 'matches'},
                 FILES['subtitle_episode'][1]), episode.__dict__)
    candidates = ModuleType('bobbi_core.subtitle_candidates')
    candidates.__dict__.update(re=re)
    sys.modules[candidates.__name__] = candidates
    exec(extract(trees['subtitle_candidates'], {'EDITION', 'EXCLUDE', 'normalized', 'episode_tags', 'rank'},
                 FILES['subtitle_candidates'][1]), candidates.__dict__)
    return episode, candidates.rank


def run_cases(episode, rank):
    context = dict(title='Ping Pong The Animation', mode='series', season=1, episode=1,
                   tmdb=60811, year=2014, release='Vodes 1080p HEVC',
                   _subtitle_single_season=episode.SingleSeason(60811, 11))

    def row(filename):
        return dict(videoname='Ping Pong The Animation 2014 [BD 1920x1080 HEVC FLAC]',
                    lang={'langlist': {'langchs': True}}, filename=filename)

    controls = []

    def control(label, actual, expected):
        controls.append(dict(case=label, expected=expected, actual=actual, passed=(actual == expected)))

    positive = ['Ping Pong EP01.ass', 'Ping Pong 第01話.ass',
                '[Group] Ping Pong [01].chs.ass', 'Ping Pong S01E01.ass']
    negative = ['Ping Pong EP02.ass', 'Ping Pong 第02話.ass', 'Ping Pong S02E01.ass',
                'Ping Pong EP01-EP02.ass', 'Ping Pong [01-02].ass',
                'Ping Pong 第01話-第02話.ass', 'Ping Pong 1080p 2014.ass',
                '[01] Group Ping Pong.ass', 'Ping Pong EP01 EP02.ass']
    for name in positive:
        control('positive: ' + name, rank(row(name), context) is not None, True)
    for name in negative:
        control('negative: ' + name, rank(row(name), context) is not None, False)
    scopes = [('missing', None), ('untyped', {'tmdb': 60811, 'episodes': 11}),
              ('wrong_tmdb', episode.SingleSeason(999, 11)),
              ('zero_episodes', episode.SingleSeason(60811, 0))]
    for label, scope in scopes:
        actual = rank(row('Ping Pong EP01.ass'), dict(context, _subtitle_single_season=scope))
        control('scope: ' + label, actual is not None, False)
    explicit = row('Ping Pong EP01.ass')
    explicit['videoname'] += ' S02'
    control('explicit season 2: accepted for season 2', rank(explicit,
            dict(context, season=2, _subtitle_single_season=None)) is not None, True)
    control('explicit season 2: rejected for season 1', rank(explicit, context) is not None, False)
    details = dict(id=60811, name='Ping Pong The Animation', number_of_seasons=1,
                   seasons=[dict(season_number=1, episode_count=11)])
    control('details: canonical single season',
            episode.from_details(details, 60811) == episode.SingleSeason(60811, 11), True)
    control('details: mismatched TMDb', episode.from_details(details, 999) is not None, False)
    control('details: multiple seasons', episode.from_details(dict(details, number_of_seasons=2,
            seasons=details['seasons'] + [dict(season_number=2, episode_count=12)]), 60811) is not None, False)
    ambiguous = []
    for name in ['Ping Pong EP01,02.ass', 'Ping Pong EP01、02.ass',
                 'Ping Pong 第01話、02話.ass', 'Ping Pong EP01;02.ass']:
        score = rank(row(name), context)
        ambiguous.append(dict(filename=name, expected='reject ambiguous episode enumeration',
                              admitted=(score is not None), rank=score))
    return dict(controls=controls, ambiguous_cases=ambiguous,
                controls_passed=all(case['passed'] for case in controls),
                ambiguous_admitted=sum(case['admitted'] for case in ambiguous))


def main(argv=None):
    result = dict(probe='ce2024_subtitle_episode_admission', reviewed_head=REVIEWED_HEAD,
                  method='AST-extracted real pure definitions; synthetic metadata/filenames',
                  limits=['No Kodi, network, subtitle bytes, full addon initialization, or device test',
                          'Does not test video selection/automatic continuation or claim an observed wrong subtitle',
                          'Compatible changed files are allowed; inspect their reported hashes'])
    saved = {name: sys.modules.get(name) for name in ('bobbi_core',
             'bobbi_core.filename_semantics', 'bobbi_core.subtitle_episode', 'bobbi_core.subtitle_candidates')}
    try:
        parser = Parser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
        parser.add_argument('--repo', required=True, type=Path, help='Actual bobbi-tv repository root (read only)')
        args = parser.parse_args(argv)
        root = args.repo.expanduser().resolve(strict=True)
        result['repo'] = str(root)
        trees, result['source_files'] = read_sources(root)
        episode, rank = load_pure_contract(trees)
        result.update(run_cases(episode, rank))
        if not result['controls_passed']:
            result.update(exit_code=2, status='environment_or_interface_incompatible',
                          reason='A positive/negative control failed; no defect conclusion is issued')
        elif result['ambiguous_admitted']:
            result.update(exit_code=1, status='ambiguity_defect_observed_in_fixture')
        else:
            result.update(exit_code=0, status='defect_not_reproduced_within_this_probe_scope')
    except Exception as error:
        result.update(exit_code=2, status='environment_or_interface_incompatible',
                      error_type=type(error).__name__, reason=str(error)[:400])
    finally:
        for name, prior in saved.items():
            if prior is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prior
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result['exit_code']


if __name__ == '__main__':
    sys.exit(main())
