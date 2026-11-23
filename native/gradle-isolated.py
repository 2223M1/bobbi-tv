"""Honor the build host's existing HTTP proxy for Java; never package it."""
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit

task_root = Path(sys.argv[1]).resolve()
if not str(task_root).startswith('/opt/bobbi-native-'):
    raise ValueError('Isolated root required')
env = dict(os.environ)
env['JAVA_HOME'] = str(task_root / 'toolchain/jdk-17.0.18+8')
env['GRADLE_USER_HOME'] = str(task_root / 'gradle')
options = []
proxy = urlsplit(env.get('https_proxy') or env.get('HTTPS_PROXY') or '')
if proxy.hostname:
    if proxy.username or proxy.password or proxy.scheme not in ('http', 'https'):
        raise ValueError('Authenticated/non-HTTP Java proxy needs explicit host configuration')
    for scheme in ('http', 'https'):
        options.extend(['-D' + scheme + '.proxyHost=' + proxy.hostname,
                        '-D' + scheme + '.proxyPort=' + str(proxy.port or 80)])
    options.append('-Dhttp.nonProxyHosts=localhost|127.*|[::1]')
env['GRADLE_OPTS'] = ' '.join(options)
gradle = task_root / 'toolchain/gradle-8.3/bin/gradle'
raise SystemExit(subprocess.call([str(gradle)] + sys.argv[2:], env=env))
