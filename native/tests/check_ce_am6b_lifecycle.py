"""Run normal frame/skin lifecycle contracts against the linked CE sources and their predecessor."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile


def definition(source, signature):
    start = source.index(signature)
    brace = source.index('{', start)
    return source[start:source.index('\n}', brace)+2]


def check(old, new, base, output):
    output.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='frame-skin-contract-', dir=output))
    template = Path(__file__).with_name('ce_am6b_lifecycle.cpp.in').read_text()
    results = {}
    for candidate, root in [(False, old), (True, new)]:
        def read(relative):
            file = root/'xbmc'/relative
            return (file if file.is_file() else base/'xbmc'/relative).read_text()
        codec = 'cores/VideoPlayer/DVDCodecs/Video/DVDVideoCodecAmlogic.'
        renderer = 'cores/VideoPlayer/VideoRenderers/HwDecRender/RendererAML.'
        header, source, render = read(codec+'h'), read(codec+'cpp'), read(renderer+'cpp')
        skin = read('addons/Skin.cpp')
        buf = definition(header, 'class CAMLVideoBuffer :')+';'
        commit = definition(render, 'void CRendererAML::CommitVideoLayer')
        async_commit = re.search(r'void RenderVideoLayerCommit\([^)]*\) override\s*\{[^}]+\}', read(renderer+'h'))[0]
        handler = definition(skin, 'class CSkinSettingUpdateHandler')+';'
        handlers = skin[skin.index('void CSkinSettingUpdateHandler::'):skin.index('} /*namespace ADDON*/')]
        lifecycle = [definition(skin, sig) for sig in ('void CSkinInfo::Start(', 'void CSkinInfo::Unload(',
                                                        'void CSkinInfo::ProcessTimers(')]
        selectors = [re.findall(r'm_settingsUpdateHandler->[^;]+;', code) for code in lifecycle]
        unload = definition(read('application/ApplicationSkinHandling.cpp'), 'void CApplicationSkinHandling::UnloadSkin()')
        policy = unload.split('{', 1)[1].split('CGUIComponent* gui', 1)[0]
        close = definition(source, 'void CDVDVideoCodecAmlogic::Close(')
        reset = definition(source, 'void CDVDVideoCodecAmlogic::Reset(')
        assert close.index('ReleaseAllBuffers()') < close.index('CloseDecoder(false)')
        if candidate:
            assert reset.index('ReleaseAllBuffers()') < reset.index('m_Codec->Reset()')
        blocks = dict(buf=buf.replace('std::mutex m_frameMutex', 'ProbeMutex m_frameMutex'),
            declaration=commit[:commit.index('\n{')].replace('CRendererAML::','')+';',
            commit=commit, async_commit=async_commit.replace(' override',''),
            frame='\n'.join(definition(source,'void CAMLVideoBuffer::'+method) for method in ('Present(', 'Discard(')) if candidate else '',
            pool=definition(source,'void CAMLVideoBufferPool::ReleaseAllBuffers('),
            render='\n'.join(definition(render,'void CRendererAML::'+method) for method in
                             ('BeginAsyncVideoLayerRender(', 'EndAsyncVideoLayerRender(', 'ReleaseBuffer(')),
            handler=handler.replace('std::chrono::steady_clock','TestClock'), handlers=handlers,
            start='\n'.join(selectors[0]), unload='\n'.join(selectors[1]), process='\n'.join(selectors[2]), policy=policy)
        cpp = template
        for tag, value in blocks.items():
            assert cpp.count('/*@'+tag+'@*/') == 1
            cpp = cpp.replace('/*@'+tag+'@*/',value)
        label = 'candidate' if candidate else 'predecessor'
        test = work/(label+'.cpp')
        test.write_text(cpp)
        exe = work/label
        subprocess.run(['g++','-std=c++17','-O2','-pthread','-DCANDIDATE='+str(int(candidate)),
                        str(test),'-o',str(exe)],check=True)
        r = subprocess.run([str(exe)], capture_output=True, text=True, timeout=15)
        rows = dict((line.split()[0],line.split()[1]=='1') for line in r.stdout.splitlines())
        assert r.returncode==0 and set(rows)=={'pinned_frame','ownership','discard','duplicate_pts',
            'close_barrier','debounce','unload_save','profile_switch','reactivate','reentrant'}, (r.returncode,rows)
        failures = {key for key, passed in rows.items() if not passed}
        expected = set() if candidate else {'pinned_frame','ownership','close_barrier','unload_save','profile_switch'}
        assert failures==expected, (label, rows)
        results[label] = dict(cases=rows, source_sha256=hashlib.sha256(test.read_bytes()).hexdigest())
    proof = work/'result.json'
    proof.write_text(json.dumps(results, indent=2))
    print(json.dumps(dict(report=str(proof), **results)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('old','new','base','output'):
        parser.add_argument('--'+arg, required=True, type=Path)
    check(**vars(parser.parse_args()))
