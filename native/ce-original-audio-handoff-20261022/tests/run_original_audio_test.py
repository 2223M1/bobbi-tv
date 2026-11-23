"""Compile the production helper and extracted production comparator, without a device."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

HERE = Path(__file__).resolve().parent
PREFIX = r'''
#include <memory>
#include <string>
namespace StreamFlags {enum {FLAG_ORIGINAL=1,FLAG_HEARING_IMPAIRED=2,FLAG_VISUAL_IMPAIRED=4,FLAG_DEFAULT=8,FLAG_COMMENT=16};}
struct SelectionStream {int type_index;int flags;int channels;std::string language;std::string codec;std::string name;};
struct CSettings {
 enum {SETTING_LOCALE_AUDIOLANGUAGE,SETTING_ACCESSIBILITY_AUDIOHEARING,SETTING_ACCESSIBILITY_AUDIOVISUAL,SETTING_VIDEOPLAYER_PREFERDEFAULTFLAG};
 std::string GetString(int) const {return "original";}
 bool GetBool(int id) const {return id==SETTING_VIDEOPLAYER_PREFERDEFAULTFLAG;}
};
struct SettingsComponent {std::shared_ptr<CSettings> GetSettings(){return std::make_shared<CSettings>();}};
struct CServiceBroker {static SettingsComponent* GetSettingsComponent(){static SettingsComponent value;return &value;}};
struct StringUtils {static bool EqualsNoCase(const std::string& a,const std::string& b){return a==b;}};
struct Language {std::string GetAudioLanguage(bool){return "";}} g_langInfo;
struct Expander {bool CompareISO639Codes(const std::string& a,const std::string& b){return a==b;}} g_LangCodeExpander;
struct StreamUtils {static int GetCodecPriority(const std::string&){return 0;}};
#define PREDICATE_RETURN(lh,rh) do {if((lh)!=(rh)) return (lh)>(rh);} while(0)
'''


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-root', type=Path, default=HERE.parent/'candidate')
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    source = args.candidate_root/'xbmc/cores/VideoPlayer/VideoPlayer.cpp'
    header = args.candidate_root/'xbmc/cores/VideoPlayer/BobiOriginalAudio.h'
    text = source.read_text()
    comparator = text[text.index('class PredicateAudioFilter'):text.index('class PredicateSubtitlePriority')]
    run = args.output_dir/('run-' + str(time.time_ns()))
    run.mkdir(parents=True)
    (run/'actual_audio_comparator.h').write_text(PREFIX + comparator)
    report = dict(source_sha256=sha(source), helper_sha256=sha(header),
                  harness_sha256=sha(HERE/'original_audio_test.cpp'),
                  comparator_sha256=hashlib.sha256(comparator.encode()).hexdigest(),
                  scope='Native helper and real comparator; settings/language service stubs; not device playback')
    command = ['g++', '-std=c++17', '-O1', '-Wall', '-Wextra', '-Werror',
               '-I' + str(args.candidate_root/'xbmc'), '-I' + str(run),
               str(HERE/'original_audio_test.cpp'), '-o', str(run/'original_audio_test')]
    report['command'] = command
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    report.update(compile_returncode=result.returncode, compile_output=result.stdout + result.stderr)
    if result.returncode == 0:
        result = subprocess.run([str(run/'original_audio_test')], capture_output=True, text=True, timeout=15)
        report.update(returncode=result.returncode, output=result.stdout + result.stderr)
    report['state'] = 'PASSED' if result.returncode == 0 else 'FAILED'
    (run/'original-audio-test-result.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(dict(run=str(run), **report)))
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
