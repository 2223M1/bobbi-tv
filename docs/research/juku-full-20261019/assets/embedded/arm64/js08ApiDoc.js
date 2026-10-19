        function openApiDocModal(initialLibId) {
            var select = document.getElementById('apiDocLibSelect');
            var writableLibs = getWritableLibraries();
            var selectedId = '';

            if (initialLibId && initialLibId !== 'all' && writableLibs.some(function(l) { return l.id === initialLibId; })) {
                selectedId = initialLibId;
            } else if (state.currentLib && state.currentLib.id && state.currentLib.share_type !== 2 && writableLibs.some(function(l) { return l.id === state.currentLib.id; })) {
                selectedId = state.currentLib.id;
            } else if (writableLibs.length > 0) {
                selectedId = writableLibs[0].id;
            }

            if (select) {
                select.innerHTML = '';
                if (writableLibs.length === 0) {
                    var opt = document.createElement('option');
                    opt.value = '';
                    opt.innerText = '暂无可导入的自建媒体库 (订阅库为只读模式)';
                    opt.disabled = true;
                    opt.selected = true;
                    select.appendChild(opt);
                } else {
                    writableLibs.forEach(function(lib) {
                        var opt = document.createElement('option');
                        opt.value = lib.id;
                        var typeTag = lib.share_type === 1 ? ' [快照]' : ' [自建]';
                        opt.innerText = (lib.name || '未命名媒体库') + typeTag + ' (' + lib.id + ')';
                        if (lib.id === selectedId) {
                            opt.selected = true;
                        }
                        select.appendChild(opt);
                    });
                }
            }

            updateApiDocCodeSnippets(selectedId);
            openModal('apiDocModal');
        }

        function handleApiDocLibChange(val) {
            updateApiDocCodeSnippets(val);
        }

        function updateApiDocCodeSnippets(targetLibId) {
            var writableLibs = getWritableLibraries();
            var matchedLib = writableLibs.find(function(l) { return l.id === targetLibId; });
            var libId = matchedLib ? matchedLib.id : ((writableLibs.length > 0) ? writableLibs[0].id : 'lib_xxxxxx');
            var hasValidLib = (matchedLib != null || (writableLibs.length > 0 && !targetLibId));

            var badgeEl = document.getElementById('apiDocLibIdBadge');
            if (badgeEl) {
                badgeEl.innerText = hasValidLib ? libId : '无可用媒体库 (订阅库只读)';
                badgeEl.style.color = hasValidLib ? '#38bdf8' : '#f87171';
            }

            var oldIdEl = document.getElementById('apiDocLibId');
            if (oldIdEl) oldIdEl.innerText = hasValidLib ? libId : '无可用媒体库';

            var singleCurl = '# 1. cURL 单条精准导入完整调用示例 (支持保留 // 注释与尾随逗号):\n' +
                'curl -X POST http://127.0.0.1:17654/api/private/import_link \\\n' +
                '  -H "Content-Type: application/json" \\\n' +
                '  -d \'{\n' +
                '    // === 必填基础参数 ===\n' +
                '    "library_id": "' + libId + '",            // [必填] 目标私有媒体库 ID (上方可一键复制)\n' +
                '    "url": "https://pan.quark.cn/s/459dbb8ab48b",  // [必填] 播放资源链接 (支持网盘/HTTP直链/磁力magnet/ED2K)\n' +
                '\n' +
                '    // === 精准匹配标识 (可选，三选一即可，强烈推荐 imdb / tmdb_id，100% 精确刮削官方元数据) ===\n' +
                '    "imdb": "tt7126948",                   // [可选] IMDb 编号 (如 tt7126948，通过 TMDB 100% 精确反查刮削)\n' +
                '    "tmdb_id": 414906,                     // [可选] TMDB 条目 ID (如 414906，直接抓取官方全套海报与元数据)\n' +
                '    "vod_id": "",                          // [可选] 自有或站方影视 ID (库内已有该 ID 时直接合并追加播放链接)\n' +
                '\n' +
                '    // === 影视基础信息 (可选，无精准 ID 时用于智能检索与建片) ===\n' +
                '    "title": "新蝙蝠侠",                    // [可选] 影视片名 (若留空则自动从文件名或 URL 提取)\n' +
                '    "year": "2022",                        // [可选] 上映年份 (如 2022)\n' +
                '    "type_id": 1,                          // [可选] 影视分类: 1 电影, 2 电视剧/动漫/综艺\n' +
                '    "media_type": "movie",                 // [可选] TMDB 媒体类型: "movie" 电影, "tv" 电视剧\n' +
                '\n' +
                '    // === 剧集分集定位 (可选，电视剧/动漫分集使用，默认第 1 季第 1 集) ===\n' +
                '    "season": 1,                           // [可选] 季号 (如 1 表示第 1 季，默认 1)\n' +
                '    "episode": 1,                          // [可选] 集号 (如 1 表示第 1 集，默认 1)\n' +
                '    "episode_title": "第1集",               // [可选] 单集小标题\n' +
                '\n' +
                '    // === 网盘凭证与辅助信息 (可选) ===\n' +
                '    "password": "",                        // [可选] 网盘提取码/访问密码 (参数名亦可为 pwd)\n' +
                '    "skip_exists_link": 1,                 // [可选] 传 1 时若库内已存在该链接前缀则直接跳过，防止重复导入\n' +
                '    "remark": "4K HDR 杜比视界",            // [可选] 资源清晰度/压制版本备注\n' +
                '    "file_name": "",                       // [可选] 原始文件名 (辅助片名智能提取与分集识别)\n' +
                '    "parent_folder_name": "",              // [可选] 上级文件夹名 (辅助季号识别)\n' +
                '    "provider": "",                        // [可选] 网盘平台 (如 夸克网盘/115网盘/百度网盘/阿里，留空自动识别)\n' +
                '    "link_type": ""                        // [可选] 链接类型: pan/http/magnet/ed2k (留空自动识别)\n' +
                '  }\'';

            var panCurl = '# 2. 网盘大包导入 (自动深度扫描子目录，视频数 > 50 时自动启用异步防超时；亦可显式指定 "async": true):\n' +
                'curl -X POST http://127.0.0.1:17654/api/private/import_link \\\n' +
                '  -H "Content-Type: application/json" \\\n' +
                '  -d \'{\n' +
                '    "library_id": "' + libId + '",\n' +
                '    "url": "https://pan.quark.cn/s/459dbb8ab48b",\n' +
                '    "password": "",\n' +
                '    "skip_exists_link": 1, // [可选] 传 1 时若库内已存在该链接前缀则直接跳过\n' +
                '    "async": true   // [可选] 显式开启异步模式，毫秒级返回 task_id，防止客户端超时\n' +
                '  }\'\n\n' +
                '# 2.1 轮询任务进度与最终入库结果 (GET /api/private/import_task):\n' +
                'curl http://127.0.0.1:17654/api/private/import_task?task_id=task_imp_xxxxxxxx';

            var pythonCode = '# 3. Python requests 异步导入与进度轮询完整示例:\n' +
                'import requests, time\n\n' +
                '# 发起导入 (支持 skip_exists_link=1 防重，传入 async=True 或当大包文件 > 50 时自动异步)\n' +
                'resp = requests.post("http://127.0.0.1:17654/api/private/import_link", json={\n' +
                '    "library_id": "' + libId + '",\n' +
                '    "url": "https://pan.quark.cn/s/459dbb8ab48b",\n' +
                '    "skip_exists_link": 1,\n' +
                '    "async": True\n' +
                '})\n' +
                'data = resp.json()\n' +
                'print("提交响应:", data)\n\n' +
                '# 若进入异步队列，轮询任务状态直至完成\n' +
                'if data.get("action") == "queued":\n' +
                '    task_id = data["task_id"]\n' +
                '    while True:\n' +
                '        t_resp = requests.get(f"http://127.0.0.1:17654/api/private/import_task?task_id={task_id}").json()\n' +
                '        status = t_resp.get("status")\n' +
                '        prog = t_resp.get("progress", {})\n' +
                '        print(f"[{prog.get(\'percent\', 0)}%] {prog.get(\'stage\')}")\n' +
                '        if status in ("completed", "failed", "canceled"):\n' +
                '            print("最终结果:", t_resp.get("result"))\n' +
                '            break\n' +
                '        time.sleep(1)';

            var singleEl = document.getElementById('codeBlockCurlSingle');
            if (singleEl) singleEl.innerText = singleCurl;

            var panEl = document.getElementById('codeBlockCurlPan');
            if (panEl) panEl.innerText = panCurl;

            var pyEl = document.getElementById('codeBlockPython');
            if (pyEl) pyEl.innerText = pythonCode;

            // 同步更新暂存箱旧折叠面板代码
            var oldCurlEl = document.getElementById('apiDocCurlSample');
            if (oldCurlEl) {
                oldCurlEl.innerText = singleCurl + '\n\n' + panCurl + '\n\n' + pythonCode;
            }
        }

        function updateApiCheatSheetContent(scope) {
            var writableLibs = getWritableLibraries();
            var targetLibId = (scope && scope !== 'all' && writableLibs.some(function(l) { return l.id === scope; })) 
                ? scope 
                : ((writableLibs.length > 0) ? writableLibs[0].id : 'lib_xxxxxx');
            updateApiDocCodeSnippets(targetLibId);
        }

        function copyApiDocLibId() {
            var badgeEl = document.getElementById('apiDocLibIdBadge');
            var text = badgeEl ? badgeEl.innerText.trim() : '';
            if (!text || text.indexOf('lib_') !== 0 || text === 'lib_xxxxxx') {
                showToast('暂无有效自建媒体库 ID 可复制 (订阅媒体库只读)');
                return;
            }
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text).then(function() {
                    showToast('已复制媒体库 ID: ' + text);
                });
            } else {
                showToast('媒体库 ID: ' + text);
            }
        }

        function copyApiDocCurl() {
            var badgeEl = document.getElementById('apiDocLibIdBadge');
            var text = badgeEl ? badgeEl.innerText.trim() : '';
            if (!text || text.indexOf('lib_') !== 0 || text === 'lib_xxxxxx') {
                showToast('暂无有效自建媒体库可生成 cURL 命令 (订阅媒体库只读)');
                return;
            }
            var singleEl = document.getElementById('codeBlockCurlSingle');
            if (!singleEl) return;
            var textCurl = singleEl.innerText;
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(textCurl).then(function() {
                    showToast('已复制单条 cURL 命令示例');
                });
            } else {
                showToast('已复制');
            }
        }

        function copyApiDocCode(type) {
            var el = null;
            var msg = '已复制代码示例';
            if (type === 'curlSingle') {
                el = document.getElementById('codeBlockCurlSingle');
                msg = '已复制单条 cURL 命令示例';
            } else if (type === 'curlPan') {
                el = document.getElementById('codeBlockCurlPan');
                msg = '已复制网盘大包 cURL 命令示例';
            } else if (type === 'pythonSample') {
                el = document.getElementById('codeBlockPython');
                msg = '已复制 Python 批量导入示例';
            }
            if (!el) return;
            var text = el.innerText;
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text).then(function() {
                    showToast(msg);
                });
            } else {
                showToast(msg);
            }
        }

        function copyApiCurlSample() {
            copyApiDocCurl();
        }

        function copyApiLibId() {
            copyApiDocLibId();
        }
