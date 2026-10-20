        var PRESET_COVERS = [
            "https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=500&auto=format&fit=crop&q=60",
            "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?w=500&auto=format&fit=crop&q=60",
            "https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=500&auto=format&fit=crop&q=60",
            "https://images.unsplash.com/photo-1534447677768-be436bb09401?w=500&auto=format&fit=crop&q=60",
            "https://images.unsplash.com/photo-1509198397868-475647b2a1e5?w=500&auto=format&fit=crop&q=60",
            "https://images.unsplash.com/photo-1536440136628-849c177e76a1?w=500&auto=format&fit=crop&q=60"
        ];

        var PROVIDER_NAMES = {
            "ALIYUN": "阿里云盘", "QUARK": "夸克网盘", "UC": "UC网盘", "BAIDU": "百度网盘",
            "XUNLEI": "迅雷云盘", "CLOUD123": "123云盘", "CLOUD115": "115网盘", "115": "115网盘",
            "CHINA_MOBILE": "移动云盘", "CHINA_TELECOM": "天翼云盘", "GUANGYA": "光鸭云盘",
            "ali": "阿里云盘", "qk": "夸克网盘", "uc": "UC网盘", "bd": "百度网盘",
            "xl": "迅雷云盘", "123": "123云盘", "yd": "移动云盘", "ty": "天翼云盘", "gy": "光鸭云盘",
            "1": "阿里云盘", "2": "夸克网盘", "3": "UC网盘", "4": "百度网盘",
            "5": "迅雷云盘", "6": "123云盘", "7": "115网盘", "8": "移动云盘",
            "9": "天翼云盘", "11": "光鸭云盘"
        };

        // --- 10 大网盘保序与自定义排序支持 (与“我的网盘”页全局同步) ---
        var DEFAULT_PAN_ORDER = ["7", "4", "2", "3", "11", "6", "9", "8", "5", "1", "10"];
        var PAN_ORDER_ITEMS = [
            { id: "7", name: "115网盘" },
            { id: "4", name: "百度网盘" },
            { id: "2", name: "夸克网盘" },
            { id: "3", name: "UC网盘" },
            { id: "11", name: "光鸭云盘" },
            { id: "6", name: "123云盘" },
            { id: "9", name: "天翼云盘" },
            { id: "8", name: "移动云盘" },
            { id: "5", name: "迅雷云盘" },
            { id: "1", name: "阿里云盘" }
        ];
        var PAN_ALIAS_TO_ID = {
            "7": "7", "115": "7", "CLOUD115": "7",
            "4": "4", "bd": "4", "BAIDU": "4",
            "2": "2", "qk": "2", "QUARK": "2",
            "3": "3", "uc": "3", "UC": "3",
            "11": "11", "gy": "11", "GUANGYA": "11",
            "6": "6", "123": "6", "CLOUD123": "6",
            "9": "9", "ty": "9", "CHINA_TELECOM": "9",
            "8": "8", "yd": "8", "CHINA_MOBILE": "8",
            "5": "5", "xl": "5", "XUNLEI": "5",
            "1": "1", "ali": "1", "ALIYUN": "1",
            "10": "10"
        };

        var currentPanOrder = DEFAULT_PAN_ORDER.slice();

        function fetchPanOrder() {
            fetch('/api/pan/order')
                .then(function(res) { return res.json(); })
                .then(function(data) {
                    if (data && data.success && Array.isArray(data.order) && data.order.length > 0) {
                        currentPanOrder = data.order;
                    }
                })
                .catch(function(err) {
                    console.warn('获取网盘自定义排序失败:', err);
                });
        }
        fetchPanOrder();

        function savePanOrder(newOrder, onSuccess) {
            currentPanOrder = newOrder;
            fetch('/api/pan/order', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ order: newOrder })
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (data && data.success) {
                    if (onSuccess) onSuccess();
                } else {
                    showToast('保存排序失败: ' + ((data && data.message) || '未知错误'));
                }
            })
            .catch(function(err) {
                showToast('保存排序失败: ' + err.message);
            });
        }

        function getPanOrderIndex(panIdentifier) {
            var id = PAN_ALIAS_TO_ID[panIdentifier] || panIdentifier;
            var idx = currentPanOrder.indexOf(String(id));
            return idx !== -1 ? idx : 999;
        }

        // 线路排序权重计算：磁力和ED2K (down) 强制紧随 115网盘 (ID 7) 之后！
        function getSourceLineOrderRank(lineKey) {
            if (lineKey === 'down' || lineKey === 'magnet' || lineKey === 'ed2k') {
                var pos115 = getPanOrderIndex('7');
                return (pos115 !== 999) ? (pos115 + 0.5) : 0.5;
            }
            return getPanOrderIndex(lineKey);
        }

        var CLOUD_SHARE_PREFIXES = {
            "1": "https://www.alipan.com/s/",
            "2": "https://pan.quark.cn/s/",
            "3": "https://drive.uc.cn/s/",
            "4": "https://pan.baidu.com/s/",
            "5": "https://pan.xunlei.com/s/",
            "6": "https://www.123pan.com/s/",
            "7": "https://115.com/s/",
            "8": "https://caiyun.139.com/m/i?",
            "9": "https://cloud.189.cn/t/",
            "11": "https://www.guangyapan.com/s/",
            
            "ali": "https://www.alipan.com/s/",
            "qk": "https://pan.quark.cn/s/",
            "uc": "https://drive.uc.cn/s/",
            "bd": "https://pan.baidu.com/s/",
            "xl": "https://pan.xunlei.com/s/",
            "123": "https://www.123pan.com/s/",
            "115": "https://115.com/s/",
            "yd": "https://caiyun.139.com/m/i?",
            "ty": "https://cloud.189.cn/t/",
            "gy": "https://www.guangyapan.com/s/",

            "ALIYUN": "https://www.alipan.com/s/",
            "QUARK": "https://pan.quark.cn/s/",
            "UC": "https://drive.uc.cn/s/",
            "BAIDU": "https://pan.baidu.com/s/",
            "XUNLEI": "https://pan.xunlei.com/s/",
            "CLOUD123": "https://www.123pan.com/s/",
            "CLOUD115": "https://115.com/s/",
            "CHINA_MOBILE": "https://caiyun.139.com/m/i?",
            "CHINA_TELECOM": "https://cloud.189.cn/t/",
            "GUANGYA": "https://www.guangyapan.com/s/",

            "阿里云盘": "https://www.alipan.com/s/",
            "夸克网盘": "https://pan.quark.cn/s/",
            "UC网盘": "https://drive.uc.cn/s/",
            "百度网盘": "https://pan.baidu.com/s/",
            "迅雷云盘": "https://pan.xunlei.com/s/",
            "123云盘": "https://www.123pan.com/s/",
            "115网盘": "https://115.com/s/",
            "移动云盘": "https://caiyun.139.com/m/i?",
            "天翼云盘": "https://cloud.189.cn/t/",
            "光鸭云盘": "https://www.guangyapan.com/s/"
        };

        function isPanShareLink(url) {
            if (!url) return false;
            var lower = String(url).toLowerCase();
            return (
                lower.indexOf('115.com') !== -1 || lower.indexOf('115cdn') !== -1 || lower.indexOf('anxia.com') !== -1 ||
                lower.indexOf('alipan.com') !== -1 || lower.indexOf('aliyundrive.com') !== -1 ||
                lower.indexOf('quark.cn') !== -1 ||
                lower.indexOf('baidu.com') !== -1 ||
                lower.indexOf('uc.cn') !== -1 ||
                lower.indexOf('123pan') !== -1 || lower.indexOf('123684') !== -1 || lower.indexOf('123865') !== -1 || lower.indexOf('123952') !== -1 ||
                lower.indexOf('139.com') !== -1 ||
                lower.indexOf('189.cn') !== -1 || lower.indexOf('content.21cn.com') !== -1 ||
                lower.indexOf('xunlei.com') !== -1 ||
                lower.indexOf('guangyapan.com') !== -1
            );
        }

        // 判断链接是否已精准定位到具体的子文件（包含 #fid=, &fid=, ?fid=, #cid=...&fid=, /file/ 等），单文件无需进行大包递归展开
        function hasSubFileLocator(url) {
            if (!url) return false;
            return /[#?&](?:fid|file_id|target_id)=/i.test(url) || /\/file\/[a-zA-Z0-9_-]+/i.test(url);
        }

        function toShareUrl(rawUrl, panName) {
            if (!rawUrl) return "";
            rawUrl = String(rawUrl).trim();
            if (rawUrl.indexOf('http://') === 0 || rawUrl.indexOf('https://') === 0) {
                return rawUrl;
            }
            var prefix = CLOUD_SHARE_PREFIXES[panName];
            if (prefix) {
                if ((panName === "8" || panName === "CHINA_MOBILE" || panName === "yd" || panName === "移动云盘") && rawUrl.indexOf("cid=") !== 0) {
                    return prefix + "cid=" + rawUrl;
                }
                return prefix + rawUrl;
            }
            return rawUrl;
        }

        function formatBackdropUrl(p) {
            if (!p) return "";
            p = String(p).trim();
            if (p.indexOf('http://') === 0 || p.indexOf('https://') === 0) {
                return p;
            }
            if (p.indexOf('/') !== 0) {
                p = '/' + p;
            }
            return 'https://image.tmdb.org/t/p/original' + p;
        }

        function formatProxiedImgUrl(u) {
            if (!u) return '';
            u = String(u).trim();
            if (u.indexOf('image.tmdb.org') !== -1 && u.indexOf('/api/image/proxy') === -1) {
                return '/api/image/proxy?url=' + encodeURIComponent(u);
            }
            return u;
        }

        function formatFileSize(bytes) {
            if (!bytes || bytes <= 0) return '';
            var units = ['B', 'KB', 'MB', 'GB', 'TB'];
            var val = parseFloat(bytes);
            var idx = 0;
            while (val >= 1024 && idx < units.length - 1) {
                val /= 1024;
                idx++;
            }
            return (idx === 0 ? val.toFixed(0) : val.toFixed(1)) + ' ' + units[idx];
        }

        function formatSizeMB(mb) {
            if (!mb || mb <= 0) return '';
            var val = parseFloat(mb);
            if (isNaN(val) || val <= 0) return '';
            if (val >= 1024 * 1024) {
                return (val / (1024 * 1024)).toFixed(2) + ' TB';
            }
            if (val >= 1024) {
                return (val / 1024).toFixed(2) + ' GB';
            }
            return (val >= 100 ? val.toFixed(0) : val.toFixed(1)) + ' MB';
        }

        var MEDIA_EXTS = ['.mp4', '.mkv', '.avi', '.ts', '.mov', '.flv', '.iso', '.rmvb', '.wmv', '.m4v', '.m2ts', '.strm'];
        function isMediaFile(fileName) {
            if (!fileName) return false;
            var lower = fileName.toLowerCase();
            for (var i = 0; i < MEDIA_EXTS.length; i++) {
                if (lower.endsWith(MEDIA_EXTS[i])) return true;
            }
            return false;
        }

        var state = {
            currentLevel: 1,
            currentLib: null,
            currentMovie: null,
            libraries: [],
            movies: [],
            links: [],
            selectedPresetCover: PRESET_COVERS[0],
            selectedMovieIds: [],
            movieViewMode: localStorage.getItem('juku_movie_view_mode') || 'poster',
            moviePage: 1,
            moviePageSize: parseInt(localStorage.getItem('juku_movie_page_size') || '100', 10),
            movieTotal: 0,
            episodeTotal: 0,
            linkTotal: 0,
            movieTotalPages: 1,
            movieKeyword: '',
            movieTypeFilter: 0,
            movieSortBy: 'updated_at',
            movieSortOrder: 'desc',
            excelMatched: [],
            excelUnmatched: [],
            excelUnmatchedViewMode: 'series',
            excelUnmatchedSeriesGroups: {},
            excelUnmatchedSeriesCandidatesMap: {},
            excelUnmatchedSelectedKeys: [],
            activeEditingLibId: null,
            activeEditingLinkId: null,
            searchResultsList: [],
            searchQuery: '',
            searchPage: 1,
            searchPageSize: 20,
            searchTotalPages: 1,
            searchTotal: 0,
            checkedSearchVideos: {},
            currentDetailVideo: null,
            currentActiveSourceTab: 'all',
            currentActiveSeasonTab: 'all',
            detailModalMode: 'create_movie',
            previewImportData: null,
            publicLibsList: [],
            publicLibsPage: 1,
            publicLibsPageSize: 25,
            publicLibsTotal: 0,
            publicLibsTotalPages: 1,
            publicLibsQuery: '',
            unmatchedQueueList: [],
            unmatchedQueueSelectedIds: [],
            unmatchedCurrentScope: 'all',
            unmatchedCounts: {},
            unmatchedGlobalTotal: 0,
            unmatchedViewMode: 'series',
            unmatchedSeriesGroups: {},
            unmatchedSeriesCandidatesMap: {}
        };

        // 智能分离 TMDB ID 与年份，并彻底洗净标题 (兼容文件名、花括号/中括号/圆括号)
        function extractTmdbIdAndClean(rawTitle) {
            if (!rawTitle) return { title: '', tmdbId: 0, year: '' };
            var text = String(rawTitle).trim();
            // 仅对紧邻英文字母的英文所有格/缩写中的异形单引号做规范化 (如 "Bug‘s" -> "Bug's", "Marvel’s" -> "Marvel's")，绝不误伤任何中文单双引号或中文标点
            text = text.replace(/([a-zA-Z])[‘'’\u0060\u00b4]([a-zA-Z])/g, "$1'$2");
            var tmdbId = 0;

            // 1. 强力提取 TMDB ID (支持 {tmdbid-91066}, [tmdbid:87632], (tmdb-106119), tmdbid:91066 等)
            var tmdbPattern = /[\{\[\(（【]?\s*(?:tmdb[_\-\s]?id|tmdb)\s*[:：=\-_#]?\s*(\d{2,10})\s*[\}\]\)）】]?/gi;
            var match;
            while ((match = tmdbPattern.exec(text)) !== null) {
                if (!tmdbId && match[1]) {
                    tmdbId = parseInt(match[1], 10) || 0;
                }
            }
            text = text.replace(tmdbPattern, ' ');

            // 2. 剥离括号包裹的年份 (1997), [2004], (2026) 等
            var year = '';
            var yearPattern = /[\(\[（【]\s*((?:19\d\d|20\d\d))\s*[\)\]）】]/g;
            var ym;
            while ((ym = yearPattern.exec(text)) !== null) {
                if (!year && ym[1]) {
                    year = ym[1];
                }
            }
            text = text.replace(yearPattern, ' ');

            // 3. 剥离末尾的点号/空格年份，例如 "康熙微服私访记 1997" 或 "康熙微服私访记.1997"
            if (!year) {
                var tailYearPattern = /(?:[\s._\-]+)((?:19\d\d|20\d\d))(?:\s*)$/;
                var tym = text.match(tailYearPattern);
                if (tym) {
                    year = tym[1];
                    text = text.replace(tailYearPattern, ' ');
                }
            }

            // 4. 去除可能残存的空括号对
            text = text.replace(/\{\s*\}/g, ' ').replace(/\[\s*\]/g, ' ').replace(/\(\s*\)/g, ' ').replace(/（\s*）/g, ' ').replace(/【\s*】/g, ' ');

            // 5. 若带有常见视频后缀且已被分离出 tmdbId 或括号年份，剥离扩展名
            if (tmdbId > 0 || year) {
                text = text.replace(/\.(?:mp4|mkv|avi|mov|wmv|iso|ts|flv|rmvb)$/i, '');
            }

            // 6. 清理首尾多余的点号、破折号与空格
            text = text.replace(/\s+/g, ' ').replace(/^[\s._\-]+|[\s._\-]+$/g, '').trim();
            return {
                title: text,
                tmdbId: tmdbId,
                year: year
            };
        }

        function fetchTmdbSearch(keyword, searchYear, searchImdb) {
            if (!keyword && !searchImdb) return Promise.resolve([]);
            var cleanObj = extractTmdbIdAndClean(keyword);
            var cleanKey = cleanObj.title || keyword;
            var cleanYear = searchYear || cleanObj.year || '';
            var tmdbId = cleanObj.tmdbId;
            var trimmedKey = String(cleanKey).trim();

            // 若用户未显式指定 tmdbId，且输入的是大于 2099 的纯长数字（如 530915），才可能是直接粘贴的 TMDb ID
            // 常见的 4 位公历年份数字（如 1000~2099，如 1776, 1917, 1984, 2012 等）为人类历史与影视真实片名，必须作为标题检索！
            if (!tmdbId && /^\d+$/.test(trimmedKey)) {
                var numVal = parseInt(trimmedKey, 10) || 0;
                if (numVal > 2099) {
                    tmdbId = numVal;
                }
            }

            // 若具有 TMDB ID，优先直达检索云端库与 TMDB
            if (tmdbId > 0) {
                return fetch('/api/mv/videos/search?tmdbId=' + tmdbId)
                    .then(function(res) { return res.json(); })
                    .then(function(data) {
                        var searchType = (data && data.data && data.data.searchType) || '';
                        var items = (data && data.data && Array.isArray(data.data.items)) ? data.data.items : [];
                        // 必须严格校验返回类型为 tmdb 精准匹配，且确实包含该 tmdbId，杜绝未命中时 fallback 为全站最新无关影片
                        if (searchType === 'tmdb' && items.length > 0 && items.some(function(it) { return (it.tmdbId || it.tmdb_id) == tmdbId; })) {
                            return items.filter(function(it) { return (it.tmdbId || it.tmdb_id) == tmdbId; }).map(function(item) {
                                return {
                                    id: item.tmdbId || item.tmdb_id || tmdbId,
                                    title: item.title,
                                    name: item.title,
                                    original_title: item.ename || item.original_title || '',
                                    release_date: item.year ? (item.year + '-01-01') : '',
                                    first_air_date: item.year ? (item.year + '-01-01') : '',
                                    poster_path: item.pic ? item.pic.replace('https://image.tmdb.org/t/p/w500', '') : '',
                                    backdrop_path: item.backdropPath || item.backdrop_path || '',
                                    vote_average: item.rating ? parseFloat(item.rating) : 0,
                                    media_type: (item.typeId === 2) ? 'tv' : 'movie',
                                    overview: item.content || ''
                                };
                            });
                        }
                        // 云端库未命中该 TMDb ID，回退至本地 TMDB 接口精准查询电影/剧集详情
                        return fetch('/api/tmdb/movie/' + tmdbId)
                            .then(function(r) { return r.json(); })
                            .then(function(d) {
                                if (d && d.success && d.data && d.data.id) {
                                    var m = d.data;
                                    return [{
                                        id: m.id,
                                        title: m.title || m.original_title || '',
                                        name: m.title || m.original_title || '',
                                        original_title: m.original_title || '',
                                        release_date: m.release_date || '',
                                        first_air_date: '',
                                        poster_path: m.poster_path || '',
                                        backdrop_path: m.backdrop_path || '',
                                        vote_average: m.vote_average || 0,
                                        media_type: 'movie',
                                        overview: m.overview || ''
                                    }];
                                }
                                return [];
                            })
                            .catch(function() { return []; });
                    })
                    .catch(function() { return []; });
            }

            var url = '/api/tmdb/search/movie?';
            if (searchImdb) {
                url += 'imdb_id=' + encodeURIComponent(searchImdb) + '&query=' + encodeURIComponent(trimmedKey || searchImdb);
            } else {
                url += 'query=' + encodeURIComponent(trimmedKey);
            }
            if (cleanYear) url += '&year=' + encodeURIComponent(cleanYear);
            return fetch(url)
                .then(function(res) { return res.json(); })
                .then(function(data) {
                    if (data && data.data && Array.isArray(data.data.results)) {
                        return data.data.results;
                    }
                    return [];
                })
                .catch(function() { return []; });
        }

        function showToast(msg, duration) {
            if (!duration) duration = 2500;
            var toast = document.getElementById('appToast');
            toast.innerText = msg;
            toast.classList.add('show');
            setTimeout(function() { toast.classList.remove('show'); }, duration);
        }

        // 通用剪贴板复制工具：自动兼容 HTTP/HTTPS、局域网 IP 与老旧浏览器降级
        function copyToClipboard(text, successToast) {
            if (!text || text === '-') return;
            var toastMsg = successToast || '已复制到剪贴板！';

            function fallbackCopy(str) {
                var textArea = document.createElement('textarea');
                textArea.value = str;
                textArea.style.position = 'fixed';
                textArea.style.top = '0';
                textArea.style.left = '0';
                textArea.style.width = '2em';
                textArea.style.height = '2em';
                textArea.style.padding = '0';
                textArea.style.border = 'none';
                textArea.style.outline = 'none';
                textArea.style.boxShadow = 'none';
                textArea.style.background = 'transparent';
                textArea.style.opacity = '0';
                textArea.setAttribute('readonly', '');
                document.body.appendChild(textArea);
                textArea.focus();
                textArea.select();
                if (typeof textArea.setSelectionRange === 'function') {
                    textArea.setSelectionRange(0, str.length);
                }
                var successful = false;
                try {
                    successful = document.execCommand('copy');
                } catch (err) {
                    console.warn('execCommand copy failed:', err);
                }
                document.body.removeChild(textArea);
                if (successful) {
                    showToast(toastMsg);
                } else {
                    prompt('自动复制受限，请直接手动复制下方文本：', str);
                }
            }

            if (window.isSecureContext && navigator && navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
                navigator.clipboard.writeText(text).then(function() {
                    showToast(toastMsg);
                }).catch(function(err) {
                    console.warn('navigator.clipboard.writeText failed, trying fallback:', err);
                    fallbackCopy(text);
                });
            } else {
                fallbackCopy(text);
            }
        }

        function closeModal(id) {
            var el = document.getElementById(id);
            if (el) el.classList.remove('active');
        }
        function openModal(id) {
            var el = document.getElementById(id);
            if (el) el.classList.add('active');
        }

        function openImageSettingsModal() {
            openModal('imageSettingsModal');
            fetch('/api/image/settings')
                .then(function(res) { return res.json(); })
                .then(function(json) {
                    if (json && json.data) {
                        var keepOriginal = !!json.data.keep_original_quality;
                        var enableDoh = json.data.enable_doh !== false;
                        var enablePrewarm = json.data.enable_prewarm !== false;
                        var optFast = document.getElementById('imgQualityFast');
                        var optOriginal = document.getElementById('imgQualityOriginal');
                        var chkDoh = document.getElementById('imgEnableDoh');
                        var chkPrewarm = document.getElementById('imgEnablePrewarm');
                        if (optFast && optOriginal) {
                            if (keepOriginal) {
                                optOriginal.checked = true;
                            } else {
                                optFast.checked = true;
                            }
                        }
                        if (chkDoh) {
                            chkDoh.checked = enableDoh;
                        }
                        if (chkPrewarm) {
                            chkPrewarm.checked = enablePrewarm;
                        }
                    }
                })
                .catch(function(err) {
                    console.error('Failed to load image settings:', err);
                });
        }

        function saveImageSettings() {
            var optOriginal = document.getElementById('imgQualityOriginal');
            var chkDoh = document.getElementById('imgEnableDoh');
            var chkPrewarm = document.getElementById('imgEnablePrewarm');
            var keepOriginal = optOriginal ? optOriginal.checked : false;
            var enableDoh = chkDoh ? chkDoh.checked : true;
            var enablePrewarm = chkPrewarm ? chkPrewarm.checked : true;

            var btn = document.getElementById('btnSaveImageSettings');
            if (btn) btn.disabled = true;

            fetch('/api/image/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    keep_original_quality: keepOriginal,
                    enable_doh: enableDoh,
                    enable_prewarm: enablePrewarm
                })
            })
            .then(function(res) { return res.json(); })
            .then(function(json) {
                if (btn) btn.disabled = false;
                closeModal('imageSettingsModal');
                showToast('🎉 图片画质与加速设置已保存并立即生效');
            })
            .catch(function(err) {
                if (btn) btn.disabled = false;
                alert('保存失败: ' + err);
            });
        }

        function copyTextFromElement(elemId) {
            var el = document.getElementById(elemId);
            if (!el) return;
            var text = el.innerText || el.textContent;
            if (!text || text.indexOf('正在获取') !== -1) return;
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text).then(function() {
                    showToast('📋 已复制地址: ' + text);
                }).catch(function() {
                    fallbackCopyText(text);
                });
            } else {
                fallbackCopyText(text);
            }
        }

        function fallbackCopyText(text) {
            var ta = document.createElement('textarea');
            ta.value = text;
            ta.style.position = 'fixed';
            ta.style.opacity = '0';
            document.body.appendChild(ta);
            ta.focus();
            ta.select();
            try {
                document.execCommand('copy');
                showToast('📋 已复制地址: ' + text);
            } catch (e) {
                prompt('请手动长按复制地址:', text);
            }
            document.body.removeChild(ta);
        }

        function escapeAttr(str) {
            if (str === null || str === undefined) return '';
            return String(str)
                .replace(/&/g, '&amp;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;');
        }

        // =========================================================================
        // 通用下拉菜单 (Dropdown Menu) 控制逻辑与工具角标合并更新
        // =========================================================================

        function toggleDropdownMenu(menuId, event) {
            if (event) {
                event.stopPropagation();
            }
            var menu = document.getElementById(menuId);
            if (!menu) return;
            var wrapper = menu.closest('.dropdown-menu-wrapper');
            var isOpen = menu.classList.contains('active');

            // 先关闭其它打开的下拉菜单
            closeAllDropdowns();

            if (!isOpen) {
                menu.classList.add('active');
                if (wrapper) wrapper.classList.add('active');
            }
        }

        function closeAllDropdowns() {
            var panels = document.querySelectorAll('.dropdown-menu-panel.active');
            panels.forEach(function(p) {
                p.classList.remove('active');
            });
            var wrappers = document.querySelectorAll('.dropdown-menu-wrapper.active');
            wrappers.forEach(function(w) {
                w.classList.remove('active');
            });
        }

        // 全局点击监听：点击外部自动收起下拉菜单
        document.addEventListener('click', function(e) {
            if (!e.target.closest('.dropdown-menu-wrapper')) {
                closeAllDropdowns();
            }
        });

        // 统一合并计算【🛠️ 库工具】上的聚合待办角标
        function updateCombinedToolsBadge() {
            var unmBadge = document.getElementById('badgeL2Unmatched');
            var dupBadge = document.getElementById('badgeL2Duplicates');
            var combBadge = document.getElementById('badgeL2ToolsCombined');
            if (!combBadge) return;

            var unmCount = (unmBadge && unmBadge.style.display !== 'none') ? (parseInt(unmBadge.innerText, 10) || 0) : 0;
            var dupCount = (dupBadge && dupBadge.style.display !== 'none') ? (parseInt(dupBadge.innerText, 10) || 0) : 0;
            var total = unmCount + dupCount;

            if (total > 0) {
                combBadge.innerText = total > 99 ? '99+' : total;
                combBadge.style.display = 'inline-flex';
                if (unmCount > 0) {
                    combBadge.style.background = '#ef4444';
                    combBadge.style.color = '#fff';
                } else {
                    combBadge.style.background = '#eab308';
                    combBadge.style.color = '#000';
                }
            } else {
                combBadge.style.display = 'none';
            }
        }




        var cachedEmbyConfigData = null;

        function openEmbySettingsModal(keepOpen) {
            if (!keepOpen) {
                openModal('embySettingsModal');
            }
            loadEmbyConfig();
        }

        var embyPortCheckTimer = null;
        function checkEmbyPortAvailability(port) {
            var statusEl = document.getElementById('embyPortStatus');
            if (!statusEl) return;
            statusEl.innerHTML = '<span style="color: var(--text-muted);">正在检测端口...</span>';

            fetch('/api/private/emby/check-port?port=' + encodeURIComponent(port))
                .then(function(res) { return res.json(); })
                .then(function(json) {
                    if (!statusEl) return;
                    if (json && json.available) {
                        statusEl.innerHTML = '<span style="color: #4ade80; font-weight: 600;">🟢 端口 ' + json.port + ' 空闲可用</span>';
                    } else {
                        var errMsg = (json && json.error) ? json.error : ('端口 ' + port + ' 已被占用');
                        statusEl.innerHTML = '<span style="color: #f87171; font-weight: 600;" title="' + (typeof escapeAttr === 'function' ? escapeAttr(errMsg) : errMsg) + '">⚠️ 端口 ' + port + ' 已被占用，请更换</span>';
                    }
                })
                .catch(function() {
                    if (statusEl) statusEl.innerHTML = '<span style="color: #fbbf24;">(检测超时，保存时将再次校验)</span>';
                });
        }

        function onEmbyEnabledChange() {
            var chk = document.getElementById('embyCfgEnabled');
            var statusEl = document.getElementById('embyPortStatus');
            var inputPort = document.getElementById('embyCfgPort');
            var port = inputPort ? parseInt(inputPort.value, 10) : 8096;

            if (chk && chk.checked) {
                checkEmbyPortAvailability(port);
            } else if (statusEl) {
                statusEl.innerHTML = '<span style="color: var(--text-muted);">(独立端口未启用，防端口冲突)</span>';
            }
        }

        function onEmbyPortInput() {
            var chk = document.getElementById('embyCfgEnabled');
            if (!chk || !chk.checked) return;
            var inputPort = document.getElementById('embyCfgPort');
            var port = inputPort ? parseInt(inputPort.value, 10) : 8096;

            if (embyPortCheckTimer) clearTimeout(embyPortCheckTimer);
            embyPortCheckTimer = setTimeout(function() {
                checkEmbyPortAvailability(port);
            }, 300);
        }

        function loadEmbyConfig() {
            fetch('/api/private/emby/config')
                .then(function(res) { return res.json(); })
                .then(function(json) {
                    if (json && json.data) {
                        var d = json.data;
                        cachedEmbyConfigData = d;
                        var elUrlStand = document.getElementById('embyConnectUrlStandalone');
                        var elUrlDef = document.getElementById('embyConnectUrlDefault');
                        var chkEnabled = document.getElementById('embyCfgEnabled');
                        var inputPort = document.getElementById('embyCfgPort');
                        var inputServerName = document.getElementById('embyCfgServerName');

                        var isEnabled = !!d.enabled;
                        if (chkEnabled) chkEnabled.checked = isEnabled;
                        if (inputPort) inputPort.value = d.port || 8096;
                        if (inputServerName) inputServerName.value = d.server_name || '巨库媒体服务器';

                        if (elUrlStand) {
                            if (isEnabled) {
                                elUrlStand.innerText = d.connect_url_standalone || ('http://' + d.local_ip + ':' + d.port);
                            } else {
                                elUrlStand.innerHTML = '<span style="color: var(--text-muted); font-size: 11px;">(独立端口未开启，勾选下方启用后生效)</span>';
                            }
                        }
                        if (elUrlDef) elUrlDef.innerText = d.connect_url_default || ('http://' + d.local_ip + ':17654');

                        var statusEl = document.getElementById('embyPortStatus');
                        if (isEnabled) {
                            checkEmbyPortAvailability(d.port || 8096);
                        } else if (statusEl) {
                            statusEl.innerHTML = '<span style="color: var(--text-muted);">(独立端口未启用，防端口冲突)</span>';
                        }

                        renderEmbyUsersList(d.users || [], d.primary_user || d.username || 'admin');
                    }
                })
                .catch(function(err) {
                    console.error('Failed to load emby config:', err);
                });
        }

        function renderEmbyUsersList(users, primaryUser) {
            var container = document.getElementById('embyUsersList');
            if (!container) return;
            if (!users || users.length === 0) {
                container.innerHTML = '<div style="font-size: 12px; color: var(--text-muted); text-align: center; padding: 12px;">暂无用户账号，请点击上方“➕ 添加账号”创建</div>';
                return;
            }
            var html = '';
            for (var i = 0; i < users.length; i++) {
                var u = users[i];
                var isPrim = u.is_primary || (primaryUser && u.username === primaryUser);
                var encId = encodeURIComponent(u.id || '');
                var encUser = encodeURIComponent(u.username || '');
                var dispUser = typeof escapeHtml === 'function' ? escapeHtml(u.username) : escapeAttr(u.username);

                html += '<div style="display: flex; align-items: center; justify-content: space-between; background: rgba(0,0,0,0.25); border: 1px solid ' + (isPrim ? 'rgba(234,179,8,0.35)' : 'rgba(255,255,255,0.06)') + '; border-radius: 6px; padding: 8px 12px;">';
                
                // 左侧信息与标签
                html += '  <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">';
                html += '    <span style="font-size: 14px;">' + (isPrim ? '👑' : '👤') + '</span>';
                html += '    <span style="font-family: monospace; font-size: 13px; font-weight: 600; color: ' + (isPrim ? '#facc15' : '#f8fafc') + ';">' + dispUser + '</span>';
                if (isPrim) {
                    html += '    <span style="background: rgba(234,179,8,0.15); color: #facc15; border: 1px solid rgba(234,179,8,0.3); padding: 1px 7px; border-radius: 10px; font-size: 11px; font-weight: 600;">⭐️ 主账号 (Kodi电视同步)</span>';
                } else {
                    html += '    <span style="background: rgba(148,163,184,0.12); color: #94a3b8; border: 1px solid rgba(148,163,184,0.2); padding: 1px 6px; border-radius: 10px; font-size: 11px;">子账号</span>';
                }
                if (u.has_password) {
                    html += '    <span style="font-size: 11px; color: #38bdf8;" title="已设置访问密码">🔒 已设密码</span>';
                } else {
                    html += '    <span style="font-size: 11px; color: #4ade80;" title="无需密码直接登录">🔓 免密登录</span>';
                }
                html += '  </div>';

                // 右侧操作按钮
                html += '  <div style="display: flex; align-items: center; gap: 6px;">';
                if (!isPrim) {
                    html += '    <button class="btn btn-secondary btn-xs" style="padding: 2px 8px; font-size: 11px; color: #facc15; border-color: rgba(234,179,8,0.4);" onclick="setEmbyPrimaryUser(decodeURIComponent(\'' + encId + '\'), decodeURIComponent(\'' + encUser + '\'))" title="将该账号的进度漫游绑定到 Kodi 电视端海报墙">设为主账号</button>';
                }
                html += '    <button class="btn btn-secondary btn-xs" style="padding: 2px 8px; font-size: 11px;" onclick="changeEmbyUserPassword(decodeURIComponent(\'' + encId + '\'), decodeURIComponent(\'' + encUser + '\'), ' + (u.has_password ? 'true' : 'false') + ')">修改密码</button>';
                if (!isPrim) {
                    html += '    <button class="btn btn-secondary btn-xs" style="padding: 2px 8px; font-size: 11px; color: #ef4444; border-color: rgba(239,68,68,0.3);" onclick="deleteEmbyUser(decodeURIComponent(\'' + encId + '\'), decodeURIComponent(\'' + encUser + '\'))">删除</button>';
                }
                html += '  </div>';

                html += '</div>';
            }
            container.innerHTML = html;
        }

        function showEmbyAddUserForm() {
            var form = document.getElementById('embyAddUserForm');
            if (form) {
                form.style.display = 'block';
                var input = document.getElementById('newEmbyUsername');
                if (input) {
                    input.value = '';
                    input.focus();
                }
                var pw = document.getElementById('newEmbyPassword');
                if (pw) pw.value = '';
            }
        }

        function hideEmbyAddUserForm() {
            var form = document.getElementById('embyAddUserForm');
            if (form) form.style.display = 'none';
        }

        function submitEmbyAddUser() {
            var inputUser = document.getElementById('newEmbyUsername');
            var inputPw = document.getElementById('newEmbyPassword');
            var username = inputUser ? inputUser.value.trim() : '';
            var password = inputPw ? inputPw.value.trim() : '';

            if (!username) {
                alert('请输入用户名');
                if (inputUser) inputUser.focus();
                return;
            }

            fetch('/api/private/emby/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    action: 'add_user',
                    username: username,
                    password: password
                })
            })
            .then(function(res) { return res.json(); })
            .then(function(json) {
                if (json && json.success) {
                    hideEmbyAddUserForm();
                    showToast('🎉 用户 [' + username + '] 添加成功');
                    loadEmbyConfig();
                } else {
                    alert('添加用户失败: ' + (json ? json.error : '未知错误'));
                }
            })
            .catch(function(err) {
                alert('添加用户请求失败: ' + err);
            });
        }

        function setEmbyPrimaryUser(userId, username) {
            fetch('/api/private/emby/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    action: 'set_primary',
                    user_id: userId,
                    username: username
                })
            })
            .then(function(res) { return res.json(); })
            .then(function(json) {
                if (json && json.success) {
                    showToast('⭐️ 已将 [' + username + '] 设为主账号，Kodi 电视端海报墙将自动以此账号同步漫游');
                    loadEmbyConfig();
                } else {
                    alert('切换主账号失败: ' + (json ? json.error : '未知错误'));
                }
            })
            .catch(function(err) {
                alert('切换主账号失败: ' + err);
            });
        }

        function changeEmbyUserPassword(userId, username, hasPassword) {
            var msg = '请输入用户 [' + username + '] 的新访问密码 (留空则为免密直接登录):';
            var newPw = prompt(msg, '');
            if (newPw === null) return; // 用户取消

            fetch('/api/private/emby/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    action: 'update_password',
                    user_id: userId,
                    username: username,
                    password: newPw.trim()
                })
            })
            .then(function(res) { return res.json(); })
            .then(function(json) {
                if (json && json.success) {
                    showToast('🎉 用户 [' + username + '] 密码已更新');
                    loadEmbyConfig();
                } else {
                    alert('修改密码失败: ' + (json ? json.error : '未知错误'));
                }
            })
            .catch(function(err) {
                alert('修改密码失败: ' + err);
            });
        }

        function deleteEmbyUser(userId, username) {
            if (!confirm('确定要删除 Emby 账号 [' + username + '] 吗？\n删除后该账号将无法再登录客户端。')) {
                return;
            }

            fetch('/api/private/emby/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    action: 'delete_user',
                    user_id: userId,
                    username: username
                })
            })
            .then(function(res) { return res.json(); })
            .then(function(json) {
                if (json && json.success) {
                    showToast('🗑️ 用户 [' + username + '] 已成功删除');
                    loadEmbyConfig();
                } else {
                    alert('删除用户失败: ' + (json ? json.error : '未知错误'));
                }
            })
            .catch(function(err) {
                alert('删除用户失败: ' + err);
            });
        }

        function saveEmbySettings() {
            var chkEnabled = document.getElementById('embyCfgEnabled');
            var inputPort = document.getElementById('embyCfgPort');
            var inputServerName = document.getElementById('embyCfgServerName');

            var enabled = chkEnabled ? chkEnabled.checked : false;
            var port = inputPort ? parseInt(inputPort.value, 10) : 8096;
            var serverName = inputServerName ? inputServerName.value.trim() : '巨库媒体服务器';

            if (enabled && (!port || port <= 0 || port > 65535)) {
                alert('请输入有效的端口号 (1-65535)');
                if (inputPort) inputPort.focus();
                return;
            }

            var btn = document.getElementById('btnSaveEmbySettings');
            if (btn) btn.disabled = true;

            var payload = {
                enabled: enabled,
                port: port,
                server_name: serverName
            };

            fetch('/api/private/emby/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            })
            .then(function(res) { return res.json(); })
            .then(function(json) {
                if (btn) btn.disabled = false;
                if (json && json.success) {
                    closeModal('embySettingsModal');
                    showToast('🎉 Emby 协议服务配置已更新并重启生效');
                } else {
                    alert('保存失败: ' + (json ? json.error : '未知错误'));
                }
            })
            .catch(function(err) {
                if (btn) btn.disabled = false;
                alert('保存失败: ' + err);
            });
        }

        // 全局键盘监听：按 ESC 键优雅关闭最顶层活跃弹窗
        window.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' || e.key === 'Esc' || e.keyCode === 27) {
                var openModals = Array.from(document.querySelectorAll('.modal-overlay.active'));
                if (openModals.length > 0) {
                    openModals.sort(function(a, b) {
                        var zA = parseInt(window.getComputedStyle(a).zIndex) || 1000;
                        var zB = parseInt(window.getComputedStyle(b).zIndex) || 1000;
                        return zA - zB;
                    });
                    var topModal = openModals[openModals.length - 1];
                    if (topModal && topModal.id) {
                        if (topModal.id === 'excelModal' && state.excelUnmatched && state.excelUnmatched.length > 0) {
                            showToast('⚠️ 待确认列表中尚有未确认记录，为防误操作已禁用 Esc 快捷关闭');
                            return;
                        }
                        closeModal(topModal.id);
                    }
                }
            }
        });

        // 点击遮罩灰色背景区域关闭弹窗
        document.addEventListener('click', function(e) {
            if (e.target && e.target.classList && e.target.classList.contains('modal-overlay') && e.target.classList.contains('active')) {
                if (e.target.id === 'excelModal' && state.excelUnmatched && state.excelUnmatched.length > 0) {
                    showToast('⚠️ 待确认列表中尚有未确认记录，为防误操作已禁用点击外部关闭');
                    return;
                }
                closeModal(e.target.id);
            }
        });

        // ------------------ 用户认证与状态 ------------------
        var authState = {
            token: localStorage.getItem('user_token') || '',
            user: (function() {
                try {
                    return JSON.parse(localStorage.getItem('user_info') || 'null');
                } catch(e) { return null; }
            })(),
            pendingCallback: null
        };

        function authFetch(url, options) {
            options = options || {};
            options.headers = options.headers || {};
            if (authState.token) {
                options.headers['Authorization'] = 'Bearer ' + authState.token;
                options.headers['X-User-Token'] = authState.token;
            }
            return fetch(url, options);
        }

        function initUserAuth() {
            renderUserNav();
            if (authState.token) {
                authFetch('/api/mv/user/auth/me')
                    .then(function(res) { return res.json(); })
                    .then(function(data) {
                        if (data.success && data.data) {
                            authState.user = data.data;
                            localStorage.setItem('user_info', JSON.stringify(data.data));
                            renderUserNav();
                        } else if (data.status === 401 || data.message?.indexOf('失效') >= 0) {
                            logoutUser(true);
                        }
                    })
                    .catch(function() {});
            }
        }

        function renderUserNav() {
            var box = document.getElementById('userNavBox');
            if (!box) return;
            if (authState.token && authState.user) {
                var initial = (authState.user.nickname || authState.user.username || 'U').charAt(0).toUpperCase();
                var displayName = authState.user.nickname || authState.user.username || '用户';
                box.innerHTML = 
                    '<div class="user-chip" onclick="toggleUserDropdown(event)">' +
                        '<div class="user-avatar-circle">' + initial + '</div>' +
                        '<span class="user-chip-name">' + displayName + '</span>' +
                        '<span style="font-size: 10px; color: var(--text-muted);">▼</span>' +
                    '</div>' +
                    '<div class="user-popover" id="userDropdownPopover" onclick="event.stopPropagation()">' +
                        '<div style="font-size: 11px; color: var(--text-muted); margin-bottom: 2px;">当前账号</div>' +
                        '<div style="font-size: 14px; font-weight: 700; color: #fff; margin-bottom: 10px; word-break: break-all;">' + (authState.user.username || '') + '</div>' +
                        '<div style="border-top: 1px solid var(--card-border); padding-top: 8px; display: flex; flex-direction: column; gap: 6px;">' +
                            '<button class="icon-btn" style="width: 100%; justify-content: center; color: #a5b4fc; background: rgba(99,102,241,0.15);" onclick="openMyPublishedModal()">📤 我的发布管理</button>' +
                            '<button class="icon-btn" style="width: 100%; justify-content: center; color: #fca5a5; background: rgba(239,68,68,0.15);" onclick="logoutUser()">🚪 退出登录</button>' +
                        '</div>' +
                    '</div>';
            } else {
                box.innerHTML = '<button class="btn-auth-nav" onclick="openAuthModal()">👤 登录 / 注册</button>';
            }
        }

        function toggleUserDropdown(event) {
            if (event) event.stopPropagation();
            var pop = document.getElementById('userDropdownPopover');
            if (pop) pop.classList.toggle('active');
        }

        window.addEventListener('click', function() {
            var pop = document.getElementById('userDropdownPopover');
            if (pop) pop.classList.remove('active');
        });

        function openAuthModal(callback, defaultTab) {
            authState.pendingCallback = typeof callback === 'function' ? callback : null;
            switchAuthTab(defaultTab === 1 ? 1 : 0);
            openModal('authModal');
            setTimeout(function() {
                var input = defaultTab === 1 ? document.getElementById('regUsername') : document.getElementById('loginUsername');
                if (input) input.focus();
            }, 100);
        }

        function switchAuthTab(tabIdx) {
            var isLogin = tabIdx === 0;
            document.getElementById('tabLoginBtn').className = isLogin ? 'auth-tab-btn active' : 'auth-tab-btn';
            document.getElementById('tabRegisterBtn').className = !isLogin ? 'auth-tab-btn active' : 'auth-tab-btn';
            document.getElementById('loginFormBox').style.display = isLogin ? 'block' : 'none';
            document.getElementById('registerFormBox').style.display = !isLogin ? 'block' : 'none';
            document.getElementById('authModalTitle').innerText = isLogin ? '账号密码登录' : '注册新账号';
            document.getElementById('loginErrorText').style.display = 'none';
            document.getElementById('registerErrorText').style.display = 'none';
        }

        function submitUserLogin() {
            var u = document.getElementById('loginUsername').value.trim();
            var p = document.getElementById('loginPassword').value;
            var errEl = document.getElementById('loginErrorText');
            errEl.style.display = 'none';

            if (!u || !p) {
                errEl.innerText = '请输入用户名和密码';
                errEl.style.display = 'block';
                return;
            }

            fetch('/api/mv/user/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username: u, password: p })
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (data.success && data.data && data.data.token) {
                    authState.token = data.data.token;
                    authState.user = data.data.user;
                    localStorage.setItem('user_token', authState.token);
                    localStorage.setItem('user_info', JSON.stringify(authState.user));
                    renderUserNav();
                    closeModal('authModal');
                    showToast('登录成功！欢迎，' + (authState.user.nickname || authState.user.username));

                    if (authState.pendingCallback) {
                        var cb = authState.pendingCallback;
                        authState.pendingCallback = null;
                        cb();
                    }
                } else {
                    errEl.innerText = data.message || '登录失败，请检查用户名和密码';
                    errEl.style.display = 'block';
                }
            })
            .catch(function(err) {
                errEl.innerText = '登录请求失败: ' + err.message;
                errEl.style.display = 'block';
            });
        }

        function submitUserRegister() {
            var u = document.getElementById('regUsername').value.trim();
            var p = document.getElementById('regPassword').value;
            var cp = document.getElementById('regConfirmPassword').value;
            var nick = document.getElementById('regNickname').value.trim();
            var errEl = document.getElementById('registerErrorText');
            errEl.style.display = 'none';

            if (!u || u.length < 3) {
                errEl.innerText = '用户名至少需要3个字符';
                errEl.style.display = 'block';
                return;
            }
            if (!p || p.length < 6) {
                errEl.innerText = '密码至少需要6个字符';
                errEl.style.display = 'block';
                return;
            }
            if (p !== cp) {
                errEl.innerText = '两次输入的密码不一致';
                errEl.style.display = 'block';
                return;
            }

            fetch('/api/mv/user/auth/register', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username: u, password: p, nickname: nick })
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (data.success && data.data && data.data.token) {
                    authState.token = data.data.token;
                    authState.user = data.data.user;
                    localStorage.setItem('user_token', authState.token);
                    localStorage.setItem('user_info', JSON.stringify(authState.user));
                    renderUserNav();
                    closeModal('authModal');
                    showToast('注册成功并已自动登录！');

                    if (authState.pendingCallback) {
                        var cb = authState.pendingCallback;
                        authState.pendingCallback = null;
                        cb();
                    }
                } else {
                    errEl.innerText = data.message || '注册失败';
                    errEl.style.display = 'block';
                }
            })
            .catch(function(err) {
                errEl.innerText = '注册请求异常: ' + err.message;
                errEl.style.display = 'block';
            });
        }

        function logoutUser(silent) {
            authState.token = '';
            authState.user = null;
            localStorage.removeItem('user_token');
            localStorage.removeItem('user_info');
            renderUserNav();
            if (!silent) {
                showToast('已退出登录');
            }
        }

        // ==========================================
        // 小爱音箱语音控制与联动管理逻辑
        // ==========================================
        var xiaoAiState = {
            config: null,
            devices: [],
            currentAuthTab: 'qr',
            qrLpUrl: '',
            qrPolling: false,
            keymaps: [],
            keymapPresets: [],
            reservedKeywords: []
        };

        function openXiaoAiSettingsModal() {
            openModal('xiaoaiModal');
            loadXiaoAiConfig();
        }

        function stopXiaoAiQrPoll() {
            xiaoAiState.qrPolling = false;
        }

        function logoutXiaoAi() {
            if (!confirm('确定退出当前小米账号并解除音箱授权吗？')) {
                return;
            }
            fetch('/api/xiaoai/logout', { method: 'POST' })
                .then(function(res) { return res.json(); })
                .then(function(data) {
                    if (data.success) {
                        showToast('已成功退出小米账号');
                        var sel = document.getElementById('xiaoaiDeviceSelect');
                        if (sel) {
                            sel.innerHTML = '<option value="">(请先登录小米账号以加载音箱列表)</option>';
                        }
                        loadXiaoAiConfig();
                    } else {
                        alert(data.error || '退出失败');
                    }
                })
                .catch(function(err) {
                    alert('网络异常: ' + err.message);
                });
        }

        function copyXiaoAiCookie() {
            showToast('正在提取米家 Cookie...');
            fetch('/api/xiaoai/cookie')
                .then(function(res) { return res.json(); })
                .then(function(data) {
                    if (!data.success || !data.cookie) {
                        alert(data.error || '获取 Cookie 失败，请确认是否已成功登录米家账号');
                        return;
                    }
                    var cookieStr = data.cookie;
                    var ta = document.getElementById('xiaoaiCookieTextarea');
                    if (ta) {
                        ta.value = cookieStr;
                    }
                    openModal('xiaoaiCookieModal');
                    setTimeout(function() {
                        if (ta) {
                            ta.focus();
                            ta.select();
                        }
                    }, 120);

                    // 优先尝试自动写入剪贴板
                    if (navigator.clipboard && navigator.clipboard.writeText) {
                        navigator.clipboard.writeText(cookieStr).then(function() {
                            showToast('✅ Cookie 已成功复制到剪贴板！');
                        }).catch(function() {
                            execXiaoAiCopyFallback(cookieStr);
                        });
                    } else {
                        execXiaoAiCopyFallback(cookieStr);
                    }
                })
                .catch(function(err) {
                    alert('网络请求异常: ' + err.message);
                });
        }

        function execXiaoAiCopyFallback(text) {
            try {
                var ta = document.createElement('textarea');
                ta.value = text;
                ta.style.position = 'fixed';
                ta.style.opacity = '0';
                document.body.appendChild(ta);
                ta.focus();
                ta.select();
                var ok = document.execCommand('copy');
                document.body.removeChild(ta);
                if (ok) {
                    showToast('✅ Cookie 已成功复制到剪贴板！');
                }
            } catch(e) {}
        }

        function doCopyXiaoAiCookieTextarea() {
            var ta = document.getElementById('xiaoaiCookieTextarea');
            if (!ta || !ta.value) return;
            ta.focus();
            ta.select();
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(ta.value).then(function() {
                    showToast('✅ Cookie 已复制到剪贴板！');
                }).catch(function() {
                    try {
                        document.execCommand('copy');
                        showToast('✅ Cookie 已复制到剪贴板！');
                    } catch(e) {
                        showToast('请手动全选文本框并按 Ctrl+C / Cmd+C 复制');
                    }
                });
            } else {
                try {
                    document.execCommand('copy');
                    showToast('✅ Cookie 已复制到剪贴板！');
                } catch(e) {
                    showToast('请手动全选文本框并按 Ctrl+C / Cmd+C 复制');
                }
            }
        }

        function onXiaoAiDeviceChange() {
            var sel = document.getElementById('xiaoaiDeviceSelect');
            var devEl = document.getElementById('xiaoaiLoggedInDevice');
            if (sel && devEl) {
                var selectedOpt = sel.options[sel.selectedIndex];
                if (selectedOpt && selectedOpt.value) {
                    var hw = selectedOpt.getAttribute('data-hw') || '';
                    var name = selectedOpt.getAttribute('data-name') || selectedOpt.text;
                    devEl.innerText = name + (hw ? ' (' + hw + ')' : '');
                } else {
                    devEl.innerText = '未指定音箱';
                }
            }
        }

        function loadXiaoAiConfig() {
            var badgeEl = document.getElementById('xiaoaiLoginBadge');
            var userTextEl = document.getElementById('xiaoaiCurrentUserText');
            var loggedInPanel = document.getElementById('xiaoaiAuthLoggedInPanel');
            var notLoggedInArea = document.getElementById('xiaoaiAuthNotLoggedInArea');
            var uidEl = document.getElementById('xiaoaiLoggedInUid');
            var devEl = document.getElementById('xiaoaiLoggedInDevice');

            if (badgeEl) badgeEl.innerText = '加载中...';

            fetch('/api/xiaoai/config')
                .then(function(res) { return res.json(); })
                .then(function(cfg) {
                    xiaoAiState.config = cfg;
                    var enabledEl = document.getElementById('xiaoaiCfgEnabled');
                    var prefixEl = document.getElementById('xiaoaiTriggerPrefix');
                    var webhookUrlEl = document.getElementById('xiaoaiWebhookUrl');
                    var webhookSecretEl = document.getElementById('xiaoaiWebhookSecret');
                    var webhookModeEl = document.getElementById('xiaoaiWebhookMode');
                    var webhookAllowRespEl = document.getElementById('xiaoaiWebhookAllowResponse');

                    if (enabledEl) enabledEl.checked = !!cfg.enabled;
                    if (prefixEl) prefixEl.value = cfg.trigger_prefix || '';
                    if (webhookUrlEl) webhookUrlEl.value = cfg.webhook_url || '';
                    if (webhookSecretEl) webhookSecretEl.value = cfg.webhook_secret || '';
                    if (webhookModeEl) webhookModeEl.value = cfg.webhook_mode || 'all';
                    if (webhookAllowRespEl) webhookAllowRespEl.checked = !!cfg.webhook_allow_response;

                    // 初始化自定义关键词映射
                    xiaoAiState.keymaps = Array.isArray(cfg.keymaps) ? cfg.keymaps : [];
                    renderXiaoAiKeymaps();
                    loadXiaoAiKeymapPresets();

                    if (cfg.is_logged_in) {
                        if (badgeEl) {
                            badgeEl.innerText = '● 已授权连接';
                            badgeEl.style.background = 'rgba(34,197,94,0.15)';
                            badgeEl.style.color = '#4ade80';
                        }
                        if (userTextEl) {
                            userTextEl.innerText = 'UID: ' + (cfg.user_id || '已登录');
                            userTextEl.style.color = '#4ade80';
                        }
                        if (loggedInPanel) loggedInPanel.style.display = 'block';
                        if (notLoggedInArea) notLoggedInArea.style.display = 'none';
                        if (uidEl) uidEl.innerText = 'UID: ' + (cfg.user_id || '-');
                        if (devEl) {
                            var devName = cfg.device_name || cfg.hardware || '未指定音箱';
                            if (cfg.hardware && cfg.device_name) {
                                devName += ' (' + cfg.hardware + ')';
                            }
                            devEl.innerText = devName;
                        }
                        stopXiaoAiQrPoll();
                        refreshXiaoAiDevices(cfg.device_id);
                    } else {
                        if (badgeEl) {
                            badgeEl.innerText = '○ 未登录';
                            badgeEl.style.background = 'rgba(148,163,184,0.15)';
                            badgeEl.style.color = '#94a3b8';
                        }
                        if (userTextEl) {
                            userTextEl.innerText = '未登录';
                            userTextEl.style.color = '#94a3b8';
                        }
                        if (loggedInPanel) loggedInPanel.style.display = 'none';
                        if (notLoggedInArea) notLoggedInArea.style.display = 'block';
                        if (xiaoAiState.currentAuthTab === 'qr') {
                            loadXiaoAiQrCode();
                        }
                    }
                })
                .catch(function(err) {
                    if (badgeEl) badgeEl.innerText = '配置加载失败';
                });
        }

        function switchXiaoAiAuthTab(tab) {
            xiaoAiState.currentAuthTab = tab;
            var tabQr = document.getElementById('btnXiaoAiTabQr');
            var tabCookie = document.getElementById('btnXiaoAiTabCookie');
            var tabPwd = document.getElementById('btnXiaoAiTabPwd');
            var panelQr = document.getElementById('xiaoaiAuthQrPanel');
            var panelCookie = document.getElementById('xiaoaiAuthCookiePanel');
            var panelPwd = document.getElementById('xiaoaiAuthPwdPanel');

            if (tab === 'qr') {
                if (tabQr) tabQr.className = 'btn btn-sm';
                if (tabPwd) tabPwd.className = 'btn btn-secondary btn-sm';
                if (tabCookie) tabCookie.className = 'btn btn-secondary btn-sm';
                if (panelQr) panelQr.style.display = 'flex';
                if (panelPwd) panelPwd.style.display = 'none';
                if (panelCookie) panelCookie.style.display = 'none';
                loadXiaoAiQrCode();
            } else if (tab === 'pwd') {
                stopXiaoAiQrPoll();
                if (tabQr) tabQr.className = 'btn btn-secondary btn-sm';
                if (tabPwd) tabPwd.className = 'btn btn-sm';
                if (tabCookie) tabCookie.className = 'btn btn-secondary btn-sm';
                if (panelQr) panelQr.style.display = 'none';
                if (panelPwd) panelPwd.style.display = 'block';
                if (panelCookie) panelCookie.style.display = 'none';
            } else {
                stopXiaoAiQrPoll();
                if (tabQr) tabQr.className = 'btn btn-secondary btn-sm';
                if (tabPwd) tabPwd.className = 'btn btn-secondary btn-sm';
                if (tabCookie) tabCookie.className = 'btn btn-sm';
                if (panelQr) panelQr.style.display = 'none';
                if (panelPwd) panelPwd.style.display = 'none';
                if (panelCookie) panelCookie.style.display = 'block';
            }
        }

        function loadXiaoAiQrCode(force) {
            var imgEl = document.getElementById('xiaoaiQrImg');
            var loadingEl = document.getElementById('xiaoaiQrLoading');
            var tipEl = document.getElementById('xiaoaiQrTip');

            if (!force && xiaoAiState.qrPolling && xiaoAiState.qrLpUrl) {
                return;
            }

            stopXiaoAiQrPoll();
            if (imgEl) imgEl.style.display = 'none';
            if (loadingEl) {
                loadingEl.style.display = 'flex';
                loadingEl.innerHTML = '<span style="font-size: 20px;">⏳</span><span>正在生成官方二维码...</span>';
            }
            if (tipEl) tipEl.innerHTML = '<span>📱 请使用【米家 App】扫码授权登录</span>';

            fetch('/api/xiaoai/qr/get')
                .then(function(res) { return res.json(); })
                .then(function(data) {
                    if (data.success && data.qr_url && data.lp_url) {
                        xiaoAiState.qrLpUrl = data.lp_url;
                        if (imgEl) {
                            imgEl.src = data.qr_url;
                            imgEl.onload = function() {
                                imgEl.style.display = 'block';
                                if (loadingEl) loadingEl.style.display = 'none';
                            };
                        }
                        startXiaoAiQrPoll(data.lp_url);
                    } else {
                        if (loadingEl) {
                            loadingEl.innerHTML = '<span style="font-size: 18px; color: #ef4444;">❌</span><span style="color:#ef4444;">生成失败，点击重试</span>';
                        }
                    }
                })
                .catch(function(err) {
                    if (loadingEl) {
                        loadingEl.innerHTML = '<span style="font-size: 18px; color: #ef4444;">❌</span><span style="color:#ef4444;">网络异常，点击重试</span>';
                    }
                });
        }

        function startXiaoAiQrPoll(lpUrl) {
            xiaoAiState.qrPolling = true;
            pollNext();

            function pollNext() {
                if (!xiaoAiState.qrPolling || xiaoAiState.currentAuthTab !== 'qr') return;
                var modal = document.getElementById('xiaoaiModal');
                if (modal && modal.style.display === 'none') {
                    stopXiaoAiQrPoll();
                    return;
                }

                fetch('/api/xiaoai/qr/status?lp=' + encodeURIComponent(lpUrl))
                    .then(function(res) { return res.json(); })
                    .then(function(res) {
                        if (!xiaoAiState.qrPolling) return;
                        if (res.status === 'success') {
                            stopXiaoAiQrPoll();
                            var tipEl = document.getElementById('xiaoaiQrTip');
                            if (tipEl) tipEl.innerHTML = '<span style="color: #4ade80; font-weight: 700;">✅ 扫码成功，已自动绑定！</span>';
                            showToast('米家扫码登录成功！已自动加载音箱设备');
                            loadXiaoAiConfig();
                        } else if (res.status === 'error') {
                            stopXiaoAiQrPoll();
                            var tipEl = document.getElementById('xiaoaiQrTip');
                            if (tipEl) tipEl.innerHTML = '<span style="color: #ef4444;">❌ ' + (res.message || '扫码失败') + '</span>';
                        } else {
                            setTimeout(pollNext, 1200);
                        }
                    })
                    .catch(function() {
                        if (xiaoAiState.qrPolling) {
                            setTimeout(pollNext, 2000);
                        }
                    });
            }
        }

        function submitXiaoAiCookieLogin() {
            var input = document.getElementById('xiaoaiCookieInput');
            var cookieStr = input ? input.value.trim() : '';
            if (!cookieStr) {
                showToast('请先粘贴完整的 Cookie 字符串');
                return;
            }

            showToast('正在验证并保存 Cookie...');
            fetch('/api/xiaoai/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ cookie: cookieStr })
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (data.success) {
                    showToast('Cookie 凭证绑定成功！已检测到音箱设备');
                    if (input) input.value = '';
                    loadXiaoAiConfig();
                } else {
                    alert(data.error || 'Cookie 验证失败，请确认包含 userId 与 serviceToken');
                }
            })
            .catch(function(err) {
                alert('登录请求异常: ' + err.message);
            });
        }

        function submitXiaoAiPwdLogin() {
            var uEl = document.getElementById('xiaoaiUsernameInput');
            var pEl = document.getElementById('xiaoaiPasswordInput');
            var u = uEl ? uEl.value.trim() : '';
            var p = pEl ? pEl.value.trim() : '';
            if (!u || !p) {
                showToast('请输入小米账号和密码');
                return;
            }

            showToast('正在向小米云端换取凭据...');
            fetch('/api/xiaoai/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username: u, password: p })
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (data.success) {
                    showToast('小米账号登录成功！');
                    if (pEl) pEl.value = '';
                    loadXiaoAiConfig();
                } else {
                    alert(data.error || '登录失败，请尝试上方【粘贴 Cookie】模式');
                }
            })
            .catch(function(err) {
                alert('登录请求异常: ' + err.message);
            });
        }

        function refreshXiaoAiDevices(selectedDid) {
            var sel = document.getElementById('xiaoaiDeviceSelect');
            if (!sel) return;
            sel.innerHTML = '<option value="">正在拉取音箱设备...</option>';

            fetch('/api/xiaoai/devices')
                .then(function(res) { return res.json(); })
                .then(function(data) {
                    if (!data.success) {
                        sel.innerHTML = '<option value="">' + escapeHtml(data.error || data.message || '拉取设备失败') + '</option>';
                        return;
                    }
                    var devs = data.devices || [];
                    xiaoAiState.devices = devs;
                    if (devs.length === 0) {
                        sel.innerHTML = '<option value="">名下未发现小爱音箱设备</option>';
                        return;
                    }
                    var html = '';
                    devs.forEach(function(d) {
                        var name = d.alias || d.name || ('小爱音箱 (' + d.hardware + ')');
                        var isSel = (selectedDid && d.deviceID === selectedDid) || (xiaoAiState.config && d.deviceID === xiaoAiState.config.device_id);
                        html += '<option value="' + escapeAttr(d.deviceID) + '" data-hw="' + escapeAttr(d.hardware) + '" data-name="' + escapeAttr(name) + '"' + (isSel ? ' selected' : '') + '>' +
                                escapeHtml(name) + ' [' + escapeHtml(d.hardware) + ']' +
                                '</option>';
                    });
                    sel.innerHTML = html;
                    onXiaoAiDeviceChange();
                })
                .catch(function(err) {
                    sel.innerHTML = '<option value="">网络异常: ' + escapeHtml(err.message || '检查服务连接') + '</option>';
                });
        }

        function saveXiaoAiConfig() {
            var enabledEl = document.getElementById('xiaoaiCfgEnabled');
            var prefixEl = document.getElementById('xiaoaiTriggerPrefix');
            var sel = document.getElementById('xiaoaiDeviceSelect');

            var enabled = enabledEl ? enabledEl.checked : false;
            var prefix = prefixEl ? prefixEl.value.trim() : '';

            var deviceId = '';
            var deviceName = '';
            var hardware = '';

            if (sel && sel.selectedIndex >= 0 && sel.options[sel.selectedIndex]) {
                var opt = sel.options[sel.selectedIndex];
                deviceId = opt.value || '';
                hardware = opt.getAttribute('data-hw') || '';
                deviceName = opt.getAttribute('data-name') || '';
            }

            var webhookUrlEl = document.getElementById('xiaoaiWebhookUrl');
            var webhookSecretEl = document.getElementById('xiaoaiWebhookSecret');
            var webhookModeEl = document.getElementById('xiaoaiWebhookMode');
            var webhookAllowRespEl = document.getElementById('xiaoaiWebhookAllowResponse');

            var webhookUrl = webhookUrlEl ? webhookUrlEl.value.trim() : '';
            var webhookSecret = webhookSecretEl ? webhookSecretEl.value.trim() : '';
            var webhookMode = webhookModeEl ? webhookModeEl.value : 'all';
            var webhookAllowResponse = webhookAllowRespEl ? webhookAllowRespEl.checked : false;

            var payload = {
                enabled: enabled,
                trigger_prefix: prefix,
                device_id: deviceId,
                device_name: deviceName,
                hardware: hardware,
                webhook_url: webhookUrl,
                webhook_secret: webhookSecret,
                webhook_mode: webhookMode,
                webhook_allow_response: webhookAllowResponse,
                keymaps: xiaoAiState.keymaps || []
            };

            fetch('/api/xiaoai/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (data.success) {
                    showToast('小爱音箱联动配置已保存并生效！');
                    closeModal('xiaoaiModal');
                } else {
                    alert(data.error || '保存失败');
                }
            })
            .catch(function(err) {
                alert('保存配置异常: ' + err.message);
            });
        }

        function testXiaoAiWebhook() {
            var urlEl = document.getElementById('xiaoaiWebhookUrl');
            var secretEl = document.getElementById('xiaoaiWebhookSecret');
            var resEl = document.getElementById('xiaoaiWebhookTestResult');
            var url = urlEl ? urlEl.value.trim() : '';
            var secret = secretEl ? secretEl.value.trim() : '';

            if (!url) {
                showToast('请先输入 Webhook 目标地址');
                return;
            }

            if (resEl) {
                resEl.style.color = '#38bdf8';
                resEl.innerText = '正在向 Webhook 发送测试请求...';
            }

            fetch('/api/xiaoai/webhook/test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    webhook_url: url,
                    webhook_secret: secret,
                    query: '这是一条聚酷 Webhook 测试语音问话'
                })
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (data.success) {
                    var r = data.result || {};
                    var cost = r.cost_ms !== undefined ? r.cost_ms + 'ms' : '';
                    if (resEl) {
                        resEl.style.color = '#4ade80';
                        resEl.innerText = '✅ 发送成功 (HTTP ' + r.status_code + ', ' + cost + ')：' + (r.raw_body ? r.raw_body.slice(0, 100) : 'OK');
                    }
                    showToast('Webhook 测试响应成功！');
                } else {
                    var errText = data.error || (data.result && data.result.error) || '请求失败';
                    if (resEl) {
                        resEl.style.color = '#ef4444';
                        resEl.innerText = '❌ 发送失败：' + errText;
                    }
                }
            })
            .catch(function(err) {
                if (resEl) {
                    resEl.style.color = '#ef4444';
                    resEl.innerText = '❌ 请求异常：' + err.message;
                }
            });
        }

        function testXiaoAiTTS() {
            var sel = document.getElementById('xiaoaiDeviceSelect');
            var devId = sel ? sel.value : '';
            if (!devId) {
                showToast('请先选择目标小爱音箱');
                return;
            }

            showToast('正在发送测试语音播报...');
            fetch('/api/xiaoai/test_tts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ device_id: devId, text: '聚酷影视语音控制已就绪，随时为您播片！' })
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (data.success) {
                    showToast('音箱发声指令已下发！请留意小爱音箱朗读');
                } else {
                    alert(data.error || '发声测试失败');
                }
            })
            .catch(function(err) {
                alert('发声测试异常: ' + err.message);
            });
        }

        function runXiaoAiTestPlay() {
            var input = document.getElementById('xiaoaiTestQueryInput');
            var resBox = document.getElementById('xiaoaiTestPlayResult');
            var q = input ? input.value.trim() : '';
            if (!q) {
                showToast('请输入测试语音指令');
                return;
            }

            if (resBox) {
                resBox.innerHTML = '<span style="color: #38bdf8;">正在模拟意图解析与三级调度起播...</span>';
            }

            fetch('/api/xiaoai/test_play', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query: q })
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (!resBox) return;
                if (data.success) {
                    if (data.type === 'keymap') {
                        resBox.innerHTML = '<span style="color: #f472b6; font-weight: 500;">🎯 命中自定义关键词映射【' + escapeHtml(data.name) + '】: 执行 Kodi 指令 <code style="color:#38bdf8;">' + escapeHtml(data.cmd) + '</code>' + (data.tts ? '，反馈语音: 《' + escapeHtml(data.tts) + '》' : '') + '</span>';
                    } else if (data.type === 'control') {
                        resBox.innerHTML = '<span style="color: #4ade80;">🟢 成功识别为播控指令: ' + escapeHtml(data.cmd) + ' (已同步向 Kodi 发送)</span>';
                    } else {
                        resBox.innerHTML = '<span style="color: #4ade80;">🟢 成功识别影视点播: 《' + escapeHtml(data.clean_title) + '》 (第' + data.target_season + '季 第' + data.target_episode + '集)，三级检索与起播调度已在后台启动！</span>';
                    }
                } else {
                    resBox.innerHTML = '<span style="color: #f87171;">⚠️ ' + escapeHtml(data.error || '未识别到有效指令') + '</span>';
                }
            })
            .catch(function(err) {
                if (resBox) resBox.innerHTML = '<span style="color: #f87171;">模拟异常: ' + escapeHtml(err.message) + '</span>';
            });
        }

        // ==========================================
        // 小爱音箱自定义关键词映射 (Keymap Editor) 前端逻辑
        // ==========================================
        function loadXiaoAiKeymapPresets() {
            if (xiaoAiState.keymapCategories && xiaoAiState.keymapCategories.length > 0) return;
            fetch('/api/xiaoai/keymaps/presets')
                .then(function(res) { return res.json(); })
                .then(function(data) {
                    if (data.success) {
                        xiaoAiState.keymapCategories = data.categories || [];
                        xiaoAiState.keymapPresets = data.presets || [];
                        xiaoAiState.reservedKeywords = data.reserved || [];
                        populateXiaoAiCategorySelect();
                    }
                })
                .catch(function(err) {
                    console.error('[XiaoAi] 加载预设动作失败:', err);
                });
        }

        function populateXiaoAiCategorySelect(selectedCat, selectedAct) {
            var catSel = document.getElementById('xiaoaiKmCategorySelect');
            if (!catSel) return;
            catSel.innerHTML = '';

            var cats = xiaoAiState.keymapCategories || [];
            cats.forEach(function(cat) {
                var opt = document.createElement('option');
                opt.value = cat.category;
                opt.innerText = cat.name + ' (' + (cat.actions ? cat.actions.length : 0) + ')';
                catSel.appendChild(opt);
            });

            if (selectedCat) {
                catSel.value = selectedCat;
            } else if (catSel.options.length > 0) {
                catSel.selectedIndex = 0;
            }

            populateXiaoAiPresetSelect(selectedAct);
        }

        function onXiaoAiKeymapCategoryChange() {
            populateXiaoAiPresetSelect();
            onXiaoAiKeymapPresetChange();
        }

        function refreshKodiAddonsList(manual) {
            var btn = document.getElementById('xiaoaiKmRefreshAddonsBtn');
            if (btn) btn.innerText = '⏳ 加载中...';
            fetch('/api/kodi/addons')
                .then(function(res) { return res.json(); })
                .then(function(data) {
                    if (btn) btn.innerText = '🔄 刷新插件';
                    if (data && data.addons && data.addons.length > 0) {
                        xiaoAiState.kodiAddons = data.addons;
                        if (manual) showToast('已从电视成功加载 ' + data.addons.length + ' 个已安装插件');
                    } else if (manual) {
                        showToast(data.error || '未获取到插件，已提供默认插件');
                    }
                    var catSel = document.getElementById('xiaoaiKmCategorySelect');
                    if (catSel && catSel.value === 'addon') {
                        populateXiaoAiPresetSelect();
                        onXiaoAiKeymapPresetChange();
                    }
                })
                .catch(function(err) {
                    if (btn) btn.innerText = '🔄 刷新插件';
                    if (manual) showToast('获取插件异常: ' + err.message);
                });
        }

        function populateXiaoAiPresetSelect(selectedAct) {
            var catSel = document.getElementById('xiaoaiKmCategorySelect');
            var actSel = document.getElementById('xiaoaiKmPresetSelect');
            if (!actSel) return;
            actSel.innerHTML = '';

            var curCatVal = catSel ? catSel.value : 'common';
            var refreshBtn = document.getElementById('xiaoaiKmRefreshAddonsBtn');
            if (refreshBtn) {
                refreshBtn.style.display = (curCatVal === 'addon') ? 'inline' : 'none';
            }

            if (curCatVal === 'addon') {
                // 运行插件分类：优先从 Kodi 动态加载的插件列表构建
                var addons = xiaoAiState.kodiAddons || [];
                if (addons.length === 0) {
                    refreshKodiAddonsList(false);
                    // 默认放入巨库本身
                    addons = [
                        { addonid: 'plugin.video.juku', name: '巨库' }
                    ];
                }

                addons.forEach(function(item) {
                    var opt = document.createElement('option');
                    var cmd = 'RunAddon(' + item.addonid + ')';
                    opt.value = 'run_' + item.addonid;
                    opt.innerText = item.name + ' (' + item.addonid + ')';
                    opt.setAttribute('data-cmd', cmd);
                    opt.setAttribute('data-tts', '正在为您打开' + item.name);
                    opt.setAttribute('data-name', '打开' + item.name);
                    actSel.appendChild(opt);
                });

                // 增加手填插件 ID 选项
                var customOpt = document.createElement('option');
                customOpt.value = 'run_custom_addon';
                customOpt.innerText = '✏️ 手动输入插件 ID (如 RunAddon(xxx))';
                customOpt.setAttribute('data-cmd', 'RunAddon()');
                customOpt.setAttribute('data-tts', '正在为您打开插件');
                customOpt.setAttribute('data-name', '运行插件');
                actSel.appendChild(customOpt);

                if (selectedAct) {
                    actSel.value = selectedAct;
                } else if (actSel.options.length > 0) {
                    actSel.selectedIndex = 0;
                }
                return;
            }

            var targetCat = null;
            (xiaoAiState.keymapCategories || []).forEach(function(c) {
                if (c.category === curCatVal) targetCat = c;
            });

            var actions = (targetCat && targetCat.actions) ? targetCat.actions : (xiaoAiState.keymapPresets || []);
            actions.forEach(function(item) {
                var opt = document.createElement('option');
                opt.value = item.action;
                opt.innerText = item.name + (item.kodi_cmd ? ' (' + item.kodi_cmd + ')' : '');
                opt.setAttribute('data-cmd', item.kodi_cmd || '');
                opt.setAttribute('data-tts', item.default_tts || '');
                opt.setAttribute('data-name', item.name || '');
                actSel.appendChild(opt);
            });

            if (selectedAct) {
                actSel.value = selectedAct;
            } else if (actSel.options.length > 0) {
                actSel.selectedIndex = 0;
            }
        }

        function renderXiaoAiKeymaps() {
            var listEl = document.getElementById('xiaoaiKeymapList');
            var emptyTip = document.getElementById('xiaoaiKeymapEmptyTip');
            if (!listEl) return;
            listEl.innerHTML = '';

            var items = xiaoAiState.keymaps || [];
            if (items.length === 0) {
                if (emptyTip) emptyTip.style.display = 'block';
                return;
            }
            if (emptyTip) emptyTip.style.display = 'none';

            items.forEach(function(item) {
                var card = document.createElement('div');
                card.style.cssText = 'background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); border-radius: 6px; padding: 10px 12px; display: flex; align-items: center; justify-content: space-between; gap: 10px; transition: all 0.2s;';
                card.onmouseenter = function() { card.style.background = 'rgba(255,255,255,0.07)'; };
                card.onmouseleave = function() { card.style.background = 'rgba(255,255,255,0.04)'; };

                var leftDiv = document.createElement('div');
                leftDiv.style.cssText = 'display: flex; flex-direction: column; gap: 4px; flex: 1; min-width: 0;';

                var titleRow = document.createElement('div');
                titleRow.style.cssText = 'display: flex; align-items: center; gap: 8px; flex-wrap: wrap;';

                var nameSpan = document.createElement('span');
                nameSpan.style.cssText = 'font-size: 13px; font-weight: 600; color: #f1f5f9;';
                nameSpan.innerText = item.name || '未命名规则';

                var cmdBadge = document.createElement('span');
                cmdBadge.style.cssText = 'font-size: 11px; padding: 1px 6px; border-radius: 4px; background: rgba(56,189,248,0.15); color: #38bdf8; font-family: monospace;';
                cmdBadge.innerText = item.kodi_cmd || '无指令';

                titleRow.appendChild(nameSpan);
                titleRow.appendChild(cmdBadge);

                if (item.tts) {
                    var ttsBadge = document.createElement('span');
                    ttsBadge.style.cssText = 'font-size: 11px; padding: 1px 6px; border-radius: 4px; background: rgba(52,211,153,0.15); color: #34d399;';
                    ttsBadge.innerText = '🔊 ' + item.tts;
                    titleRow.appendChild(ttsBadge);
                }

                var kwRow = document.createElement('div');
                kwRow.style.cssText = 'display: flex; gap: 6px; flex-wrap: wrap; align-items: center; margin-top: 2px;';

                var kwLabel = document.createElement('span');
                kwLabel.style.cssText = 'font-size: 11px; color: #94a3b8;';
                kwLabel.innerText = '触发口令:';
                kwRow.appendChild(kwLabel);

                (item.keywords || []).forEach(function(kw) {
                    var b = document.createElement('span');
                    b.style.cssText = 'font-size: 11px; padding: 1px 7px; border-radius: 10px; background: rgba(244,114,182,0.18); color: #f472b6; font-weight: 500; border: 1px solid rgba(244,114,182,0.3);';
                    b.innerText = kw;
                    kwRow.appendChild(b);
                });

                leftDiv.appendChild(titleRow);
                leftDiv.appendChild(kwRow);

                var rightDiv = document.createElement('div');
                rightDiv.style.cssText = 'display: flex; align-items: center; gap: 8px; flex-shrink: 0;';

                var enableLabel = document.createElement('label');
                enableLabel.style.cssText = 'display: flex; align-items: center; gap: 4px; font-size: 11px; color: #cbd5e1; cursor: pointer; user-select: none; margin-right: 4px;';
                var chk = document.createElement('input');
                chk.type = 'checkbox';
                chk.checked = !!item.enabled;
                chk.style.cssText = 'width: 14px; height: 14px; cursor: pointer;';
                chk.onchange = function() {
                    item.enabled = chk.checked;
                };
                var chkText = document.createElement('span');
                chkText.innerText = item.enabled ? '启用' : '禁用';
                chk.addEventListener('change', function() {
                    chkText.innerText = chk.checked ? '启用' : '禁用';
                });
                enableLabel.appendChild(chk);
                enableLabel.appendChild(chkText);

                var btnEdit = document.createElement('button');
                btnEdit.type = 'button';
                btnEdit.className = 'btn btn-secondary btn-sm';
                btnEdit.style.cssText = 'padding: 2px 8px; font-size: 11px;';
                btnEdit.innerText = '✏️ 编辑';
                btnEdit.onclick = function() {
                    openXiaoAiKeymapEditor(item.id);
                };

                var btnDel = document.createElement('button');
                btnDel.type = 'button';
                btnDel.className = 'btn btn-secondary btn-sm';
                btnDel.style.cssText = 'padding: 2px 8px; font-size: 11px; color: #f87171;';
                btnDel.innerText = '🗑️';
                btnDel.title = '删除此规则';
                btnDel.onclick = function() {
                    if (confirm('确定要删除映射规则【' + (item.name || '') + '】吗？')) {
                        deleteXiaoAiKeymapItem(item.id);
                    }
                };

                rightDiv.appendChild(enableLabel);
                rightDiv.appendChild(btnEdit);
                rightDiv.appendChild(btnDel);

                card.appendChild(leftDiv);
                card.appendChild(rightDiv);
                listEl.appendChild(card);
            });
        }

        function openXiaoAiKeymapEditor(ruleId) {
            var panel = document.getElementById('xiaoaiKeymapFormPanel');
            var titleEl = document.getElementById('xiaoaiKeymapFormTitle');
            var editIdEl = document.getElementById('xiaoaiKmEditId');
            var nameEl = document.getElementById('xiaoaiKmName');
            var cmdEl = document.getElementById('xiaoaiKmCmd');
            var ttsEl = document.getElementById('xiaoaiKmTTS');
            var kwEl = document.getElementById('xiaoaiKmKeywords');
            var msgEl = document.getElementById('xiaoaiKmValidateMsg');
            var btnSave = document.getElementById('btnXiaoAiKmSave');

            if (!panel) return;
            if (msgEl) msgEl.innerHTML = '';
            if (btnSave) btnSave.disabled = false;

            if (ruleId) {
                // 编辑模式
                var found = null;
                (xiaoAiState.keymaps || []).forEach(function(r) {
                    if (r.id === ruleId) found = r;
                });
                if (found) {
                    if (titleEl) titleEl.innerText = '✏️ 编辑语音映射规则';
                    if (editIdEl) editIdEl.value = found.id;
                    if (nameEl) nameEl.value = found.name || '';
                    if (cmdEl) cmdEl.value = found.kodi_cmd || '';
                    if (ttsEl) ttsEl.value = found.tts || '';
                    if (kwEl) kwEl.value = (found.keywords || []).join(', ');

                    // 反查该 action 属于哪个 category
                    var foundCat = 'common';
                    if ((found.kodi_cmd || '').indexOf('RunAddon') === 0 || (found.action || '').indexOf('run_') === 0) {
                        foundCat = 'addon';
                    } else {
                        (xiaoAiState.keymapCategories || []).forEach(function(c) {
                            (c.actions || []).forEach(function(a) {
                                if (a.action === found.action || (found.action === 'custom' && c.category === 'custom')) {
                                    foundCat = c.category;
                                }
                            });
                        });
                    }
                    populateXiaoAiCategorySelect(foundCat, found.action);
                }
            } else {
                // 新增模式
                if (titleEl) titleEl.innerText = '➕ 添加语音映射规则';
                if (editIdEl) editIdEl.value = '';
                if (nameEl) nameEl.value = '';
                if (kwEl) kwEl.value = '';
                populateXiaoAiCategorySelect('common', '');
                onXiaoAiKeymapPresetChange();
            }

            panel.style.display = 'block';
            panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            if (kwEl && kwEl.value) {
                onXiaoAiKeymapKeywordsInput();
            }
        }

        function closeXiaoAiKeymapEditor() {
            var panel = document.getElementById('xiaoaiKeymapFormPanel');
            if (panel) panel.style.display = 'none';
        }

        function onXiaoAiKeymapPresetChange() {
            var sel = document.getElementById('xiaoaiKmPresetSelect');
            var nameEl = document.getElementById('xiaoaiKmName');
            var cmdEl = document.getElementById('xiaoaiKmCmd');
            var ttsEl = document.getElementById('xiaoaiKmTTS');
            if (!sel || sel.selectedIndex < 0) return;

            var opt = sel.options[sel.selectedIndex];
            var cmd = opt.getAttribute('data-cmd') || '';
            var tts = opt.getAttribute('data-tts') || '';
            var defName = opt.getAttribute('data-name') || '';

            if (cmdEl) cmdEl.value = cmd;
            if (ttsEl) ttsEl.value = tts;
            if (nameEl && (!nameEl.value.trim() || nameEl.value === '未命名规则')) {
                nameEl.value = defName;
            }

            var kwEl = document.getElementById('xiaoaiKmKeywords');
            if (kwEl && !kwEl.value.trim()) {
                var actVal = sel.value || '';
                if (actVal === 'shutdown') {
                    kwEl.value = '关机, 关闭电视';
                    onXiaoAiKeymapKeywordsInput();
                } else if (actVal === 'reboot') {
                    kwEl.value = '重启, 重启电视';
                    onXiaoAiKeymapKeywordsInput();
                } else if (actVal === 'playerprocessinfo') {
                    kwEl.value = '播放信息, 码率信息';
                    onXiaoAiKeymapKeywordsInput();
                } else if (actVal === 'audionextlanguage' || actVal === 'next_audio') {
                    kwEl.value = '换音轨, 切换音轨';
                    onXiaoAiKeymapKeywordsInput();
                } else if (actVal === 'next_subtitle') {
                    kwEl.value = '换字幕, 切换字幕';
                    onXiaoAiKeymapKeywordsInput();
                } else if (actVal === 'shutdownmenu') {
                    kwEl.value = '关机菜单';
                    onXiaoAiKeymapKeywordsInput();
                }
            }
        }

        function validateXiaoAiKeywordClient(kw, existingKeywords) {
            kw = (kw || '').trim().toLowerCase().replace(/[。！？，,!.?~ 《》"'“”‘’]/g, '');
            if (kw.length < 2) {
                return '关键词【' + kw + '】过短，至少需2个字符';
            }

            var reserved = xiaoAiState.reservedKeywords || [];
            for (var i = 0; i < reserved.length; i++) {
                var sys = (reserved[i] || '').trim().toLowerCase().replace(/[。！？，,!.?~ 《》"'“”‘’]/g, '');
                if (!sys) continue;
                if (kw === sys) {
                    return '关键词【' + kw + '】与系统内置保留词【' + reserved[i] + '】完全相同，请更换其他口令';
                }
            }

            for (var j = 0; j < existingKeywords.length; j++) {
                var exist = (existingKeywords[j] || '').trim().toLowerCase().replace(/[。！？，,!.?~ 《》"'“”‘’]/g, '');
                if (!exist) continue;
                if (kw === exist) {
                    return '关键词【' + kw + '】已被其他规则使用，不可重复添加';
                }
            }

            return null;
        }

        function onXiaoAiKeymapKeywordsInput() {
            var kwInput = document.getElementById('xiaoaiKmKeywords');
            var msgEl = document.getElementById('xiaoaiKmValidateMsg');
            var btnSave = document.getElementById('btnXiaoAiKmSave');
            if (!kwInput || !msgEl) return;

            var raw = kwInput.value.trim();
            if (!raw) {
                msgEl.innerHTML = '<span style="color: #94a3b8;">请输入触发关键词（如：切换配音, 换个声音）</span>';
                if (btnSave) btnSave.disabled = false;
                return;
            }

            var parts = raw.split(/[,，\s\n]+/).filter(function(s) { return s.trim().length > 0; });
            var editId = (document.getElementById('xiaoaiKmEditId') || {}).value || '';

            var otherKeywords = [];
            (xiaoAiState.keymaps || []).forEach(function(r) {
                if (r.id !== editId) {
                    (r.keywords || []).forEach(function(k) { otherKeywords.push(k); });
                }
            });

            var checkedInThisBatch = [];
            for (var i = 0; i < parts.length; i++) {
                var p = parts[i].trim();
                var err = validateXiaoAiKeywordClient(p, otherKeywords.concat(checkedInThisBatch));
                if (err) {
                    msgEl.innerHTML = '<span style="color: #f87171; font-weight: 500;">❌ ' + escapeHtml(err) + '</span>';
                    if (btnSave) btnSave.disabled = true;
                    return;
                }
                checkedInThisBatch.push(p);
            }

            msgEl.innerHTML = '<span style="color: #4ade80;">✔ 关键词有效且无冲突 (' + parts.length + '个口令，完全匹配)</span>';
            if (btnSave) btnSave.disabled = false;
        }

        function saveXiaoAiKeymapItem() {
            var editIdEl = document.getElementById('xiaoaiKmEditId');
            var nameEl = document.getElementById('xiaoaiKmName');
            var presetSel = document.getElementById('xiaoaiKmPresetSelect');
            var cmdEl = document.getElementById('xiaoaiKmCmd');
            var ttsEl = document.getElementById('xiaoaiKmTTS');
            var kwEl = document.getElementById('xiaoaiKmKeywords');

            var name = nameEl ? nameEl.value.trim() : '';
            var cmd = cmdEl ? cmdEl.value.trim() : '';
            var tts = ttsEl ? ttsEl.value.trim() : '';
            var action = presetSel ? presetSel.value : 'custom';
            var rawKw = kwEl ? kwEl.value.trim() : '';
            var editId = editIdEl ? editIdEl.value.trim() : '';

            if (!name) {
                alert('请输入规则名称');
                return;
            }
            if (!cmd) {
                alert('请输入 Kodi 内置执行命令');
                return;
            }
            if (!rawKw) {
                alert('请至少输入 1 个触发关键词');
                return;
            }

            var parts = rawKw.split(/[,，\s\n]+/).filter(function(s) { return s.trim().length > 0; });
            if (parts.length === 0) {
                alert('请至少输入 1 个有效触发关键词');
                return;
            }

            var otherKeywords = [];
            (xiaoAiState.keymaps || []).forEach(function(r) {
                if (r.id !== editId) {
                    (r.keywords || []).forEach(function(k) { otherKeywords.push(k); });
                }
            });

            var checkedInThisBatch = [];
            for (var i = 0; i < parts.length; i++) {
                var p = parts[i].trim();
                var err = validateXiaoAiKeywordClient(p, otherKeywords.concat(checkedInThisBatch));
                if (err) {
                    alert('关键词校验失败:\n' + err);
                    return;
                }
                checkedInThisBatch.push(p);
            }

            if (!editId) {
                // 新增
                var newId = 'km_' + Date.now();
                xiaoAiState.keymaps.push({
                    id: newId,
                    name: name,
                    action: action,
                    kodi_cmd: cmd,
                    tts: tts,
                    keywords: checkedInThisBatch,
                    enabled: true
                });
            } else {
                // 更新
                var found = false;
                for (var j = 0; j < xiaoAiState.keymaps.length; j++) {
                    if (xiaoAiState.keymaps[j].id === editId) {
                        xiaoAiState.keymaps[j].name = name;
                        xiaoAiState.keymaps[j].action = action;
                        xiaoAiState.keymaps[j].kodi_cmd = cmd;
                        xiaoAiState.keymaps[j].tts = tts;
                        xiaoAiState.keymaps[j].keywords = checkedInThisBatch;
                        found = true;
                        break;
                    }
                }
                if (!found) {
                    xiaoAiState.keymaps.push({
                        id: editId,
                        name: name,
                        action: action,
                        kodi_cmd: cmd,
                        tts: tts,
                        keywords: checkedInThisBatch,
                        enabled: true
                    });
                }
            }

            closeXiaoAiKeymapEditor();
            renderXiaoAiKeymaps();
            showToast('规则已更新，请点击底部【保存并应用配置】完成最终保存');
        }

        function deleteXiaoAiKeymapItem(ruleId) {
            if (!ruleId) return;
            xiaoAiState.keymaps = (xiaoAiState.keymaps || []).filter(function(r) {
                return r.id !== ruleId;
            });
            renderXiaoAiKeymaps();
            showToast('规则已移除，请点击底部【保存并应用配置】生效');
        }

        window.openXiaoAiKeymapEditor = openXiaoAiKeymapEditor;
        window.closeXiaoAiKeymapEditor = closeXiaoAiKeymapEditor;
        window.saveXiaoAiKeymapItem = saveXiaoAiKeymapItem;
        window.deleteXiaoAiKeymapItem = deleteXiaoAiKeymapItem;
        window.onXiaoAiKeymapCategoryChange = onXiaoAiKeymapCategoryChange;
        window.onXiaoAiKeymapPresetChange = onXiaoAiKeymapPresetChange;
        window.onXiaoAiKeymapKeywordsInput = onXiaoAiKeymapKeywordsInput;
        window.refreshKodiAddonsList = refreshKodiAddonsList;




        // ================= 媒体库专属科技封面自动生成与配色体系 =================
        var LIB_COVER_THEMES = [
            {
                name: '星夜紫晶',
                bgStart: '#1e1b4b',
                bgMid: '#2e1065',
                bgEnd: '#09090b',
                borderColor: 'rgba(167, 139, 250, 0.45)',
                innerBorder: 'rgba(192, 132, 252, 0.22)',
                icon: '📚',
                badgeBg: 'rgba(139, 92, 246, 0.3)',
                badgeText: '#c4b5fd'
            },
            {
                name: '翡翠暗影',
                bgStart: '#064e3b',
                bgMid: '#022c22',
                bgEnd: '#021b14',
                borderColor: 'rgba(52, 211, 153, 0.45)',
                innerBorder: 'rgba(16, 185, 129, 0.22)',
                icon: '🎬',
                badgeBg: 'rgba(16, 185, 129, 0.3)',
                badgeText: '#a7f3d0'
            },
            {
                name: '深海曜石',
                bgStart: '#0c4a6e',
                bgMid: '#082f49',
                bgEnd: '#030712',
                borderColor: 'rgba(56, 189, 248, 0.45)',
                innerBorder: 'rgba(14, 165, 233, 0.22)',
                icon: '🍿',
                badgeBg: 'rgba(14, 165, 233, 0.3)',
                badgeText: '#bae6fd'
            },
            {
                name: '暮光绯红',
                bgStart: '#831843',
                bgMid: '#500724',
                bgEnd: '#0f050c',
                borderColor: 'rgba(244, 114, 182, 0.45)',
                innerBorder: 'rgba(236, 72, 153, 0.22)',
                icon: '🎞️',
                badgeBg: 'rgba(236, 72, 153, 0.3)',
                badgeText: '#fbcfe8'
            },
            {
                name: '赛博暗金',
                bgStart: '#451a03',
                bgMid: '#290e02',
                bgEnd: '#0b0908',
                borderColor: 'rgba(251, 191, 36, 0.45)',
                innerBorder: 'rgba(245, 158, 11, 0.22)',
                icon: '🌌',
                badgeBg: 'rgba(245, 158, 11, 0.3)',
                badgeText: '#fde68a'
            }
        ];

        function generateLibGradientCover(name, themeIdx) {
            try {
                var canvas = document.createElement('canvas');
                canvas.width = 640;
                canvas.height = 360;
                var ctx = canvas.getContext('2d');

                var idx = (typeof themeIdx === 'number' && themeIdx >= 0) ? (themeIdx % LIB_COVER_THEMES.length) : 0;
                var theme = LIB_COVER_THEMES[idx];

                // 1. 深色科技渐变背景 (对角线方向)
                var grad = ctx.createLinearGradient(0, 0, 640, 360);
                grad.addColorStop(0, theme.bgStart);
                grad.addColorStop(0.5, theme.bgMid);
                grad.addColorStop(1, theme.bgEnd);
                ctx.fillStyle = grad;
                ctx.fillRect(0, 0, 640, 360);

                // 2. 科技感双层边框质感
                ctx.strokeStyle = theme.borderColor;
                ctx.lineWidth = 2.5;
                ctx.strokeRect(12, 12, 616, 336);

                ctx.strokeStyle = theme.innerBorder;
                ctx.lineWidth = 1;
                ctx.strokeRect(18, 18, 604, 324);

                // 3. 顶部微小圆点装饰
                ctx.fillStyle = theme.badgeText;
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.font = 'bold 12px sans-serif';
                ctx.fillText('• • •', 320, 48);

                // 4. 主体大图标
                ctx.font = '54px sans-serif';
                ctx.fillText(theme.icon || '📚', 320, 115);

                // 5. 媒体库名称排版 (横向大字号与阴影)
                ctx.fillStyle = '#f8fafc';
                ctx.font = 'bold 28px sans-serif';
                ctx.shadowColor = 'rgba(0, 0, 0, 0.85)';
                ctx.shadowBlur = 12;
                ctx.shadowOffsetY = 3;

                var displayName = (name || '私有媒体库').trim();
                if (displayName.length > 13) {
                    var line1 = displayName.slice(0, 13);
                    var line2 = displayName.slice(13, 26);
                    if (displayName.length > 26) line2 += '...';
                    ctx.fillText(line1, 320, 182);
                    ctx.fillText(line2, 320, 220);
                } else {
                    ctx.fillText(displayName, 320, 195);
                }

                // 清除阴影
                ctx.shadowColor = 'transparent';
                ctx.shadowBlur = 0;
                ctx.shadowOffsetY = 0;

                // 6. 副标题
                ctx.fillStyle = '#94a3b8';
                ctx.font = '500 13px sans-serif';
                ctx.fillText('精选影视 · 私人珍藏', 320, 252);

                // 7. 底部胶囊徽章
                var badgeW = 140;
                var badgeH = 26;
                var badgeX = (640 - badgeW) / 2;
                var badgeY = 286;
                ctx.fillStyle = theme.badgeBg;
                ctx.beginPath();
                if (ctx.roundRect) {
                    ctx.roundRect(badgeX, badgeY, badgeW, badgeH, 13);
                } else {
                    ctx.rect(badgeX, badgeY, badgeW, badgeH);
                }
                ctx.fill();

                ctx.strokeStyle = theme.borderColor;
                ctx.lineWidth = 1;
                ctx.stroke();

                ctx.fillStyle = theme.badgeText;
                ctx.font = 'bold 11px sans-serif';
                ctx.fillText('• 私有媒体库 •', 320, badgeY + badgeH / 2);

                return canvas.toDataURL('image/jpeg', 0.88);
            } catch (e) {
                return '';
            }
        }

        function updateLibPosterPreview(url) {
            var imgEl = document.getElementById('libPosterPreviewImg');
            var placeholder = document.getElementById('libPosterPlaceholder');
            if (url) {
                imgEl.src = url;
                imgEl.style.display = 'block';
                placeholder.style.display = 'none';
            } else {
                imgEl.src = '';
                imgEl.style.display = 'none';
                placeholder.style.display = 'block';
            }
        }

        function updateLibPosterPreviewIfEmpty() {
            var currentCover = (document.getElementById('libCoverInput').value || '').trim();
            if (currentCover && !currentCover.startsWith('data:image')) {
                updateLibPosterPreview(currentCover);
                return;
            }
            var name = (document.getElementById('libNameInput').value || '').trim();
            var autoCover = generateLibGradientCover(name || '私有媒体库', state.currentLibThemeIdx || 0);
            state.generatedLibCoverDataUrl = autoCover;
            updateLibPosterPreview(autoCover);
        }

        function handleLibNameInput(val) {
            if (!state.isCustomLibCoverUploaded) {
                updateLibPosterPreviewIfEmpty();
            }
        }

        function handleLibCoverInput(val) {
            val = (val || '').trim();
            if (val) {
                state.isCustomLibCoverUploaded = true;
                updateLibPosterPreview(val);
            } else {
                state.isCustomLibCoverUploaded = false;
                updateLibPosterPreviewIfEmpty();
            }
        }

        function switchLibCoverTheme() {
            state.currentLibThemeIdx = ((state.currentLibThemeIdx || 0) + 1) % LIB_COVER_THEMES.length;
            var theme = LIB_COVER_THEMES[state.currentLibThemeIdx];
            state.isCustomLibCoverUploaded = false;
            document.getElementById('libCoverInput').value = '';
            updateLibPosterPreviewIfEmpty();
            showToast('已切换至【' + theme.name + '】封面配色');
        }

        function triggerLibPosterUpload() {
            var fileInput = document.getElementById('libPosterFileInput');
            if (fileInput) fileInput.click();
        }

        function handleLibPosterFileSelect(input) {
            if (!input || !input.files || input.files.length === 0) return;
            var file = input.files[0];
            uploadLibPosterFile(file);
            input.value = '';
        }

        function uploadLibPosterFile(file) {
            if (!file) return;
            if (file.type && !file.type.startsWith('image/')) {
                showToast('请选择有效的图片文件 (JPG/PNG/WebP/GIF)');
                return;
            }

            var overlay = document.getElementById('libPosterUploadOverlay');
            if (overlay) overlay.style.display = 'flex';

            var formData = new FormData();
            formData.append('file', file);

            fetch('/api/private/upload_poster', {
                method: 'POST',
                body: formData
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (overlay) overlay.style.display = 'none';
                if (data.success && data.data && data.data.url) {
                    var uploadedUrl = data.data.url;
                    state.isCustomLibCoverUploaded = true;
                    document.getElementById('libCoverInput').value = uploadedUrl;
                    updateLibPosterPreview(uploadedUrl);
                    showToast('🎉 媒体库封面上传成功！');
                } else {
                    throw new Error(data.message || data.error || '上传失败');
                }
            })
            .catch(function(err) {
                if (overlay) overlay.style.display = 'none';
                showToast('封面上传异常: ' + err.message);
            });
        }

        function uploadBase64LibPoster(dataUrl) {
            if (!dataUrl || !dataUrl.startsWith('data:image')) {
                return Promise.resolve(dataUrl || '');
            }
            return fetch('/api/private/upload_poster', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ image: dataUrl })
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (data.success && data.data && data.data.url) {
                    return data.data.url;
                }
                return dataUrl;
            })
            .catch(function(err) {
                console.warn('上传 Base64 封面失败，使用 DataURL 兜底:', err);
                return dataUrl;
            });
        }

        window.addEventListener('DOMContentLoaded', function() {
            initUserAuth();
            loadLibraries();

            // 绑定媒体库封面拖拽与剪贴板粘贴
            var libBox = document.getElementById('libPosterBox');
            if (libBox) {
                libBox.addEventListener('dragover', function(e) {
                    e.preventDefault();
                    libBox.style.borderColor = '#38bdf8';
                });
                libBox.addEventListener('dragleave', function() {
                    libBox.style.borderColor = 'rgba(255,255,255,0.2)';
                });
                libBox.addEventListener('drop', function(e) {
                    e.preventDefault();
                    libBox.style.borderColor = 'rgba(255,255,255,0.2)';
                    if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                        uploadLibPosterFile(e.dataTransfer.files[0]);
                    }
                });
            }

            var libModal = document.getElementById('libModal');
            if (libModal) {
                libModal.addEventListener('paste', function(e) {
                    var items = (e.clipboardData || (window.clipboardData && window.clipboardData.items) || {}).items;
                    if (!items) return;
                    for (var i = 0; i < items.length; i++) {
                        if (items[i].type && items[i].type.indexOf('image') !== -1) {
                            var blob = items[i].getAsFile();
                            if (blob) {
                                uploadLibPosterFile(blob);
                                showToast('已从剪贴板捕获图片并正在上传...');
                                break;
                            }
                        }
                    }
                });
            }
        });

        function autoGenerateMissingLibCovers() {
            if (!state.libraries || state.libraries.length === 0) return;
            for (var i = 0; i < state.libraries.length; i++) {
                (function(lib, idx) {
                    if (!lib.cover_url) {
                        var autoCover = generateLibGradientCover(lib.name || '私有媒体库', idx % LIB_COVER_THEMES.length);
                        if (autoCover) {
                            lib.cover_url = autoCover;
                            uploadBase64LibPoster(autoCover).then(function(finalCover) {
                                if (finalCover) {
                                    lib.cover_url = finalCover;
                                    fetch('/api/private/libraries/' + lib.id, {
                                        method: 'PUT',
                                        headers: { 'Content-Type': 'application/json' },
                                        body: JSON.stringify({ cover_url: finalCover })
                                    }).catch(function(e) {
                                        console.warn('[autoGenerateMissingLibCovers] Failed to persist cover for lib:', lib.id, e);
                                    });
                                }
                            });
                        }
                    }
                })(state.libraries[i], i);
            }
        }

        function loadLibraries(showNotice) {
            fetch('/api/private/libraries')
                .then(function(res) { return res.json(); })
                .then(function(data) {
                    state.libraries = data.data || [];
                    autoGenerateMissingLibCovers();
                    renderLibraries();
                    pollPosterSyncStatuses();
                    refreshUnmatchedCounts();
                    if (showNotice === true) {
                        showToast('已刷新媒体库列表');
                    }
                })
                .catch(function(err) {
                    showToast('加载媒体库失败: ' + err.message);
                });
        }

        var posterPollTimer = null;
        function pollPosterSyncStatuses() {
            if (posterPollTimer) clearTimeout(posterPollTimer);
            if (!state.libraries || state.libraries.length === 0) return;

            var syncingAny = false;
            var promises = state.libraries.map(function(lib) {
                if (lib.poster_mode <= 0) return Promise.resolve();
                return fetch('/api/private/libraries/' + lib.id + '/poster_status')
                    .then(function(res) { return res.json(); })
                    .then(function(status) {
                        if (!state.posterStatuses) state.posterStatuses = {};
                        state.posterStatuses[lib.id] = status;
                        if (status && status.status === 'syncing') {
                            syncingAny = true;
                        }
                    })
                    .catch(function() {});
            });

            Promise.all(promises).then(function() {
                renderLibraries();
                if (syncingAny) {
                    posterPollTimer = setTimeout(pollPosterSyncStatuses, 2000);
                }
            });
        }

        function renderLibraries() {
            var grid = document.getElementById('libListGrid');
            document.getElementById('libCountText').innerText = '共有 ' + state.libraries.length + ' 个媒体库';

            if (state.libraries.length === 0) {
                grid.innerHTML = '<div class="empty-state" style="grid-column: 1 / -1;"><div class="empty-icon">🗃️</div><div style="font-size: 16px; font-weight: 600; color: #fff;">暂无私有媒体库</div><div>点击右上角【+ 创建媒体库】或导入他人分享</div></div>';
                return;
            }

            var html = '';
            for (var i = 0; i < state.libraries.length; i++) {
                var lib = state.libraries[i];
                var badgeClass = 'badge-self';
                var badgeText = '自建';
                if (lib.share_type === 2) {
                    badgeClass = 'badge-sync';
                    badgeText = '持续更新';
                } else if (lib.share_type === 1) {
                    badgeClass = 'badge-snap';
                    badgeText = '快照导入';
                } else if (lib.share_code) {
                    badgeClass = 'badge-self';
                    badgeText = '自建 · 已发布';
                }

                var posterBadgeHtml = '';
                var syncStatus = state.posterStatuses ? state.posterStatuses[lib.id] : null;
                if (syncStatus && syncStatus.status === 'syncing') {
                    var cur = syncStatus.current || 0;
                    var tot = syncStatus.total || (lib.item_count || 0);
                    posterBadgeHtml = '<div class="lib-badge-right badge-poster-syncing">🔄 同步中 ' + cur + '/' + tot + '</div>';
                } else if (lib.poster_mode === 2) {
                    posterBadgeHtml = '<div class="lib-badge-right badge-poster-tmdb">完整海报墙</div>';
                } else if (lib.poster_mode === 1) {
                    posterBadgeHtml = '<div class="lib-badge-right badge-poster-lite">精简海报墙</div>';
                }

                var cover = lib.cover_url || generateLibGradientCover(lib.name || '私有媒体库', i % LIB_COVER_THEMES.length);
                html += '<div class="lib-card" id="lib-card-' + lib.id + '" data-id="' + lib.id + '" onclick="enterLibrary(\'' + lib.id + '\')">';
                html += '<div class="lib-cover-box"><img referrerpolicy="no-referrer" src="' + cover + '" class="lib-cover"><div class="lib-badge ' + badgeClass + '">' + badgeText + '</div>' + posterBadgeHtml + '</div>';
                html += '<div class="lib-content">';
                html += '<div class="lib-name">' + lib.name + '</div>';
                html += '<div class="lib-meta"><span>🎬 ' + (lib.item_count || 0) + ' 部影片</span><span>作者: ' + (lib.creator_name || '我') + '</span></div>';
                html += '<div class="lib-card-actions" onclick="event.stopPropagation()">';
                if (lib.share_type === 2) {
                    html += '<button class="icon-btn" onclick="syncLibrary(\'' + lib.id + '\')">🔄 同步</button>';
                    html += '<button class="icon-btn" onclick="detachLibrary(\'' + lib.id + '\')" title="解除云端订阅并转为自建媒体库，获得完整编辑权限">🔓 转自建</button>';
                    html += '<button class="icon-btn" onclick="openEditLibModal(\'' + lib.id + '\')">✏️ 配置</button>';
                    html += '<button class="icon-btn" style="color: #fca5a5;" onclick="deleteLibrary(\'' + lib.id + '\')">🗑️ 退订</button>';
                } else {
                    if (lib.share_code) {
                        html += '<button class="icon-btn" onclick="syncLibrary(\'' + lib.id + '\')">🔄 同步</button>';
                    }
                    html += '<button class="icon-btn" onclick="openShareModal(\'' + lib.id + '\')">🔗 分享</button>';
                    html += '<button class="icon-btn" onclick="openEditLibModal(\'' + lib.id + '\')">✏️ 修改</button>';
                    html += '<button class="icon-btn" style="color: #fca5a5;" onclick="deleteLibrary(\'' + lib.id + '\')">🗑️ 删除</button>';
                }
                html += '</div></div></div>';
            }
            grid.innerHTML = html;
        }

        function openCreateLibModal() {
            state.activeEditingLibId = null;
            state.isCustomLibCoverUploaded = false;
            state.currentLibThemeIdx = 0;
            document.getElementById('libModalTitle').innerText = '创建媒体库';
            var nameInput = document.getElementById('libNameInput');
            if (nameInput) {
                nameInput.value = '';
                nameInput.disabled = false;
                nameInput.placeholder = '输入媒体库名称（例如：4K科幻精选、漫威宇宙全集）';
            }
            var coverInput = document.getElementById('libCoverInput');
            if (coverInput) {
                coverInput.value = '';
                coverInput.disabled = false;
                coverInput.placeholder = '支持粘贴网络图片直链 (建议 16:9 横版)；留空将使用自动生成封面';
            }
            var radio = document.getElementById('posterMode2');
            if (radio) radio.checked = true;

            var btnResync = document.getElementById('btnResyncPosterModal');
            if (btnResync) btnResync.style.display = 'none';

            updateLibPosterPreviewIfEmpty();
            openModal('libModal');
        }

        function openEditLibModal(id) {
            var lib = null;
            for (var i = 0; i < state.libraries.length; i++) {
                if (state.libraries[i].id === id) { lib = state.libraries[i]; break; }
            }
            if (!lib) return;
            state.activeEditingLibId = id;
            var isSubLib = (lib.share_type === 2);

            document.getElementById('libModalTitle').innerText = isSubLib ? '修改媒体库配置 (订阅库)' : '修改媒体库';
            var nameInput = document.getElementById('libNameInput');
            if (nameInput) {
                nameInput.value = lib.name || '';
                nameInput.disabled = isSubLib;
                nameInput.placeholder = isSubLib ? '订阅型媒体库名称跟随作者云端，不可修改' : '输入媒体库名称（例如：4K科幻精选、漫威宇宙全集）';
            }
            var coverInput = document.getElementById('libCoverInput');
            if (coverInput) {
                coverInput.value = lib.cover_url || '';
                coverInput.disabled = false;
                coverInput.placeholder = '支持粘贴网络图片直链 (建议 16:9 横版)；留空将使用自动生成封面';
            }

            if (lib.cover_url) {
                state.isCustomLibCoverUploaded = true;
                updateLibPosterPreview(lib.cover_url);
            } else {
                state.isCustomLibCoverUploaded = false;
                updateLibPosterPreviewIfEmpty();
            }

            var mode = (lib.poster_mode !== undefined && lib.poster_mode !== null) ? lib.poster_mode : 2;
            var targetRadio = document.getElementById('posterMode' + mode);
            if (targetRadio) targetRadio.checked = true;

            var btnResync = document.getElementById('btnResyncPosterModal');
            if (btnResync) {
                btnResync.style.display = (lib.poster_mode > 0) ? 'inline-block' : 'none';
            }

            openModal('libModal');
        }

        function triggerCurrentLibPosterSync() {
            var libId = state.activeEditingLibId || (state.currentLib ? state.currentLib.id : '');
            if (!libId || libId === 'all') {
                showToast('请先选择一个具体的媒体库');
                return;
            }
            triggerPosterSync(libId);
        }

        function triggerPosterSync(libId, evt) {
            if (evt) evt.stopPropagation();
            var lib = null;
            for (var i = 0; i < (state.libraries || []).length; i++) {
                if (state.libraries[i].id === libId) { lib = state.libraries[i]; break; }
            }
            var libName = lib ? lib.name : (state.currentLib ? state.currentLib.name : '媒体库');

            if (!confirm('确定要为【' + libName + '】立即重新全量同步海报墙与评分吗？\n将自动为全库影片聚合获取 IMDb、烂番茄、Metacritic 等全套评分并写入 Kodi 资料库。')) {
                return;
            }

            closeModal('libModal');
            showToast('已触发后台海报墙与评分同步，正在处理...');

            fetch('/api/private/libraries/' + libId + '/export_strm', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({})
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (data && data.success) {
                    if (!state.posterStatuses) state.posterStatuses = {};
                    state.posterStatuses[libId] = {
                        status: 'syncing',
                        current: 0,
                        total: lib ? (lib.item_count || 0) : 0
                    };
                    pollPosterSyncStatuses();
                } else {
                    showToast('触发同步失败: ' + (data.message || '未知错误'));
                }
            })
            .catch(function(err) {
                showToast('请求异常: ' + err.message);
            });
        }

        function submitSaveLibrary() {
            var name = document.getElementById('libNameInput').value.trim();
            if (!name) {
                showToast('请输入媒体库名称');
                return;
            }
            var coverInputVal = document.getElementById('libCoverInput').value.trim();
            var posterMode = 2;
            var selectedRadio = document.querySelector('input[name="libPosterMode"]:checked');
            if (selectedRadio) {
                posterMode = parseInt(selectedRadio.value, 10);
            }

            var editId = state.activeEditingLibId;
            var btnSave = document.getElementById('btnSubmitSaveLib');
            if (btnSave) {
                btnSave.disabled = true;
                btnSave.innerText = '正在保存...';
            }

            // 若封面为空或为 DataURL，则自动上传为本地实体文件
            var coverPromise;
            if (coverInputVal && !coverInputVal.startsWith('data:image')) {
                coverPromise = Promise.resolve(coverInputVal);
            } else {
                var autoDataUrl = state.generatedLibCoverDataUrl || generateLibGradientCover(name, state.currentLibThemeIdx || 0);
                coverPromise = uploadBase64LibPoster(autoDataUrl);
            }

            coverPromise.then(function(finalCover) {
                var url = '/api/private/libraries';
                var method = 'POST';
                if (editId) {
                    var currentLib = null;
                    for (var i = 0; i < state.libraries.length; i++) {
                        if (state.libraries[i].id === editId) { currentLib = state.libraries[i]; break; }
                    }
                    if (currentLib && currentLib.poster_mode > 0 && posterMode === 0) {
                        if (!confirm('将媒体库设置为【不启用海报墙】将会同步清空 Kodi 中该媒体库导出的海报墙与本地 STRM 文件。确定要继续吗？')) {
                            if (btnSave) {
                                btnSave.disabled = false;
                                btnSave.innerText = '确认保存';
                            }
                            return;
                        }
                    }
                    url = '/api/private/libraries/' + editId;
                    method = 'PUT';
                }

                return fetch(url, {
                    method: method,
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: name, cover_url: finalCover, poster_mode: posterMode })
                })
                .then(function(res) { return res.json(); })
                .then(function(data) {
                    if (btnSave) {
                        btnSave.disabled = false;
                        btnSave.innerText = '确认保存';
                    }
                    if (data && !data.success) {
                        showToast(data.message || '保存失败');
                        return;
                    }
                    showToast(editId ? '修改成功' : '创建成功');
                    closeModal('libModal');
                    state.activeEditingLibId = null;

                    if (editId && posterMode > 0) {
                        if (!state.posterStatuses) state.posterStatuses = {};
                        state.posterStatuses[editId] = {
                            status: 'syncing',
                            current: 0,
                            total: 0
                        };
                    }
                    loadLibraries();
                });
            })
            .catch(function(err) {
                if (btnSave) {
                    btnSave.disabled = false;
                    btnSave.innerText = '确认保存';
                }
                showToast('保存失败: ' + err.message);
            });
        }

        function triggerCleanOrphanedKodi() {
            if (!confirm('确定要清理 Kodi 中所有已删除媒体库的废弃海报墙和失效记录吗？\n\n该操作将自动扫描并移除 Kodi 视频数据库与 sources.xml 中所有本地磁盘已不存在的孤立记录。')) {
                return;
            }
            fetch('/api/private/kodi/clean_orphaned', { method: 'POST' })
                .then(function(res) { return res.json(); })
                .then(function(data) {
                    showToast(data.message || '已触发 Kodi 海报墙深度清理');
                })
                .catch(function(err) {
                    showToast('清理请求失败: ' + err.message);
                });
        }

        function deleteLibrary(id) {
            var lib = null;
            for (var i = 0; i < state.libraries.length; i++) {
                if (state.libraries[i].id === id) { lib = state.libraries[i]; break; }
            }
            if (!lib) return;

            // 如果是自建且已发布分享的媒体库，弹出双选项弹窗让作者选择（仅删本地 vs 同时下架）
            if (lib.share_type === 0 && lib.share_code) {
                state.pendingDelLib = lib;
                document.getElementById('delLibNameDisplay').innerText = lib.name || '自建媒体库';
                document.getElementById('delLibCodeDisplay').innerText = lib.share_code;
                openModal('deleteShareLibModal');
                return;
            }

            // 普通自建库或订阅库
            var isSub = lib.share_type === 2;
            var libName = lib.name || '该媒体库';
            var confirmMsg = isSub ?
                ('确定要退订并删除媒体库【' + libName + '】吗？\n\n本地影片与海报墙将被清空，云端分享不受任何影响。') :
                ('确定要删除媒体库【' + libName + '】及其包含的所有影片与链接吗？');

            if (lib.poster_mode > 0) {
                confirmMsg += '\n\n⚠️ 注意：该媒体库已启用 Kodi 海报墙，删除媒体库将同步清空 Kodi 中对应的海报墙与本地 STRM 文件。';
            }

            if (!confirm(confirmMsg)) return;
            var cardEl = document.getElementById('lib-card-' + id);
            if (cardEl) {
                cardEl.style.opacity = '0.35';
                cardEl.style.pointerEvents = 'none';
                cardEl.style.filter = 'grayscale(0.8)';
            }
            showToast('正在删除媒体库【' + libName + '】及关联数据，请稍候...', 5000);

            fetch('/api/private/libraries/' + id, { method: 'DELETE' })
                .then(function(res) {
                    if (!res.ok) throw new Error('HTTP ' + res.status);
                    return res.json();
                })
                .then(function() {
                    showToast('媒体库【' + libName + '】已成功删除');
                    loadLibraries();
                })
                .catch(function(err) {
                    if (cardEl) {
                        cardEl.style.opacity = '';
                        cardEl.style.pointerEvents = '';
                        cardEl.style.filter = '';
                    }
                    showToast('删除失败: ' + err.message);
                });
        }

        async function executeDeleteSharedLib(unpublishCloud) {
            var lib = state.pendingDelLib;
            if (!lib) return;

            closeModal('deleteShareLibModal');
            var cardEl = document.getElementById('lib-card-' + lib.id);
            if (cardEl) {
                cardEl.style.opacity = '0.35';
                cardEl.style.pointerEvents = 'none';
                cardEl.style.filter = 'grayscale(0.8)';
            }

            if (unpublishCloud) {
                // 同时下架云端分享
                if (!authState.token) {
                    openAuthModal(function() {
                        executeDeleteSharedLib(true);
                    });
                    return;
                }

                showToast('正在下架云端分享并清理本地数据，请稍候...', 5000);
                try {
                    var unpubRes = await authFetch('/api/mv/shared-libraries/unpublish', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ shareCode: lib.share_code })
                    });
                    var unpubJson = await unpubRes.json();
                    if (!unpubJson.success && unpubJson.message && unpubJson.message.indexOf('不存在') === -1) {
                        throw new Error(unpubJson.message || '云端下架失败');
                    }
                } catch (err) {
                    if (cardEl) {
                        cardEl.style.opacity = '';
                        cardEl.style.pointerEvents = '';
                        cardEl.style.filter = '';
                    }
                    showToast('云端下架异常: ' + err.message);
                    return;
                }
            } else {
                showToast('正在删除本地媒体库【' + (lib.name || '') + '】及关联数据...', 5000);
            }

            // 清理本地媒体库与海报墙
            fetch('/api/private/libraries/' + lib.id, { method: 'DELETE' })
                .then(function(res) {
                    if (!res.ok) throw new Error('HTTP ' + res.status);
                    return res.json();
                })
                .then(function() {
                    showToast(unpublishCloud ? '已成功下架云端分享并删除本地媒体库！' : '已删除本地媒体库（云端分享依然保留）');
                    state.pendingDelLib = null;
                    loadLibraries();
                })
                .catch(function(err) {
                    if (cardEl) {
                        cardEl.style.opacity = '';
                        cardEl.style.pointerEvents = '';
                        cardEl.style.filter = '';
                    }
                    showToast('删除失败: ' + err.message);
                });
        }

        function openMyPublishedModal() {
            if (!authState.token) {
                openAuthModal(function() {
                    openMyPublishedModal();
                });
                return;
            }

            openModal('myPublishedModal');
            loadMyPublishedList();
        }

        async function loadMyPublishedList() {
            var loadingEl = document.getElementById('myPublishedLoading');
            var emptyEl = document.getElementById('myPublishedEmpty');
            var listEl = document.getElementById('myPublishedList');
            var countEl = document.getElementById('myPublishedCountSummary');

            if (loadingEl) loadingEl.style.display = 'block';
            if (emptyEl) emptyEl.style.display = 'none';
            if (listEl) listEl.innerHTML = '';

            try {
                var res = await authFetch('/api/mv/shared-libraries/my-published');
                var json = await res.json();

                if (loadingEl) loadingEl.style.display = 'none';

                if (!json.success || !json.data || !Array.isArray(json.data.items) || json.data.items.length === 0) {
                    if (emptyEl) emptyEl.style.display = 'block';
                    if (countEl) countEl.innerText = '共 0 个发布资产';
                    return;
                }

                var items = json.data.items;
                if (countEl) countEl.innerText = '共 ' + items.length + ' 个发布资产';

                var html = '';
                for (var i = 0; i < items.length; i++) {
                    var it = items[i];
                    var isPublicTag = it.isPublic ? '<span style="background: rgba(16,185,129,0.2); color: #34d399; font-size: 11px; padding: 2px 8px; border-radius: 12px;">🌐 公开大厅</span>' : '<span style="background: rgba(148,163,184,0.2); color: #cbd5e1; font-size: 11px; padding: 2px 8px; border-radius: 12px;">🔒 私密分享</span>';
                    var coverImg = it.coverUrl || PRESET_COVERS[0];

                    // 检查当前设备本地是否已经存在该分享码的媒体库
                    var localExist = false;
                    for (var k = 0; k < state.libraries.length; k++) {
                        if (state.libraries[k].share_code === it.shareCode) {
                            localExist = true;
                            break;
                        }
                    }

                    html += '<div style="background: rgba(15, 23, 42, 0.6); border: 1px solid var(--card-border); border-radius: 12px; padding: 14px; display: flex; gap: 14px; align-items: center; justify-content: space-between; flex-wrap: wrap;">';
                    html += '<div style="display: flex; gap: 12px; align-items: center; min-width: 240px; flex: 1;">';
                    html += '<img referrerpolicy="no-referrer" src="' + coverImg + '" style="width: 50px; height: 70px; object-fit: cover; border-radius: 6px; background: #1e293b;">';
                    html += '<div>';
                    html += '<div style="font-weight: 700; font-size: 15px; color: #fff;">' + it.name + ' <span style="font-size: 13px; color: #a5b4fc; font-weight: 600; margin-left: 4px;">[' + it.shareCode + ']</span></div>';
                    html += '<div style="display: flex; gap: 6px; align-items: center; margin-top: 4px; flex-wrap: wrap;">';
                    html += '<span style="font-size: 11px; color: var(--text-muted);">v' + (it.version || 1) + '</span>';
                    html += '<span style="font-size: 11px; color: var(--text-muted);">· ' + (it.itemCount || 0) + ' 部影片</span>';
                    html += '<span style="font-size: 11px; color: var(--text-muted);">· ' + (it.linkCount || 0) + ' 条链接</span>';
                    html += isPublicTag;
                    html += '</div>';
                    html += '</div></div>';

                    html += '<div style="display: flex; gap: 8px; align-items: center;">';
                    if (localExist) {
                        html += '<button class="btn btn-secondary" style="font-size: 12px; padding: 6px 12px; color: #a5b4fc; border-color: rgba(99,102,241,0.4);" onclick="locateLocalLibraryByShareCode(\'' + it.shareCode + '\')">📍 本地已存在 (直达)</button>';
                    } else {
                        html += '<button class="btn" style="font-size: 12px; padding: 6px 12px;" onclick="importFromMyPublished(\'' + it.shareCode + '\')">📥 拉回本地维护</button>';
                    }
                    html += '<button class="btn btn-secondary" style="font-size: 12px; padding: 6px 10px; color: #fca5a5; background: rgba(239,68,68,0.1); border-color: rgba(239,68,68,0.3);" onclick="unpublishFromMyPublished(\'' + it.shareCode + '\', \'' + it.name + '\')">🚫 下架</button>';
                    html += '</div>';
                    html += '</div>';
                }

                if (listEl) listEl.innerHTML = html;
            } catch (err) {
                if (loadingEl) loadingEl.style.display = 'none';
                showToast('加载我的发布失败: ' + err.message);
            }
        }

        async function importFromMyPublished(shareCode) {
            showToast('正在从云端拉取完整片单...');
            try {
                var detailRes = await fetch('/api/mv/shared-libraries/detail/' + shareCode);
                var detailData = await detailRes.json();
                if (!detailData.success || !detailData.data) {
                    throw new Error(detailData.message || '拉取媒体库数据失败');
                }

                // 强制将 isOwner 标记为 true，本地入库为自建可维护媒体库 (share_type = 0)
                if (detailData.data.library) {
                    detailData.data.library.isOwner = true;
                }

                var importRes = await fetch('/api/private/import_snapshot', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(detailData.data)
                });
                var importData = await importRes.json();
                if (importData.success) {
                    showToast('🎉 已成功拉回本地，开启作者编辑维护模式！');
                    closeModal('myPublishedModal');
                    loadLibraries();
                } else {
                    showToast('导入失败: ' + (importData.message || '未知错误'));
                }
            } catch (err) {
                showToast('拉取异常: ' + err.message);
            }
        }

        function locateLocalLibraryByShareCode(shareCode) {
            closeModal('myPublishedModal');
            closeModal('importShareModal');
            for (var i = 0; i < state.libraries.length; i++) {
                if (state.libraries[i].share_code === shareCode) {
                    enterLibrary(state.libraries[i].id);
                    showToast('已为您定位到本地媒体库【' + state.libraries[i].name + '】');
                    return;
                }
            }
        }

        async function unpublishFromMyPublished(shareCode, libName) {
            if (!confirm('确定要从云端和分享大厅彻底下架媒体库【' + libName + '】(专属码: ' + shareCode + ') 吗？\n\n下架后其他订阅者将无法再同步此库。')) return;

            try {
                var unpubRes = await authFetch('/api/mv/shared-libraries/unpublish', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ shareCode: shareCode })
                });
                var unpubJson = await unpubRes.json();
                if (unpubJson.success) {
                    showToast('已成功下架云端分享！');
                    loadMyPublishedList();
                    loadLibraries();
                } else {
                    showToast('下架失败: ' + (unpubJson.message || '未知错误'));
                }
            } catch (err) {
                showToast('下架异常: ' + err.message);
            }
        }

        function isCurrentLibReadOnly() {
            return Boolean(state.currentLib && state.currentLib.share_type === 2);
        }

        function isMovieReadOnly(movie) {
            if (!movie) return false;
            var libId = movie.library_id;
            if (libId && state.libraries) {
                for (var i = 0; i < state.libraries.length; i++) {
                    if (state.libraries[i].id === libId) {
                        return state.libraries[i].share_type === 2;
                    }
                }
            }
            return isCurrentLibReadOnly();
        }

        function enterLibraryDirect(libId) {
            if (!libId) return;
            var lib = null;
            if (state.libraries) {
                for (var i = 0; i < state.libraries.length; i++) {
                    if (state.libraries[i].id === libId) { lib = state.libraries[i]; break; }
                }
            }
            if (lib) {
                enterLibrary(libId);
            } else {
                fetch('/api/private/libraries/' + libId)
                    .then(function(res) { return res.json(); })
                    .then(function(d) {
                        if (d && d.data) {
                            if (!state.libraries) state.libraries = [];
                            state.libraries.push(d.data);
                            enterLibrary(libId);
                        }
                    })
                    .catch(function(err) {
                        showToast('获取媒体库信息失败: ' + err.message);
                    });
            }
        }

        function checkReadOnlyGuard() {
            if (isCurrentLibReadOnly()) {
                showToast('🔒 持续更新型订阅媒体库为只读模式，不可手动修改。请点击【🔄 同步】从作者处获取最新片单');
                return true;
            }
            return false;
        }

        function enterLibrary(libId) {
            var lib = null;
            for (var i = 0; i < state.libraries.length; i++) {
                if (state.libraries[i].id === libId) { lib = state.libraries[i]; break; }
            }
            if (!lib) return;
            state.currentLib = lib;
            state.currentLevel = 2;

            document.getElementById('viewLevel1').style.display = 'none';
            document.getElementById('viewLevel2').style.display = 'block';
            document.getElementById('viewLevel3').style.display = 'none';
            document.getElementById('headerBackBtn').style.display = 'inline-flex';
            document.getElementById('pageMainTitle').innerText = lib.name;
            document.getElementById('currentLibName').innerText = lib.name;
            refreshUnmatchedCounts(libId);

            var isSubLib = (lib.share_type === 2);
            var dropdownImport = document.getElementById('dropdownL2ImportWrapper');
            var btnUnmatched = document.getElementById('btnL2Unmatched');
            var btnDuplicates = document.getElementById('btnL2Duplicates');
            var btnSyncDirs = document.getElementById('btnL2SyncDirs');
            var btnShare = document.getElementById('btnL2Share');
            var textShare = document.getElementById('textL2Share');
            var btnSync = document.getElementById('btnL2Sync');
            var btnSearch = document.getElementById('btnL2Search');
            var btnDetach = document.getElementById('btnL2Detach');

            if (isSubLib) {
                if (dropdownImport) dropdownImport.style.display = 'none';
                if (btnSearch) btnSearch.style.display = 'none';
                if (btnUnmatched) btnUnmatched.style.display = 'none';
                if (btnSyncDirs) btnSyncDirs.style.display = 'none';
                if (btnShare) btnShare.style.display = 'none';
                if (btnSync) {
                    btnSync.style.display = 'flex';
                }
                if (btnDetach) btnDetach.style.display = 'flex';
            } else {
                if (dropdownImport) dropdownImport.style.display = 'inline-block';
                if (btnSearch) btnSearch.style.display = 'inline-flex';
                if (btnDetach) btnDetach.style.display = 'none';
                if (btnUnmatched) btnUnmatched.style.display = 'flex';
                if (btnDuplicates) btnDuplicates.style.display = 'flex';
                if (btnSyncDirs) btnSyncDirs.style.display = 'flex';
                if (btnShare) {
                    btnShare.style.display = 'flex';
                    if (textShare) {
                        textShare.innerText = lib.share_code ? '管理分享' : '分享媒体库';
                    }
                }
                if (btnSync) {
                    btnSync.style.display = lib.share_code ? 'flex' : 'none';
                }
            }
            if (typeof updateCombinedToolsBadge === 'function') {
                updateCombinedToolsBadge();
            }

            // 重置检索与分页状态
            state.moviePage = 1;
            state.movieKeyword = '';
            state.movieTypeFilter = 0;
            var searchInp = document.getElementById('movieSearchInput');
            if (searchInp) {
                searchInp.value = '';
                searchInp.placeholder = '搜索片名 / 导演 / 演员...';
            }
            var clearBtn = document.getElementById('movieSearchClearBtn');
            if (clearBtn) clearBtn.style.display = 'none';
            var typeSel = document.getElementById('movieTypeFilter');
            if (typeSel) typeSel.value = '0';
            var sizeSel = document.getElementById('moviePageSizeSelect');
            if (sizeSel) sizeSel.value = String(state.moviePageSize);

            // 同步视图切换按钮状态
            var btnPoster = document.getElementById('btnViewPoster');
            var btnTable = document.getElementById('btnViewTable');
            if (state.movieViewMode === 'table') {
                if (btnTable) btnTable.classList.add('active');
                if (btnPoster) btnPoster.classList.remove('active');
            } else {
                if (btnPoster) btnPoster.classList.add('active');
                if (btnTable) btnTable.classList.remove('active');
            }
            updateMovieSortIcons();

            loadMovies();
        }

        function refreshCurrentLibrary(showNotice) {
            if (!state.currentLib) return;
            var libId = state.currentLib.id;
            var btn = document.getElementById('btnL2Refresh');
            if (btn) {
                btn.disabled = true;
                btn.style.opacity = '0.6';
            }

            if (libId === 'all') {
                loadMovies();
                setTimeout(function() {
                    if (btn) {
                        btn.disabled = false;
                        btn.style.opacity = '1';
                    }
                    if (showNotice !== false) {
                        showToast('已刷新全部私有库影片');
                    }
                }, 350);
                return;
            }

            // 1. 刷新待确认暂存箱角标
            refreshUnmatchedCounts(libId);

            // 2. 获取该媒体库最新的元数据信息（如总影片数 item_count、最新名称等）
            fetch('/api/private/libraries/' + libId)
                .then(function(res) { return res.json(); })
                .then(function(d) {
                    if (d && d.data) {
                        state.currentLib = d.data;
                        for (var i = 0; i < state.libraries.length; i++) {
                            if (state.libraries[i].id === libId) {
                                state.libraries[i] = d.data;
                                break;
                            }
                        }
                        var nameEl = document.getElementById('currentLibName');
                        if (nameEl) nameEl.innerText = d.data.name;
                        var metaEl = document.getElementById('currentLibMeta');
                        if (metaEl) {
                            var cnt = d.data.item_count || 0;
                            metaEl.innerText = '共 ' + cnt + ' 部影片 · ' + (state.episodeTotal || 0) + ' 个单集 · ' + (state.linkTotal || 0) + ' 个链接';
                        }
                    }
                })
                .catch(function(e) {
                    console.warn('获取媒体库最新状态失败:', e);
                })
                .finally(function() {
                    // 3. 重新拉取影片列表
                    loadMovies();
                    setTimeout(function() {
                        if (btn) {
                            btn.disabled = false;
                            btn.style.opacity = '1';
                        }
                        if (showNotice !== false) {
                            showToast('已刷新媒体库');
                        }
                    }, 350);
                });
        }

        function escapeHtml(str) {
            if (str === null || str === undefined) return '';
            return String(str)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }

        function formatDateTime(val) {
            if (!val) return '-';
            if (typeof val === 'number' || (!isNaN(val) && String(val).indexOf('-') === -1)) {
                var num = parseInt(val, 10);
                if (num <= 0) return '-';
                if (num < 10000000000) num = num * 1000;
                var d = new Date(num);
                var pad = function(n) { return n < 10 ? '0' + n : String(n); };
                return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
            }
            var s = String(val).replace('T', ' ');
            if (s.length >= 16) return s.substring(0, 16);
            return s;
        }

        function getMovieCountry(m) {
            var raw = m.area || m.country || '';
            if (raw) {
                var parts = raw.split(/[\/,]/);
                var mapped = [];
                for (var i = 0; i < parts.length; i++) {
                    var p = parts[i].trim();
                    if (!p) continue;
                    var zh = mapCountryCodeToArea('', p);
                    if (zh && mapped.indexOf(zh) === -1) mapped.push(zh);
                }
                if (mapped.length > 0) return mapped.join(' / ');
            }
            if (m.extra_meta_json) {
                try {
                    var meta = typeof m.extra_meta_json === 'string' ? JSON.parse(m.extra_meta_json) : m.extra_meta_json;
                    if (meta) {
                        if (meta.production_countries && meta.production_countries.length > 0) {
                            var names = [];
                            for (var k = 0; k < meta.production_countries.length && k < 3; k++) {
                                var c = meta.production_countries[k];
                                var zh = mapCountryCodeToArea(c.iso_3166_1, c.name);
                                if (zh && names.indexOf(zh) === -1) names.push(zh);
                            }
                            if (names.length > 0) return names.join(' / ');
                        }
                        if (meta.origin_country && meta.origin_country.length > 0) {
                            var names = [];
                            for (var k = 0; k < meta.origin_country.length && k < 3; k++) {
                                var code = meta.origin_country[k];
                                var zh = mapCountryCodeToArea(code, '');
                                if (zh && names.indexOf(zh) === -1) names.push(zh);
                            }
                            if (names.length > 0) return names.join(' / ');
                        }
                    }
                } catch(e) {}
            }
            return '';
        }

        function getProviderPillHtml(links) {
            if (!links || links.length === 0) {
                return '<span style="color: var(--text-muted); font-size: 11px;">无资源</span>';
            }
            var seen = {};
            var pills = [];
            for (var i = 0; i < links.length; i++) {
                var lk = links[i];
                var name = getProviderDisplayName(lk.provider, lk.link_type, lk.url);
                if (!seen[name]) {
                    seen[name] = true;
                    var cls = 'prov-pill-default';
                    if (name.indexOf('115') !== -1) cls = 'prov-pill-115';
                    else if (name.indexOf('夸克') !== -1) cls = 'prov-pill-quark';
                    else if (name.indexOf('阿里') !== -1) cls = 'prov-pill-aliyun';
                    else if (name.indexOf('百度') !== -1) cls = 'prov-pill-baidu';
                    else if (name.indexOf('迅雷') !== -1) cls = 'prov-pill-xunlei';
                    else if (name.indexOf('UC') !== -1 || name.indexOf('uc') !== -1) cls = 'prov-pill-uc';
                    else if (name === '磁力' || name === '电驴') cls = 'prov-pill-down';
                    pills.push('<span class="prov-pill ' + cls + '">' + escapeHtml(name) + '</span>');
                }
            }
            return pills.join('');
        }

        function showTablePosterHover(e, src) {
            if (!src) return;
            var popup = document.getElementById('tablePosterHoverPopup');
            var img = document.getElementById('tablePosterHoverImg');
            if (!popup || !img) return;
            img.src = src;
            popup.style.display = 'block';
            updateTablePosterHover(e);
        }

        function updateTablePosterHover(e) {
            var popup = document.getElementById('tablePosterHoverPopup');
            if (!popup || popup.style.display === 'none') return;
            var x = e.clientX + 16;
            var y = e.clientY - 120;
            var winW = window.innerWidth;
            var winH = window.innerHeight;
            if (x + 190 > winW) {
                x = e.clientX - 190;
            }
            if (y + 270 > winH) {
                y = winH - 280;
            }
            if (y < 10) y = 10;
            popup.style.left = x + 'px';
            popup.style.top = y + 'px';
        }

        function hideTablePosterHover() {
            var popup = document.getElementById('tablePosterHoverPopup');
            if (popup) popup.style.display = 'none';
        }

        function switchMovieViewMode(mode) {
            state.movieViewMode = mode;
            localStorage.setItem('juku_movie_view_mode', mode);
            var btnPoster = document.getElementById('btnViewPoster');
            var btnTable = document.getElementById('btnViewTable');
            if (mode === 'table') {
                if (btnTable) btnTable.classList.add('active');
                if (btnPoster) btnPoster.classList.remove('active');
            } else {
                if (btnPoster) btnPoster.classList.add('active');
                if (btnTable) btnTable.classList.remove('active');
                clearMovieSelection();
            }
            renderMovies();
        }

        function handleMovieSort(col) {
            if (state.movieSortBy === col) {
                state.movieSortOrder = (state.movieSortOrder === 'asc') ? 'desc' : 'asc';
            } else {
                state.movieSortBy = col;
                state.movieSortOrder = (col === 'title' || col === 'area' || col === 'directors' || col === 'actors') ? 'asc' : 'desc';
            }
            state.moviePage = 1;
            updateMovieSortIcons();
            loadMovies();
        }

        function updateMovieSortIcons() {
            var cols = ['title', 'year', 'area', 'directors', 'actors', 'resources', 'updated_at'];
            for (var i = 0; i < cols.length; i++) {
                var c = cols[i];
                var iconEl = document.getElementById('sortIcon_' + c);
                var thEl = document.getElementById('th_' + c);
                if (iconEl && thEl) {
                    if (state.movieSortBy === c) {
                        thEl.classList.add('sort-active');
                        iconEl.innerText = (state.movieSortOrder === 'asc') ? '↑' : '↓';
                    } else {
                        thEl.classList.remove('sort-active');
                        iconEl.innerText = '↕';
                    }
                }
            }
        }

        var globalMovieSearchTimer = null;
        function handleGlobalMovieSearchInput(val) {
            var clearBtn = document.getElementById('globalMovieSearchClearBtn');
            if (clearBtn) clearBtn.style.display = val ? 'block' : 'none';
            if (globalMovieSearchTimer) clearTimeout(globalMovieSearchTimer);
            globalMovieSearchTimer = setTimeout(function() {
                if (val && val.trim()) {
                    handleGlobalMovieSearchCommit();
                }
            }, 350);
        }

        function detachLibrary(libId) {
            if (!libId) return;
            var lib = null;
            if (state.libraries) {
                for (var i = 0; i < state.libraries.length; i++) {
                    if (state.libraries[i].id === libId) { lib = state.libraries[i]; break; }
                }
            }
            var libName = lib ? lib.name : '该媒体库';
            var confirmMsg = '确定要将媒体库【' + libName + '】转为个人自建媒体库吗？\n\n' +
                '• 转为自建库后，将解除与原作者的云端订阅，后续不再接收原作者的增量更新；\n' +
                '• 解除后，您将获得该库的完整管理权限（可自由添加影片、编辑/删除播放源、修改片名及删除影片等）。';
            if (!confirm(confirmMsg)) return;

            fetch('/api/private/libraries/' + libId + '/detach', {
                method: 'POST'
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (data && data.success) {
                    showToast('已成功转为个人自建媒体库，只读限制已解除！');
                    if (lib) {
                        lib.share_type = 0;
                        lib.share_code = '';
                        lib.remote_version = 0;
                        lib.creator_name = '我';
                    }
                    if (state.currentLib && state.currentLib.id === libId) {
                        state.currentLib.share_type = 0;
                        state.currentLib.share_code = '';
                        state.currentLib.remote_version = 0;
                        enterLibrary(libId);
                    } else {
                        loadLibraries();
                    }
                } else {
                    showToast('操作失败: ' + ((data && data.message) || '未知错误'));
                }
            })
            .catch(function(err) {
                showToast('请求异常: ' + err.message);
            });
        }

        // =========================================================================
        // SHA 重复文件查重与清理工作台业务逻辑
        // =========================================================================

        function openDuplicatesModal() {
            openModal('duplicatesModal');
            state.needRefreshAfterDupClose = false;

            // 监听关闭事件：当用户关闭弹窗且曾删除了数据时，自动静默刷新主列表
            var modalEl = document.getElementById('duplicatesModal');
            if (modalEl && !modalEl.__dupCloseBound) {
                modalEl.__dupCloseBound = true;
                var origClose = modalEl.querySelector('.modal-close');
                var footerClose = modalEl.querySelector('.modal-footer .btn');
                var handleClose = function() {
                    if (state.needRefreshAfterDupClose) {
                        state.needRefreshAfterDupClose = false;
                        if (typeof refreshCurrentLibrary === 'function') {
                            refreshCurrentLibrary();
                        }
                    }
                };
                if (origClose) origClose.addEventListener('click', handleClose);
                if (footerClose) footerClose.addEventListener('click', handleClose);
            }

            var chkAll = document.getElementById('dupAllLibsCheck');
            // 如果用户当前处于“全部媒体库”视图，默认勾选扫描所有库
            if (chkAll) {
                if (!state.currentLib || state.currentLib.id === 'all') {
                    chkAll.checked = true;
                } else {
                    chkAll.checked = false;
                }
            }
            var sInput = document.getElementById('dupSearchInput');
            if (sInput) sInput.value = '';
            var sClear = document.getElementById('dupSearchClear');
            if (sClear) sClear.style.display = 'none';

            loadDuplicatesList();
        }

        function loadDuplicatesList() {
            var badge = document.getElementById('dupCountBadge');
            var container = document.getElementById('duplicatesListContainer');
            if (badge) badge.innerText = '正在扫描查重...';
            if (container) {
                container.innerHTML = '<div style="text-align: center; padding: 40px 20px; color: var(--text-muted);">' +
                    '<div class="spinner" style="margin: 0 auto 12px;"></div>' +
                    '正在检索媒体库中 SHA1 相同的视频文件，请稍候...' +
                    '</div>';
            }

            var chkAll = document.getElementById('dupAllLibsCheck');
            var isAll = chkAll && chkAll.checked;
            var curLibId = (state.currentLib && state.currentLib.id !== 'all') ? state.currentLib.id : '';

            var url = '/api/private/duplicates?library_id=' + encodeURIComponent(curLibId) + (isAll ? '&all=1' : '');

            fetch(url)
                .then(function(res) { return res.json(); })
                .then(function(res) {
                    if (!res || !res.success) {
                        var errMsg = (res && res.message) || '查重请求失败';
                        if (badge) badge.innerText = '检测失败';
                        if (container) {
                            container.innerHTML = '<div style="text-align: center; padding: 40px; color: #f87171;">❌ ' + escapeHtml(errMsg) + '</div>';
                        }
                        return;
                    }

                    var data = res.data || {};
                    var groups = Array.isArray(data.groups) ? data.groups : [];
                    state.rawDuplicates = groups;

                    updateDuplicatesBadge(groups);
                    renderDuplicatesCards(groups);
                })
                .catch(function(err) {
                    if (badge) badge.innerText = '网络异常';
                    if (container) {
                        container.innerHTML = '<div style="text-align: center; padding: 40px; color: #f87171;">❌ 异常: ' + escapeHtml(err.message) + '</div>';
                    }
                });
        }

        function updateDuplicatesBadge(groups) {
            var badge = document.getElementById('dupCountBadge');
            var topBadge = document.getElementById('badgeL2Duplicates');
            var totalGroups = groups ? groups.length : 0;
            var totalItems = 0;
            if (groups) {
                for (var i = 0; i < groups.length; i++) {
                    totalItems += (groups[i].items ? groups[i].items.length : 0);
                }
            }

            if (totalGroups === 0) {
                if (badge) badge.innerHTML = '<span style="color: #34d399;">✓ 未发现重复文件</span>';
                if (topBadge) topBadge.style.display = 'none';
            } else {
                if (badge) badge.innerHTML = '共发现 <strong style="color: #f59e0b;">' + totalGroups + '</strong> 组重复文件（涉及 ' + totalItems + ' 个条目）';
                if (topBadge) {
                    topBadge.innerText = totalGroups;
                    topBadge.style.display = 'inline-block';
                }
            }
            if (typeof updateCombinedToolsBadge === 'function') {
                updateCombinedToolsBadge();
            }
        }

        function renderDuplicatesCards(groups) {
            var container = document.getElementById('duplicatesListContainer');
            if (!container) return;

            if (!groups || groups.length === 0) {
                container.innerHTML = '<div style="text-align: center; padding: 60px 20px; color: #94a3b8;">' +
                    '<div style="font-size: 42px; margin-bottom: 12px;">🎉</div>' +
                    '<div style="font-size: 16px; font-weight: 600; color: #e2e8f0; margin-bottom: 6px;">太棒了，未发现 SHA 重复的文件！</div>' +
                    '<div style="font-size: 13px; color: var(--text-muted);">当前扫描范围内所有视频文件的 SHA1 均唯一，媒体库整洁规范。</div>' +
                    '</div>';
                return;
            }

            var html = '';
            for (var gIdx = 0; gIdx < groups.length; gIdx++) {
                var g = groups[gIdx];
                var sha = g.sha1 || '';
                var shortSha = (sha.length > 16) ? (sha.substring(0, 8) + '...' + sha.substring(sha.length - 8)) : sha;
                var sizeStr = (typeof formatFileSize === 'function') ? formatFileSize(g.file_size) : (g.file_size + ' B');
                var items = Array.isArray(g.items) ? g.items : [];

                html += '<div class="dup-group-card" id="dupGroupCard_' + escapeHtml(sha) + '">';
                html += '  <div class="dup-group-header">';
                html += '    <div class="dup-group-title">';
                html += '      <span>📌 重复组 #' + (gIdx + 1) + '</span>';
                html += '      <span class="dup-sha-badge" title="SHA1: ' + escapeHtml(sha) + '">SHA1: ' + escapeHtml(shortSha) + '</span>';
                html += '      <span class="dup-size-badge">' + escapeHtml(sizeStr) + '</span>';
                html += '    </div>';
                html += '    <div style="font-size: 12px; color: var(--text-muted);">';
                html += '      共 <strong style="color: #a5b4fc;" id="dupGroupCount_' + escapeHtml(sha) + '">' + items.length + '</strong> 个条目';
                html += '    </div>';
                html += '  </div>';

                html += '  <div class="dup-items-grid">';
                for (var iIdx = 0; iIdx < items.length; iIdx++) {
                    var it = items[iIdx];
                    var coverUrl = it.movie_cover ? escapeHtml(it.movie_cover) : '';
                    var title = escapeHtml(it.movie_title || '未命名影视');
                    var year = it.movie_year ? (' (' + escapeHtml(it.movie_year) + ')') : '';
                    var typeLabel = (it.movie_type_id === 2) ? '电视剧' : (it.movie_type_id === 3 ? '动漫' : (it.movie_type_id === 4 ? '综艺' : '电影'));
                    var libName = escapeHtml(it.library_name || '媒体库');
                    var providerName = (typeof getProviderDisplayName === 'function') ? getProviderDisplayName(it.provider) : (it.provider || '网盘');
                    var fileName = escapeHtml(it.file_name || '未知文件名');
                    var remark = it.remark ? ('目录/备注: ' + escapeHtml(it.remark)) : '';
                    var isSingleSource = (it.movie_link_count <= 1);
                    var linkCount = it.movie_link_count || 1;

                    var epInfo = '';
                    if (it.season_number > 0 || it.episode_number > 0) {
                        epInfo = 'S' + String(it.season_number).padStart(2, '0') + 'E' + String(it.episode_number).padStart(2, '0');
                    }

                    var dateStr = '';
                    var ts = it.movie_updated_at || it.link_updated_at || it.movie_created_at;
                    if (ts > 0) {
                        var d = new Date(ts * 1000);
                        dateStr = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
                    }

                    html += '<div class="dup-item-card" id="dupItemCard_' + escapeHtml(it.link_id) + '">';
                    html += '  <img class="dup-item-poster" src="' + coverUrl + '" referrerpolicy="no-referrer" onerror="this.src=\'data:image/svg+xml;utf8,<svg xmlns=\\\'http://www.w3.org/2000/svg\\\' width=\\\'60\\\' height=\\\'90\\\' viewBox=\\\'0 0 60 90\\\'><rect width=\\\'60\\\' height=\\\'90\\\' fill=\\\'%231e293b\\\'/><text x=\\\'50%\\\' y=\\\'50%\\\' fill=\\\'%2364748b\\\' font-size=\\\'11\\\' text-anchor=\\\'middle\\\' dy=\\\'.3em\\\'>无封面</text></svg>\'">';
                    html += '  <div class="dup-item-info">';
                    html += '    <div class="dup-item-title-row">';
                    html += '      <span class="dup-item-title" title="' + title + '">' + title + '</span>';
                    html += '      <span style="font-size: 11px; color: #94a3b8;">' + year + '</span>';
                    html += '      <span class="movie-type-badge" style="font-size: 10px; padding: 1px 5px;">' + typeLabel + '</span>';
                    html += '      <span style="font-size: 10px; color: #a5b4fc; background: rgba(99,102,241,0.15); border: 1px solid rgba(99,102,241,0.3); border-radius: 4px; padding: 1px 5px;" title="所属媒体库">' + libName + '</span>';
                    html += '    </div>';

                    html += '    <div class="dup-item-meta">';
                    html += '      <span style="color: #38bdf8;">[' + escapeHtml(providerName) + ']</span>';
                    if (epInfo) {
                        html += '      <span style="color: #fbbf24; font-weight: 600;">' + epInfo + '</span>';
                    }
                    if (dateStr) {
                        html += '      <span style="font-size: 11px; color: #64748b;">更新: ' + dateStr + '</span>';
                    }
                    html += '    </div>';

                    html += '    <div class="dup-item-file" title="' + fileName + '">📄 ' + fileName + '</div>';
                    if (remark) {
                        html += '    <div class="dup-item-path" title="' + remark + '">' + remark + '</div>';
                    }

                    html += '    <div class="dup-item-actions">';
                    if (isSingleSource) {
                        html += '      <span class="dup-status-tag dup-status-warn" title="该影片名下仅此 1 个播放源，删除将移出该影片">⚠️ 仅此1个源</span>';
                    } else {
                        html += '      <span class="dup-status-tag dup-status-info" title="该影片拥有多个播放源，删除仅移出此链接">ℹ️ 共 ' + linkCount + ' 个播放源</span>';
                    }
                    html += '      <button class="btn-dup-delete" onclick="handleDeleteDuplicateItem(this, \'' + escapeHtml(it.link_id) + '\', \'' + escapeHtml(it.movie_id) + '\', \'' + escapeHtml(it.movie_title || '') + '\', ' + linkCount + ', \'' + escapeHtml(sha) + '\')">';
                    html += '        🗑️ 移出此项';
                    html += '      </button>';
                    html += '    </div>';
                    html += '  </div>';
                    html += '</div>';
                }
                html += '  </div>';
                html += '</div>';
            }

            container.innerHTML = html;
        }

        function filterDuplicatesDisplay() {
            var sInput = document.getElementById('dupSearchInput');
            var sClear = document.getElementById('dupSearchClear');
            var kw = sInput ? sInput.value.trim().toLowerCase() : '';
            if (sClear) sClear.style.display = kw ? 'inline-block' : 'none';

            if (!state.rawDuplicates) return;
            if (!kw) {
                renderDuplicatesCards(state.rawDuplicates);
                return;
            }

            var filtered = [];
            for (var i = 0; i < state.rawDuplicates.length; i++) {
                var g = state.rawDuplicates[i];
                var matchedItems = [];
                for (var j = 0; j < (g.items || []).length; j++) {
                    var it = g.items[j];
                    var text = (it.movie_title + ' ' + it.file_name + ' ' + it.remark + ' ' + it.library_name + ' ' + (it.sha1 || '')).toLowerCase();
                    if (text.indexOf(kw) !== -1) {
                        matchedItems.push(it);
                    }
                }
                if (matchedItems.length > 0) {
                    var gClone = Object.assign({}, g, { items: matchedItems });
                    filtered.push(gClone);
                }
            }
            renderDuplicatesCards(filtered);
        }

        function clearDupSearch() {
            var sInput = document.getElementById('dupSearchInput');
            if (sInput) sInput.value = '';
            var sClear = document.getElementById('dupSearchClear');
            if (sClear) sClear.style.display = 'none';
            if (state.rawDuplicates) {
                renderDuplicatesCards(state.rawDuplicates);
            }
        }

        function handleDeleteDuplicateItem(btn, linkId, movieId, movieTitle, linkCount, sha1) {
            var confirmMsg = (linkCount <= 1)
                ? ('确定要移出《' + movieTitle + '》下的该重复文件吗？\n\n' +
                   '• 注意：该影片名下仅此 1 个播放源，移出后将同步从媒体库中清理该影片；\n' +
                   '• 网盘内的真实物理文件不受任何影响。')
                : ('确定要移出《' + movieTitle + '》名下的该条重复播放链接吗？\n\n' +
                   '• 该影片仍保留其余 ' + (linkCount - 1) + ' 个播放源，仅删除本次指定的重复链接条目；\n' +
                   '• 网盘内的真实物理文件不受任何影响。');

            if (!confirm(confirmMsg)) return;

            btn.disabled = true;
            btn.innerText = '正在移出...';

            var deleteUrl = (linkCount <= 1)
                ? ('/api/private/movies/' + movieId)
                : ('/api/private/links/' + linkId);

            fetch(deleteUrl, { method: 'DELETE' })
                .then(function(res) { return res.json(); })
                .then(function(res) {
                    if (res && res.success) {
                        state.needRefreshAfterDupClose = true;
                        showToast('已成功移出该重复条目！');

                        // 局部淡出删除卡片
                        var itemCard = document.getElementById('dupItemCard_' + linkId);
                        if (itemCard) {
                            itemCard.style.transition = 'all 0.3s ease';
                            itemCard.style.opacity = '0';
                            itemCard.style.transform = 'scale(0.95)';
                            setTimeout(function() {
                                if (itemCard.parentNode) itemCard.parentNode.removeChild(itemCard);
                            }, 300);
                        }

                        // 更新内存中的 rawDuplicates
                        if (state.rawDuplicates) {
                            for (var gIdx = 0; gIdx < state.rawDuplicates.length; gIdx++) {
                                var g = state.rawDuplicates[gIdx];
                                if (g.sha1 === sha1 && Array.isArray(g.items)) {
                                    g.items = g.items.filter(function(it) { return it.link_id !== linkId; });
                                    var countEl = document.getElementById('dupGroupCount_' + sha1);
                                    if (countEl) countEl.innerText = g.items.length;

                                    // 如果该组剩余条目 <= 1，说明该 SHA 已经不再构成重复
                                    if (g.items.length <= 1) {
                                        var groupCard = document.getElementById('dupGroupCard_' + sha1);
                                        if (groupCard) {
                                            groupCard.style.transition = 'all 0.4s ease';
                                            groupCard.style.opacity = '0';
                                            groupCard.style.transform = 'translateY(-10px)';
                                            setTimeout(function() {
                                                if (groupCard.parentNode) groupCard.parentNode.removeChild(groupCard);
                                            }, 400);
                                        }
                                        state.rawDuplicates.splice(gIdx, 1);
                                    }
                                    break;
                                }
                            }
                            updateDuplicatesBadge(state.rawDuplicates);
                        }
                    } else {
                        btn.disabled = false;
                        btn.innerText = '🗑️ 移出此项';
                        showToast('移出失败: ' + ((res && res.message) || '未知错误'));
                    }
                })
                .catch(function(err) {
                    btn.disabled = false;
                    btn.innerText = '🗑️ 移出此项';
                    showToast('请求异常: ' + err.message);
                });
        }



        function handleGlobalMovieSearchCommit() {
            if (globalMovieSearchTimer) clearTimeout(globalMovieSearchTimer);
            var input = document.getElementById('globalMovieSearchInput');
            var kw = input ? input.value.trim() : '';
            var typeSel = document.getElementById('globalMovieTypeFilter');
            var typeId = typeSel ? parseInt(typeSel.value, 10) || 0 : 0;
            handleGlobalMovieSearch(kw, typeId);
        }

        function clearGlobalMovieSearch() {
            var input = document.getElementById('globalMovieSearchInput');
            if (input) input.value = '';
            var clearBtn = document.getElementById('globalMovieSearchClearBtn');
            if (clearBtn) clearBtn.style.display = 'none';
        }

        function handleGlobalMovieTypeFilter(val) {
            var input = document.getElementById('globalMovieSearchInput');
            var kw = input ? input.value.trim() : '';
            var typeId = parseInt(val, 10) || 0;
            handleGlobalMovieSearch(kw, typeId);
        }

        function updateLevel2ActionButtonsForGlobal(isGlobal) {
            var dropdownImport = document.getElementById('dropdownL2ImportWrapper');
            var btnSearch = document.getElementById('btnL2Search');
            var btnUnmatched = document.getElementById('btnL2Unmatched');
            var btnSyncDirs = document.getElementById('btnL2SyncDirs');
            var btnShare = document.getElementById('btnL2Share');
            var btnSync = document.getElementById('btnL2Sync');
            var btnDetach = document.getElementById('btnL2Detach');
            var btnRefresh = document.getElementById('btnL2Refresh');

            if (btnRefresh) {
                btnRefresh.title = isGlobal ? '刷新全部私有库影片' : '刷新当前媒体库影片与状态';
            }

            if (isGlobal) {
                if (dropdownImport) dropdownImport.style.display = 'none';
                if (btnSearch) btnSearch.style.display = 'none';
                if (btnUnmatched) btnUnmatched.style.display = 'none';
                if (btnSyncDirs) btnSyncDirs.style.display = 'none';
                if (btnShare) btnShare.style.display = 'none';
                if (btnSync) btnSync.style.display = 'none';
                if (btnDetach) btnDetach.style.display = 'none';
            } else {
                if (dropdownImport) dropdownImport.style.display = 'inline-block';
                if (btnSearch) btnSearch.style.display = 'inline-flex';
                if (btnUnmatched) btnUnmatched.style.display = 'flex';
                if (btnSyncDirs) btnSyncDirs.style.display = 'flex';
                if (btnShare) btnShare.style.display = 'flex';
            }
            if (typeof updateCombinedToolsBadge === 'function') {
                updateCombinedToolsBadge();
            }
        }

        function handleGlobalMovieSearch(keyword, typeId) {
            keyword = (keyword || '').trim();
            typeId = parseInt(typeId, 10) || 0;

            state.currentLib = { id: 'all', name: '全部私有库', is_all: true };
            state.currentLevel = 2;

            document.getElementById('viewLevel1').style.display = 'none';
            document.getElementById('viewLevel2').style.display = 'block';
            document.getElementById('viewLevel3').style.display = 'none';
            document.getElementById('headerBackBtn').style.display = 'inline-flex';
            document.getElementById('pageMainTitle').innerText = '全部私有库影片';
            document.getElementById('currentLibName').innerText = '全部私有库';
            var metaEl = document.getElementById('currentLibMeta');
            if (metaEl) metaEl.innerText = '跨全部媒体库检索';

            updateLevel2ActionButtonsForGlobal(true);

            // 同步 Level 2 搜索框与类型过滤器
            state.movieKeyword = keyword;
            state.movieTypeFilter = typeId;
            state.moviePage = 1;

            var searchInp = document.getElementById('movieSearchInput');
            if (searchInp) {
                searchInp.value = keyword;
                searchInp.placeholder = '在全部私有库中搜索片名 / 导演 / 演员...';
            }
            var clearBtn = document.getElementById('movieSearchClearBtn');
            if (clearBtn) clearBtn.style.display = keyword ? 'block' : 'none';

            var typeSel = document.getElementById('movieTypeFilter');
            if (typeSel) typeSel.value = String(typeId);

            var sizeSel = document.getElementById('moviePageSizeSelect');
            if (sizeSel) sizeSel.value = String(state.moviePageSize);

            // 同步视图按钮
            var btnPoster = document.getElementById('btnViewPoster');
            var btnTable = document.getElementById('btnViewTable');
            if (state.movieViewMode === 'table') {
                if (btnTable) btnTable.classList.add('active');
                if (btnPoster) btnPoster.classList.remove('active');
            } else {
                if (btnPoster) btnPoster.classList.add('active');
                if (btnTable) btnTable.classList.remove('active');
            }
            updateMovieSortIcons();

            loadMovies();
        }

        var movieSearchTimer = null;
        function handleMovieSearchInput(val) {
            var clearBtn = document.getElementById('movieSearchClearBtn');
            if (clearBtn) clearBtn.style.display = val ? 'block' : 'none';
            if (movieSearchTimer) clearTimeout(movieSearchTimer);
            movieSearchTimer = setTimeout(function() {
                state.movieKeyword = (val || '').trim();
                state.moviePage = 1;
                loadMovies();
            }, 300);
        }

        function handleMovieSearchCommit() {
            if (movieSearchTimer) clearTimeout(movieSearchTimer);
            var input = document.getElementById('movieSearchInput');
            state.movieKeyword = input ? input.value.trim() : '';
            state.moviePage = 1;
            loadMovies();
        }

        function clearMovieSearch() {
            var input = document.getElementById('movieSearchInput');
            if (input) input.value = '';
            var clearBtn = document.getElementById('movieSearchClearBtn');
            if (clearBtn) clearBtn.style.display = 'none';
            state.movieKeyword = '';
            state.moviePage = 1;
            loadMovies();
        }

        function handleMovieTypeFilter(val) {
            state.movieTypeFilter = parseInt(val, 10) || 0;
            state.moviePage = 1;
            loadMovies();
        }

        function handleMoviePageSizeChange(val) {
            var ps = parseInt(val, 10) || 100;
            state.moviePageSize = ps;
            localStorage.setItem('juku_movie_page_size', String(ps));
            state.moviePage = 1;
            loadMovies();
        }

        function goToMoviePage(p) {
            if (p < 1) p = 1;
            if (p > state.movieTotalPages) p = state.movieTotalPages;
            if (p === state.moviePage) return;
            state.moviePage = p;
            loadMovies();
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }

        function jumpToMoviePage(e) {
            if (e.key === 'Enter') {
                var val = parseInt(e.target.value, 10);
                if (!isNaN(val)) {
                    goToMoviePage(val);
                }
            }
        }

        function renderPaginationBar() {
            var bar = document.getElementById('moviePaginationBar');
            if (!bar) return;
            if (state.movieTotal <= 0) {
                bar.style.display = 'none';
                return;
            }
            bar.style.display = 'flex';
            bar.style.alignItems = 'center';
            bar.style.justifyContent = 'space-between';
            bar.style.padding = '14px 16px';
            bar.style.marginTop = '16px';
            bar.style.borderTop = '1px solid var(--card-border)';
            bar.style.flexWrap = 'wrap';
            bar.style.gap = '12px';

            var cur = state.moviePage;
            var totalPages = state.movieTotalPages || 1;
            var totalItems = state.movieTotal;
            var startIdx = (cur - 1) * state.moviePageSize + 1;
            var endIdx = Math.min(cur * state.moviePageSize, totalItems);

            var html = '';
            html += '<div style="font-size: 13px; color: var(--text-muted);">';
            html += '显示第 <span style="color: #fff; font-weight: 600;">' + startIdx + ' - ' + endIdx + '</span> 条，共 <span style="color: #6366f1; font-weight: 700;">' + totalItems + '</span> 条';
            html += '</div>';

            html += '<div style="display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">';
            html += '<button class="pagination-btn" onclick="goToMoviePage(1)" ' + (cur <= 1 ? 'disabled' : '') + ' title="第一页">« 首页</button>';
            html += '<button class="pagination-btn" onclick="goToMoviePage(' + (cur - 1) + ')" ' + (cur <= 1 ? 'disabled' : '') + ' title="上一页">‹ 上页</button>';

            var maxButtons = 5;
            var startP = Math.max(1, cur - Math.floor(maxButtons / 2));
            var endP = Math.min(totalPages, startP + maxButtons - 1);
            if (endP - startP + 1 < maxButtons) {
                startP = Math.max(1, endP - maxButtons + 1);
            }

            if (startP > 1) {
                html += '<span style="color: var(--text-muted); padding: 0 4px;">...</span>';
            }

            for (var p = startP; p <= endP; p++) {
                var activeCls = (p === cur) ? 'active' : '';
                html += '<button class="pagination-btn ' + activeCls + '" onclick="goToMoviePage(' + p + ')">' + p + '</button>';
            }

            if (endP < totalPages) {
                html += '<span style="color: var(--text-muted); padding: 0 4px;">...</span>';
            }

            html += '<button class="pagination-btn" onclick="goToMoviePage(' + (cur + 1) + ')" ' + (cur >= totalPages ? 'disabled' : '') + ' title="下一页">下页 ›</button>';
            html += '<button class="pagination-btn" onclick="goToMoviePage(' + totalPages + ')" ' + (cur >= totalPages ? 'disabled' : '') + ' title="最后页">末页 »</button>';

            html += '<div style="display: flex; align-items: center; gap: 4px; margin-left: 6px; font-size: 12px; color: var(--text-muted);">';
            html += '<span>跳至</span>';
            html += '<input type="number" min="1" max="' + totalPages + '" value="' + cur + '" onkeydown="jumpToMoviePage(event)" style="width: 48px; height: 28px; text-align: center; border-radius: 4px; border: 1px solid var(--card-border); background: rgba(255,255,255,0.05); color: #fff; font-size: 12px; padding: 0 4px;">';
            html += '<span>/' + totalPages + ' 页</span>';
            html += '</div>';

            html += '</div>';

            bar.innerHTML = html;
        }

        function loadMovies() {
            if (!state.currentLib) return;
            state.selectedMovieIds = [];
            updateBatchBarUI();
            var params = new URLSearchParams();
            params.set('page', state.moviePage);
            params.set('page_size', state.moviePageSize);
            if (state.movieKeyword && state.movieKeyword.trim()) {
                params.set('keyword', state.movieKeyword.trim());
            }
            if (state.movieTypeFilter > 0) {
                params.set('type_id', state.movieTypeFilter);
            }
            if (state.movieSortBy) {
                params.set('sort_by', state.movieSortBy);
                params.set('sort_order', state.movieSortOrder || 'desc');
            }

            var url = '/api/private/libraries/' + state.currentLib.id + '/movies?' + params.toString();
            fetch(url)
                .then(function(res) { return res.json(); })
                .then(function(data) {
                    if (data && data.data && typeof data.data === 'object' && !Array.isArray(data.data)) {
                        state.movies = data.data.items || [];
                        state.movieTotal = data.data.total || 0;
                        state.episodeTotal = (data.data.episode_total !== undefined) ? data.data.episode_total : (data.data.total_episodes || 0);
                        state.linkTotal = (data.data.link_total !== undefined) ? data.data.link_total : (data.data.total_links || 0);
                        state.moviePage = data.data.page || 1;
                        state.moviePageSize = data.data.page_size || 100;
                        state.movieTotalPages = data.data.total_pages || 1;
                    } else {
                        state.movies = Array.isArray(data.data) ? data.data : [];
                        state.movieTotal = state.movies.length;
                        state.episodeTotal = 0;
                        state.linkTotal = 0;
                        state.movieTotalPages = 1;
                    }
                    if (state.movies.length === 0 && state.moviePage > 1 && state.movieTotal > 0) {
                        state.moviePage = Math.max(1, Math.ceil(state.movieTotal / state.moviePageSize));
                        loadMovies();
                        return;
                    }
                    renderMovies();
                })
                .catch(function(err) {
                    showToast('加载影片失败: ' + err.message);
                });
        }

        function isSeriesTypeId(typeId) {
            var tid = parseInt(typeId, 10);
            // 2: 电视剧, 3: 动漫, 4: 综艺 在云端数据库与 TMDB 上均为按季/期/集连载的 TV 剧集系列
            return tid === 2 || tid === 3 || tid === 4;
        }

        function checkIsSeries(movie, links) {
            if (!movie) return false;
            var tid = parseInt(movie.type_id, 10);
            // 电影类型绝对神圣不可侵犯：如果明确是电影 (type_id === 1)，严禁被篡改识别为剧集
            if (tid === 1) return false;
            if (isSeriesTypeId(tid)) return true;

            // 如果已有抓取到的 TMDB 深度元数据且明确包含多季多集
            if (movie.extra_meta_json) {
                try {
                    var meta = JSON.parse(movie.extra_meta_json);
                    if (meta && (meta.total_episodes > 1 || (meta.seasons && meta.seasons.length > 1))) {
                        return true;
                    }
                } catch(e) {}
            }

            // 检查链接列表中是否存在真实的多集或多季特征（实质重于形式）
            // 严禁因为数据库默认的 season_number=1 或 episode_number=1 就把单部电影误判为剧集！
            var targetLinks = links || movie.links;
            if (targetLinks && targetLinks.length > 0) {
                var seasonSet = {};
                var epSet = {};
                var hasMultiSeasonOrEp = false;
                for (var i = 0; i < targetLinks.length; i++) {
                    var lk = targetLinks[i];
                    var s = (lk.season_number !== undefined && lk.season_number !== null && lk.season_number >= 0) ? lk.season_number : 1;
                    var e = (lk.episode_number && lk.episode_number > 0) ? lk.episode_number : 1;
                    if (s > 1 || e > 1 || (s === 0 && e > 0)) {
                        hasMultiSeasonOrEp = true;
                    }
                    seasonSet[s] = true;
                    epSet[s + '_' + e] = true;
                }
                // 只有当存在大于第 1 季、大于第 1 集，或者存在多个不同集时，才识别为剧集！
                if (hasMultiSeasonOrEp || Object.keys(epSet).length > 1 || Object.keys(seasonSet).length > 1) {
                    return true;
                }
            }

            return false;
        }

        function renderMovies() {
            var isSubLib = isCurrentLibReadOnly();
            var isGlobal = Boolean(state.currentLib && state.currentLib.id === 'all');
            var metaText = '共 ' + state.movieTotal + ' 部影片 · ' + (state.episodeTotal || 0) + ' 个单集 · ' + (state.linkTotal || 0) + ' 个链接';
            if (isGlobal) {
                metaText += ' · 🌐 全部私有库聚合';
            } else if (isSubLib) {
                metaText += ' · 🔒 持续更新订阅库 (只读)';
            }
            if (state.movieKeyword) {
                metaText += ' · 搜索: "' + escapeHtml(state.movieKeyword) + '"';
            }
            document.getElementById('currentLibMeta').innerHTML = metaText;

            var isTable = (state.movieViewMode === 'table');
            var grid = document.getElementById('movieListGrid');
            var tableContainer = document.getElementById('movieTableContainer');
            var tableBody = document.getElementById('movieTableBody');

            if (isTable) {
                grid.style.display = 'none';
                tableContainer.style.display = 'block';
            } else {
                grid.style.display = 'grid';
                tableContainer.style.display = 'none';
            }

            if (state.movies.length === 0) {
                var emptyTip = isSubLib ? '点击右上角【🔄 检查并同步最新内容】从作者处拉取片单' : '点击右上角【🔍 搜索添加片子】、【📊 表格导入】或【📝 文本/粘贴导入】';
                if (state.movieKeyword || state.movieTypeFilter > 0) {
                    if (!isGlobal && state.movieKeyword) {
                        emptyTip = '在当前媒体库【' + escapeHtml(state.currentLib ? state.currentLib.name : '') + '】中未找到符合条件的影片。<br><button class="btn btn-secondary" style="margin-top: 10px; font-size: 12px; padding: 5px 14px; display: inline-flex; align-items: center; gap: 6px;" onclick="handleGlobalMovieSearch(\'' + escapeHtml(state.movieKeyword).replace(/'/g, "\\'") + '\', ' + state.movieTypeFilter + ')">🔍 在全部私有库中搜索 "' + escapeHtml(state.movieKeyword) + '"</button>';
                    } else {
                        emptyTip = isGlobal ? '全部私有库中未找到符合条件的影片，请尝试更换搜索词或筛选条件' : '未找到符合条件的影片，请尝试更换搜索词或筛选条件';
                    }
                }
                if (isTable) {
                    tableBody.innerHTML = '<tr><td colspan="11" style="text-align: center; padding: 48px 16px; color: var(--text-muted);"><div style="font-size: 28px; margin-bottom: 8px;">🎬</div><div style="font-size: 15px; font-weight: 600; color: #fff; margin-bottom: 6px;">' + (isGlobal ? '全部私有库暂无匹配影片' : '库内暂无匹配影片') + '</div><div>' + emptyTip + '</div></td></tr>';
                } else {
                    grid.innerHTML = '<div class="empty-state" style="grid-column: 1 / -1;"><div class="empty-icon">🎬</div><div style="font-size: 16px; font-weight: 600; color: #fff;">' + (isGlobal ? '全部私有库暂无匹配影片' : '库内暂无匹配影片') + '</div><div>' + emptyTip + '</div></div>';
                }
                updateBatchBarUI();
                renderPaginationBar();
                return;
            }

            if (!isTable) {
                // 海报墙模式渲染
                var html = '';
                for (var i = 0; i < state.movies.length; i++) {
                    var m = state.movies[i];
                    var cover = formatProxiedImgUrl(m.cover_url || PRESET_COVERS[0]);
                    var linksCount = (m.links && m.links.length) || 0;
                    var isTV = checkIsSeries(m, m.links);
                    var seasonSet = {};
                    var epSet = {};

                    if (m.links && m.links.length > 0) {
                        for (var lIdx = 0; lIdx < m.links.length; lIdx++) {
                            var lk = m.links[lIdx];
                            var sNum = (lk.season_number !== undefined && lk.season_number !== null && lk.season_number >= 0) ? lk.season_number : 1;
                            var eNum = lk.episode_number > 0 ? lk.episode_number : 1;
                            seasonSet[sNum] = true;
                            epSet[sNum + '_' + eNum] = true;
                        }
                    }
                    var totalSeasons = Object.keys(seasonSet).length;
                    var totalEpisodes = Object.keys(epSet).length;

                    var badgeText = linksCount + ' 源';
                    if (isTV) {
                        if (totalSeasons > 0 && totalEpisodes > 0) {
                            badgeText = '全 ' + totalSeasons + ' 季全 ' + totalEpisodes + ' 集';
                        } else {
                            badgeText = '剧集';
                        }
                    }
                    var isMovieReadOnlyFlag = isMovieReadOnly(m);
                    var rebindHtml = isMovieReadOnlyFlag ? '' : '<span style="color: #38bdf8; cursor: pointer; margin-right: 8px;" onclick="event.stopPropagation(); openRebindMovieModal(\'' + m.id + '\')">识别</span>';
                    var copyHtml = '<span style="color: #a5b4fc; cursor: pointer; margin-right: 8px;" onclick="event.stopPropagation(); openCopyMovieModal(\'' + m.id + '\', \'' + escapeHtml(m.title).replace(/'/g, "\\'") + '\')">复制</span>';
                    var delHtml = isMovieReadOnlyFlag ? '' : '<span style="color: #fca5a5; cursor: pointer;" onclick="event.stopPropagation(); deleteMovie(\'' + m.id + '\')">移出</span>';
                    var tvTag = '';
                    if (isTV) {
                        var tid = parseInt(m.type_id, 10);
                        var tLabel = '剧集';
                        if (tid === 2) tLabel = '电视剧';
                        else if (tid === 3) tLabel = '动漫';
                        else if (tid === 4) tLabel = '综艺';
                        else if (tid === 5) tLabel = '纪录片';
                        tvTag = '<span style="font-size: 11px; padding: 1px 5px; border-radius: 4px; background: rgba(56, 189, 248, 0.2); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.4); margin-right: 4px;">' + tLabel + '</span>';
                    }

                    var libBadge = '';
                    if (m.library_name && (!state.currentLib || state.currentLib.id === 'all')) {
                        libBadge = '<div class="movie-badge-lib" onclick="event.stopPropagation(); enterLibraryDirect(\'' + m.library_id + '\')" title="所属媒体库：' + escapeHtml(m.library_name) + ' (点击直达该库)">📁 ' + escapeHtml(m.library_name) + '</div>';
                    }

                    var userPanTag = '';
                    if (m.has_user_pan || (m.links && m.links.some(function(l){ return l.link_type === 'user_pan' || (l.url && l.url.indexOf('user_pan://') === 0); }))) {
                        userPanTag = '<span style="display: inline-block; font-size: 10px; padding: 1px 4px; border-radius: 4px; background: rgba(168, 85, 247, 0.25); color: #c084fc; border: 1px solid rgba(168, 85, 247, 0.4); margin-left: 4px; font-weight: 600; vertical-align: middle;">个人盘</span>';
                    }

                    html += '<div class="movie-card" onclick="enterMovie(\'' + m.id + '\')">';
                    html += '<div class="movie-poster-box"><img referrerpolicy="no-referrer" src="' + cover + '" class="movie-poster"><div class="movie-badge-links">' + badgeText + '</div>' + libBadge + '</div>';
                    html += '<div class="movie-info"><div class="movie-title">' + tvTag + escapeHtml(m.title) + userPanTag + '</div>';
                    html += '<div class="movie-meta-sub"><span>' + (escapeHtml(m.year) || '未知年份') + '</span><div>' + rebindHtml + copyHtml + delHtml + '</div></div>';
                    html += '</div></div>';
                }
                grid.innerHTML = html;
            } else {
                // 详细表格模式渲染
                var tHtml = '';
                for (var i = 0; i < state.movies.length; i++) {
                    var m = state.movies[i];
                    var cover = formatProxiedImgUrl(m.cover_url || PRESET_COVERS[0]);
                    var isTV = checkIsSeries(m, m.links);

                    var tid = parseInt(m.type_id, 10);
                    var tLabel = '电影';
                    var tStyle = 'border: 1px solid rgba(148, 163, 184, 0.3); background: rgba(148, 163, 184, 0.15); color: #cbd5e1;';
                    if (tid === 2) {
                        tLabel = '电视剧';
                        tStyle = 'border: 1px solid rgba(56, 189, 248, 0.4); background: rgba(56, 189, 248, 0.2); color: #38bdf8;';
                    } else if (tid === 3) {
                        tLabel = '动漫';
                        tStyle = 'border: 1px solid rgba(236, 72, 153, 0.4); background: rgba(236, 72, 153, 0.2); color: #f472b6;';
                    } else if (tid === 4) {
                        tLabel = '综艺';
                        tStyle = 'border: 1px solid rgba(245, 158, 11, 0.4); background: rgba(245, 158, 11, 0.2); color: #fbbf24;';
                    } else if (tid === 5) {
                        tLabel = '纪录片';
                        tStyle = 'border: 1px solid rgba(52, 211, 153, 0.4); background: rgba(52, 211, 153, 0.2); color: #34d399;';
                    }
                    var typeTag = '<span style="display: inline-block; font-size: 11px; padding: 1px 5px; border-radius: 4px; ' + tStyle + ' font-weight: 600; flex-shrink: 0;">' + tLabel + '</span>';

                    var seasonSet = {};
                    var epSet = {};
                    if (m.links && m.links.length > 0) {
                        for (var lIdx = 0; lIdx < m.links.length; lIdx++) {
                            var lk = m.links[lIdx];
                            var sNum = (lk.season_number !== undefined && lk.season_number !== null && lk.season_number >= 0) ? lk.season_number : 1;
                            var eNum = lk.episode_number > 0 ? lk.episode_number : 1;
                            seasonSet[sNum] = true;
                            epSet[sNum + '_' + eNum] = true;
                        }
                    }
                    var totalSeasons = Object.keys(seasonSet).length;
                    var totalEpisodes = Object.keys(epSet).length;
                    var epInfo = '';
                    if (isTV) {
                        if (totalSeasons > 0 && totalEpisodes > 0) {
                            epInfo = '<div style="font-size: 11px; color: #38bdf8; margin-top: 3px; font-weight: 500;">全 ' + totalSeasons + ' 季全 ' + totalEpisodes + ' 集</div>';
                        } else {
                            epInfo = '<div style="font-size: 11px; color: #38bdf8; margin-top: 3px; font-weight: 500;">剧集</div>';
                        }
                    } else {
                        epInfo = '<div style="font-size: 11px; color: var(--text-muted); margin-top: 3px;">' + (m.links ? m.links.length : 0) + ' 个播放源</div>';
                    }

                    var provPills = getProviderPillHtml(m.links);
                    var isMovieReadOnlyFlag = isMovieReadOnly(m);
                    var delBtn = isMovieReadOnlyFlag ? '' : '<button class="btn btn-secondary" style="padding: 3px 8px; font-size: 11px; color: #fca5a5; border-color: rgba(239,68,68,0.3); border-radius: 4px;" onclick="event.stopPropagation(); deleteMovie(\'' + m.id + '\')">移出</button>';
                    var copyBtn = '<button class="btn btn-secondary" style="padding: 3px 8px; font-size: 11px; margin-right: 4px; border-radius: 4px; color: #a5b4fc; border-color: rgba(99,102,241,0.3);" onclick="event.stopPropagation(); openCopyMovieModal(\'' + m.id + '\', \'' + escapeHtml(m.title).replace(/'/g, "\\'") + '\')">复制</button>';
                    var detailBtn = '<button class="btn btn-secondary" style="padding: 3px 8px; font-size: 11px; margin-right: 4px; border-radius: 4px; color: #38bdf8; border-color: rgba(56,189,248,0.3);" onclick="event.stopPropagation(); showMovieTmdbDetail(\'' + m.id + '\')">详情</button>';
                    var rebindBtn = isMovieReadOnlyFlag ? '' : '<button class="btn btn-secondary" style="padding: 3px 8px; font-size: 11px; margin-right: 4px; border-radius: 4px; color: #38bdf8; border-color: rgba(56,189,248,0.3);" onclick="event.stopPropagation(); openRebindMovieModal(\'' + m.id + '\')">🎯 识别</button>';

                    var origTitleHtml = (m.original_name && m.original_name !== m.title) ? '<div style="font-size: 11px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 240px; margin-top: 1px;" title="' + escapeHtml(m.original_name) + '">' + escapeHtml(m.original_name) + '</div>' : '';

                    var genresHtml = m.genres ? '<div style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">' + escapeHtml(m.genres) + '</div>' : '';

                    var areaStr = getMovieCountry(m);

                    var tmdbBadge = (m.tmdb_id > 0) ? '<span class="tmdb-badge" style="cursor: pointer; font-size: 10px; padding: 1px 5px; border-radius: 3px; background: rgba(99,102,241,0.25); color: #a5b4fc; border: 1px solid rgba(99,102,241,0.4); margin-left: 6px; font-weight: 600; vertical-align: middle;" onclick="event.stopPropagation(); showMovieTmdbDetail(\'' + m.id + '\')" title="点击查看 TMDB 详细信息与官方主页">TMDB ↗</span>' : '';

                    var userPanTag = '';
                    if (m.has_user_pan || (m.links && m.links.some(function(l){ return l.link_type === 'user_pan' || (l.url && l.url.indexOf('user_pan://') === 0); }))) {
                        userPanTag = '<span style="display: inline-block; font-size: 10px; padding: 1px 4px; border-radius: 4px; background: rgba(168, 85, 247, 0.25); color: #c084fc; border: 1px solid rgba(168, 85, 247, 0.4); margin-left: 4px; font-weight: 600; vertical-align: middle;">个人盘</span>';
                    }

                    var libTag = '';
                    if (m.library_name && (!state.currentLib || state.currentLib.id === 'all')) {
                        libTag = '<span class="movie-lib-pill" onclick="event.stopPropagation(); enterLibraryDirect(\'' + m.library_id + '\')" title="所属媒体库：' + escapeHtml(m.library_name) + ' (点击直达该库)">📁 ' + escapeHtml(m.library_name) + '</span>';
                    }

                    var isChecked = (state.selectedMovieIds && state.selectedMovieIds.indexOf(m.id) !== -1);
                    var cbHtml = '<input type="checkbox" class="movie-select-cb" data-id="' + m.id + '" ' + (isChecked ? 'checked' : '') + ' onchange="handleMovieSelectChange(event, \'' + m.id + '\')" onclick="event.stopPropagation()" title="选择 / 取消选择">';

                    tHtml += '<tr onclick="enterMovie(\'' + m.id + '\')" class="' + (isChecked ? 'tr-selected' : '') + '" id="tr_movie_' + m.id + '">';
                    tHtml += '<td style="text-align: center; padding: 6px 4px;" onclick="event.stopPropagation();">' + cbHtml + '</td>';
                    tHtml += '<td style="text-align: center; padding: 6px 8px;"><div class="table-thumb-cell"><img referrerpolicy="no-referrer" src="' + cover + '" onmouseenter="showTablePosterHover(event, this.src)" onmousemove="updateTablePosterHover(event)" onmouseleave="hideTablePosterHover()"></div></td>';
                    tHtml += '<td style="padding: 8px 12px;"><div style="display: flex; align-items: center; flex-wrap: wrap; gap: 4px;"><span style="font-weight: 700; color: #fff; font-size: 13px;">' + escapeHtml(m.title) + '</span>' + tmdbBadge + userPanTag + libTag + '</div>' + origTitleHtml + genresHtml + '</td>';
                    tHtml += '<td style="text-align: center; padding: 8px;">' + typeTag + '</td>';
                    tHtml += '<td style="padding: 8px; font-size: 12px; color: #cbd5e1; text-align: center;">' + escapeHtml(m.year || '-') + '</td>';
                    tHtml += '<td style="padding: 8px; font-size: 12px; color: #cbd5e1; max-width: 110px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="' + escapeHtml(areaStr || '-') + '">' + escapeHtml(areaStr || '-') + '</td>';
                    tHtml += '<td style="padding: 8px; font-size: 12px; color: #cbd5e1; max-width: 110px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="' + escapeHtml(m.directors || '-') + '">' + escapeHtml(m.directors || '-') + '</td>';
                    tHtml += '<td style="padding: 8px; font-size: 12px; color: var(--text-muted); max-width: 180px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="' + escapeHtml(m.actors || '-') + '">' + escapeHtml(m.actors || '-') + '</td>';
                    tHtml += '<td style="padding: 8px;"><div style="line-height: 1.2;">' + provPills + '</div>' + epInfo + '</td>';
                    tHtml += '<td style="padding: 8px; font-size: 11px; color: var(--text-muted); white-space: nowrap;">' + formatDateTime(m.updated_at || m.created_at) + '</td>';
                    tHtml += '<td style="text-align: center; padding: 8px; white-space: nowrap;" onclick="event.stopPropagation();">' + detailBtn + rebindBtn + copyBtn + delBtn + '</td>';
                    tHtml += '</tr>';
                }
                tableBody.innerHTML = tHtml;
            }

            updateBatchBarUI();
            renderPaginationBar();
        }

        function deleteMovie(movieId) {
            if (checkReadOnlyGuard()) return;
            if (!confirm('确定要将该影片移出媒体库吗？')) return;
            fetch('/api/private/movies/' + movieId, { method: 'DELETE' })
                .then(function(res) { return res.json(); })
                .then(function(data) {
                    if (data && !data.success) {
                        showToast(data.message || '移出失败');
                    } else {
                        showToast('已移出');
                        if (state.selectedMovieIds) {
                            var sIdx = state.selectedMovieIds.indexOf(movieId);
                            if (sIdx !== -1) {
                                state.selectedMovieIds.splice(sIdx, 1);
                                updateBatchBarUI();
                            }
                        }
                        loadMovies();
                    }
                })
                .catch(function(err) {
                    showToast('删除失败: ' + err.message);
                });
        }

        function handleMovieSelectChange(event, movieId) {
            event.stopPropagation();
            if (!state.selectedMovieIds) state.selectedMovieIds = [];
            var idx = state.selectedMovieIds.indexOf(movieId);
            if (event.target.checked) {
                if (idx === -1) state.selectedMovieIds.push(movieId);
                var tr = document.getElementById('tr_movie_' + movieId);
                if (tr) tr.classList.add('tr-selected');
            } else {
                if (idx !== -1) state.selectedMovieIds.splice(idx, 1);
                var tr = document.getElementById('tr_movie_' + movieId);
                if (tr) tr.classList.remove('tr-selected');
            }
            updateBatchBarUI();
        }

        function toggleSelectAllMovies(checked) {
            if (!state.movies || state.movies.length === 0) return;
            var isSubLib = (state.currentLib && state.currentLib.share_type === 2);
            if (isSubLib) return;
            if (!state.selectedMovieIds) state.selectedMovieIds = [];

            for (var i = 0; i < state.movies.length; i++) {
                var mid = state.movies[i].id;
                var idx = state.selectedMovieIds.indexOf(mid);
                if (checked) {
                    if (idx === -1) state.selectedMovieIds.push(mid);
                } else {
                    if (idx !== -1) state.selectedMovieIds.splice(idx, 1);
                }
            }

            var cbs = document.querySelectorAll('.movie-select-cb');
            for (var j = 0; j < cbs.length; j++) {
                var mid = cbs[j].getAttribute('data-id');
                if (mid) {
                    var isChk = state.selectedMovieIds.indexOf(mid) !== -1;
                    cbs[j].checked = isChk;
                    var tr = document.getElementById('tr_movie_' + mid);
                    if (tr) {
                        if (isChk) tr.classList.add('tr-selected');
                        else tr.classList.remove('tr-selected');
                    }
                }
            }
            updateBatchBarUI();
        }

        function selectAllCurrentPageMovies() {
            toggleSelectAllMovies(true);
        }

        function clearMovieSelection() {
            state.selectedMovieIds = [];
            var cbs = document.querySelectorAll('.movie-select-cb');
            for (var j = 0; j < cbs.length; j++) {
                cbs[j].checked = false;
            }
            var trs = document.querySelectorAll('.movie-table tbody tr.tr-selected');
            for (var k = 0; k < trs.length; k++) {
                trs[k].classList.remove('tr-selected');
            }
            updateBatchBarUI();
        }

        function updateBatchBarUI() {
            var isTable = (state.movieViewMode === 'table');
            var batchBar = document.getElementById('movieBatchBar');
            var selectAllCb = document.getElementById('selectAllMovies');
            var countEl = document.getElementById('selectedMovieCount');
            var btnBatchCopy = document.getElementById('btnBatchCopy');
            var btnBatchDelete = document.getElementById('btnBatchDelete');
            var totalSelected = state.selectedMovieIds ? state.selectedMovieIds.length : 0;
            var isSubLib = isCurrentLibReadOnly();

            if (countEl) countEl.innerText = totalSelected;
            if (btnBatchCopy) {
                btnBatchCopy.disabled = (totalSelected === 0);
                btnBatchCopy.innerHTML = '📋 批量复制到媒体库 (' + totalSelected + ')';
            }
            if (btnBatchDelete) {
                if (isSubLib) {
                    btnBatchDelete.style.display = 'none';
                } else {
                    btnBatchDelete.style.display = 'inline-flex';
                    btnBatchDelete.disabled = (totalSelected === 0);
                    btnBatchDelete.innerHTML = '🗑️ 批量移出 (' + totalSelected + ')';
                }
            }

            if (batchBar) {
                if (isTable && totalSelected > 0) {
                    batchBar.style.display = 'flex';
                } else {
                    batchBar.style.display = 'none';
                }
            }

            if (selectAllCb) {
                if (!state.movies || state.movies.length === 0) {
                    selectAllCb.checked = false;
                    selectAllCb.indeterminate = false;
                    selectAllCb.disabled = true;
                } else {
                    selectAllCb.disabled = false;
                    var pageCount = state.movies.length;
                    var pageSelectedCount = 0;
                    for (var i = 0; i < pageCount; i++) {
                        if (state.selectedMovieIds && state.selectedMovieIds.indexOf(state.movies[i].id) !== -1) {
                            pageSelectedCount++;
                        }
                    }
                    if (pageSelectedCount === 0) {
                        selectAllCb.checked = false;
                        selectAllCb.indeterminate = false;
                    } else if (pageSelectedCount === pageCount) {
                        selectAllCb.checked = true;
                        selectAllCb.indeterminate = false;
                    } else {
                        selectAllCb.checked = false;
                        selectAllCb.indeterminate = true;
                    }
                }
            }
        }

        function batchDeleteSelectedMovies() {
            if (checkReadOnlyGuard()) return;
            if (!state.selectedMovieIds || state.selectedMovieIds.length === 0) {
                showToast('请先勾选需要移出的影片');
                return;
            }
            var count = state.selectedMovieIds.length;
            var confirmMsg = '确定要将选中的 ' + count + ' 部影片移出媒体库吗？\n如果已开启海报墙，对应的本地 STRM 物理文件将同步清理。';
            if (!confirm(confirmMsg)) return;

            var idsToDelete = state.selectedMovieIds.slice();
            var btn = document.getElementById('btnBatchDelete');
            if (btn) {
                btn.disabled = true;
                btn.innerHTML = '⏳ 正在批量移出...';
            }

            fetch('/api/private/movies/batch-delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ movie_ids: idsToDelete })
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (data && !data.success) {
                    showToast(data.message || '批量移出失败');
                    updateBatchBarUI();
                } else {
                    var delCount = (data && data.deleted_count != null) ? data.deleted_count : count;
                    showToast('已成功移出 ' + delCount + ' 部影片');
                    state.selectedMovieIds = [];
                    updateBatchBarUI();
                    loadMovies();
                }
            })
            .catch(function(err) {
                showToast('批量移出请求异常: ' + err.message);
                updateBatchBarUI();
            });
        }

        function showMovieTmdbDetail(movieId) {
            var m = null;
            if (state.currentMovie && state.currentMovie.id === movieId) {
                m = state.currentMovie;
            } else if (state.movies && state.movies.length > 0) {
                for (var i = 0; i < state.movies.length; i++) {
                    if (state.movies[i].id === movieId) {
                        m = state.movies[i];
                        break;
                    }
                }
            }
            if (!m) return;

            var areaStr = getMovieCountry(m);
            var isTv = checkIsSeries(m, m.links);
            var finalTypeId = isTv ? 2 : (parseInt(m.type_id, 10) || 1);

            var vData = {
                tmdbId: m.tmdb_id || 0,
                title: m.title,
                originalTitle: m.original_name || '',
                year: m.year || '',
                pic: m.cover_url || '',
                backdropPath: m.backdrop_url || '',
                typeId: finalTypeId,
                content: m.summary || '',
                director: m.directors || '',
                starring: m.actors || '',
                area: areaStr
            };

            var isTmdb = (m.tmdb_id > 0);
            openTmdbPreviewModal(-1, vData, isTmdb);

            var btnConfirm = document.getElementById('btnConfirmTmdbBind');
            if (btnConfirm) btnConfirm.style.display = 'none';

            var titleEl = document.getElementById('tmdbDetailModalTitle');
            if (titleEl) {
                titleEl.innerText = (m.title || '') + (m.year ? ' (' + m.year + ')' : '');
            }
        }

        function parseMovieExtraTvMeta(movie) {
            if (!movie || !movie.extra_meta_json) return;
            try {
                var fMeta = typeof movie.extra_meta_json === 'string' ? JSON.parse(movie.extra_meta_json) : movie.extra_meta_json;
                if (fMeta && fMeta.seasons) {
                    for (var sI = 0; sI < fMeta.seasons.length; sI++) {
                        var sObj = fMeta.seasons[sI];
                        if (sObj.episodes) {
                            for (var eI = 0; eI < sObj.episodes.length; eI++) {
                                var epObj = sObj.episodes[eI];
                                state.tvMetaMap[epObj.season_number + '_' + epObj.episode_number] = epObj;
                            }
                        }
                    }
                }
            } catch(e) {}
        }

        function enterMovie(movieId) {
            var movie = null;
            for (var i = 0; i < state.movies.length; i++) {
                if (state.movies[i].id === movieId) { movie = state.movies[i]; break; }
            }
            if (!movie) return;
            state.currentMovie = movie;
            state.currentLevel = 3;
            state.currentSeason = 1;
            state.currentEpisode = 1;
            state.tvMetaMap = {};

            // 保持底层 viewLevel2 列表原位与滚动位置不变，以全屏弹窗形式覆盖展示
            var v3 = document.getElementById('viewLevel3');
            if (v3) {
                v3.classList.add('active');
                v3.style.display = 'flex';
                // 滚动弹窗主体至顶部
                var modalBody = v3.querySelector('.movie-detail-modal-body');
                if (modalBody) modalBody.scrollTop = 0;
            }
            document.body.style.overflow = 'hidden';

            var headingTitleEl = document.getElementById('modalMovieTitleHeading');
            if (headingTitleEl) headingTitleEl.innerText = movie.title || '';

            document.getElementById('currentMovieTitle').innerText = movie.title;
            document.getElementById('currentMoviePoster').src = formatProxiedImgUrl(movie.cover_url || PRESET_COVERS[0]);
            document.getElementById('currentMovieSubMeta').innerText = (movie.year || '') + (movie.genres ? ' · ' + movie.genres : '');
            document.getElementById('currentMovieDesc').innerText = movie.summary || '暂无剧情简介。';

            // 解析已缓存的深度剧集元数据
            parseMovieExtraTvMeta(movie);

            // 若当前为剧集系列且尚未加载深度元数据，按需异步拉取单片元数据补齐分集简介与单集剧照
            if (!movie.extra_meta_json && (isSeriesTypeId(movie.type_id) || checkIsSeries(movie, movie.links))) {
                fetch('/api/private/movies/' + movie.id)
                    .then(function(res) { return res.json(); })
                    .then(function(data) {
                        if (data && data.success && data.data && data.data.extra_meta_json) {
                            movie.extra_meta_json = data.data.extra_meta_json;
                            if (state.currentMovie && state.currentMovie.id === movie.id) {
                                parseMovieExtraTvMeta(movie);
                                renderLinks();
                            }
                        }
                    })
                    .catch(function(err) {
                        console.warn('按需加载剧集深度元数据失败:', err);
                    });
            }

            var libBadgeEl = document.getElementById('currentMovieLibBadge');
            if (libBadgeEl) {
                if (movie.library_name) {
                    libBadgeEl.style.display = 'inline-flex';
                    libBadgeEl.innerText = '📁 ' + movie.library_name;
                    libBadgeEl.onclick = function(e) {
                        e.stopPropagation();
                        enterLibraryDirect(movie.library_id);
                    };
                } else {
                    libBadgeEl.style.display = 'none';
                }
            }

            var isSubLib = isMovieReadOnly(movie);
            var btnSelectSources = document.getElementById('btnL3SelectSources');
            var btnAddLink = document.getElementById('btnL3AddLink');
            var btnRebind = document.getElementById('btnRebindMovie');
            if (isSubLib) {
                if (btnSelectSources) btnSelectSources.style.display = 'none';
                if (btnAddLink) btnAddLink.style.display = 'none';
                if (btnRebind) btnRebind.style.display = 'none';
            } else {
                if (btnSelectSources) btnSelectSources.style.display = 'inline-flex';
                if (btnAddLink) btnAddLink.style.display = 'inline-flex';
                if (btnRebind) btnRebind.style.display = 'inline-flex';
            }

            loadLinks();
        }

        function loadLinks() {
            if (!state.currentMovie) return;
            fetch('/api/private/movies/' + state.currentMovie.id + '/links')
                .then(function(res) { return res.json(); })
                .then(function(data) {
                    state.links = data.data || [];
                    var isTV = checkIsSeries(state.currentMovie, state.links);
                    var badge = document.getElementById('currentMovieTypeBadge');
                    if (badge) {
                        var tid = parseInt(state.currentMovie.type_id, 10);
                        var badgeText = '电影';
                        if (tid === 2) badgeText = '电视剧';
                        else if (tid === 3) badgeText = '动漫';
                        else if (tid === 4) badgeText = '综艺';
                        else if (tid === 5) badgeText = isTV ? '纪录片(系列)' : '纪录片';
                        else if (isTV) badgeText = '剧集';

                        badge.innerText = badgeText;
                        badge.style.background = isTV ? 'rgba(56, 189, 248, 0.2)' : 'rgba(99, 102, 241, 0.2)';
                        badge.style.color = isTV ? '#38bdf8' : '#818cf8';
                        badge.style.borderColor = isTV ? 'rgba(56, 189, 248, 0.4)' : 'rgba(99, 102, 241, 0.4)';
                    }

                    // 检查是否包含尚未记录上级目录的个人盘链接
                    var hasMissingPath = state.links.some(function(l) {
                        var is115 = (l.provider === 'CLOUD115' || l.provider === '115网盘' || (l.url && l.url.indexOf('user_pan://') === 0));
                        var hasPath = !!(l.parent_folder_path || l.parent_folder_name);
                        return is115 && !hasPath;
                    });

                    var btnSyncF = document.getElementById('btnL3SyncFolders');
                    if (btnSyncF) {
                        btnSyncF.style.display = hasMissingPath ? 'inline-flex' : 'none';
                    }

                    renderLinks();

                    // 若存在缺失路径的个人盘链接，后台静默自动补齐
                    if (hasMissingPath && state.currentMovie) {
                        fetch('/api/private/movies/' + state.currentMovie.id + '/sync_parent_folders', { method: 'POST' })
                            .then(function(r) { return r.json(); })
                            .then(function(res) {
                                if (res && res.success && res.synced_count > 0 && res.data) {
                                    state.links = res.data;
                                    var btnSyncFNow = document.getElementById('btnL3SyncFolders');
                                    if (btnSyncFNow) btnSyncFNow.style.display = 'none';
                                    renderLinks();
                                }
                            })
                            .catch(function() {});
                    }
                })
                .catch(function(err) {
                    showToast('加载链接失败: ' + err.message);
                });
        }

        function syncCurrentMovieParentFolders() {
            if (!state.currentMovie) return;
            var btn = document.getElementById('btnL3SyncFolders');
            if (btn) {
                btn.disabled = true;
                btn.innerText = '⏳ 正在补全路径...';
            }
            showToast('正在为当前影片所有网盘链接反查并补全路径...');
            fetch('/api/private/movies/' + state.currentMovie.id + '/sync_parent_folders', {
                method: 'POST'
            })
            .then(function(res) { return res.json(); })
            .then(function(json) {
                if (btn) {
                    btn.disabled = false;
                    btn.innerText = '📁 补全网盘路径';
                }
                if (json && json.success) {
                    if (json.data) {
                        state.links = json.data;
                        renderLinks();
                    } else {
                        loadLinks();
                    }
                    showToast('补全完成！共更新 ' + (json.synced_count || 0) + ' 条链接的网盘路径');
                } else {
                    showToast(json && json.error ? json.error : '补全网盘路径失败');
                }
            })
            .catch(function(err) {
                if (btn) {
                    btn.disabled = false;
                    btn.innerText = '📁 补全网盘路径';
                }
                showToast('请求异常: ' + err.message);
            });
        }

        function syncCurrentLibParentFolders() {
            var libId = state.currentLib ? state.currentLib.id : 'all';
            var libName = state.currentLib ? state.currentLib.name : '全部私有库';
            if (!confirm('确定要为【' + libName + '】中所有个人网盘链接自动反查并补全网盘上级目录吗？\n\n系统将自动通过 115 接口反查真实层级路径。')) {
                return;
            }
            showToast('正在反查并补全媒体库个人网盘路径，请稍候...');
            fetch('/api/private/libraries/' + libId + '/sync_parent_folders', {
                method: 'POST'
            })
            .then(function(res) { return res.json(); })
            .then(function(json) {
                if (json && json.success) {
                    showToast('媒体库网盘路径补全完成！共更新 ' + (json.synced_count || 0) + ' 条链接');
                    if (state.currentMovie) {
                        loadLinks();
                    }
                } else {
                    showToast(json && json.error ? json.error : '反查补全失败');
                }
            })
            .catch(function(err) {
                showToast('请求异常: ' + err.message);
            });
        }

        var CLOUD_PROVIDER_MAP = {
            '1': '阿里云盘', 'ALIYUN': '阿里云盘', 'aliyun': '阿里云盘', 'ALI': '阿里云盘',
            '2': '夸克网盘', 'QUARK': '夸克网盘', 'quark': '夸克网盘',
            '3': 'UC网盘', 'UC': 'UC网盘', 'uc': 'UC网盘',
            '4': '百度网盘', 'BAIDU': '百度网盘', 'baidu': '百度网盘',
            '5': '迅雷网盘', 'XUNLEI': '迅雷网盘', 'xunlei': '迅雷网盘',
            '6': '123云盘', 'CLOUD123': '123云盘', 'cloud123': '123云盘',
            '7': '115网盘', 'CLOUD115': '115网盘', 'cloud115': '115网盘', '115': '115网盘',
            '8': '移动云盘', 'CHINA_MOBILE': '移动云盘', 'china_mobile': '移动云盘',
            '9': '天翼云盘', 'CHINA_TELECOM': '天翼云盘', 'china_telecom': '天翼云盘',
            '11': '光鸭云盘', 'GUANGYA': '光鸭云盘', 'guangya': '光鸭云盘'
        };

        function getProviderDisplayName(provider, linkType, url) {
            if (linkType === 'user_pan' || (url && url.indexOf('user_pan://') === 0)) {
                var pStr = String(provider || '').trim();
                if (!pStr && url && url.indexOf('user_pan://') === 0) {
                    var m = url.match(/^user_pan:\/\/([^\/]+)/i);
                    if (m) pStr = m[1];
                }
                var pName = CLOUD_PROVIDER_MAP[pStr] || pStr || '网盘';
                return '个人' + pName.replace('网盘', '').replace('云盘', '');
            }
            if (linkType === 'magnet') return '磁力';
            if (linkType === 'ed2k') return '电驴';
            if (linkType === 'http') return '直链';

            var pStr = String(provider || '').trim();
            if (CLOUD_PROVIDER_MAP[pStr]) {
                return CLOUD_PROVIDER_MAP[pStr];
            }

            var u = (url || '').toLowerCase();
            if (u.indexOf('115.com') !== -1 || u.indexOf('115cdn') !== -1 || u.indexOf('anxia.com') !== -1) return '115网盘';
            if (u.indexOf('quark.cn') !== -1) return '夸克网盘';
            if (u.indexOf('alipan.com') !== -1 || u.indexOf('aliyundrive.com') !== -1) return '阿里云盘';
            if (u.indexOf('pan.baidu.com') !== -1 || u.indexOf('baidu.com') !== -1) return '百度网盘';
            if (u.indexOf('pan.xunlei.com') !== -1 || u.indexOf('xunlei.com') !== -1) return '迅雷网盘';
            if (u.indexOf('disk.uc.cn') !== -1 || u.indexOf('drive.uc.cn') !== -1 || u.indexOf('uc.cn') !== -1) return 'UC网盘';
            if (u.indexOf('123pan') !== -1 || u.indexOf('123684') !== -1 || u.indexOf('123865') !== -1 || u.indexOf('123952') !== -1) return '123云盘';
            if (u.indexOf('yun.139.com') !== -1 || u.indexOf('caiyun.139.com') !== -1 || u.indexOf('139.com') !== -1) return '移动云盘';
            if (u.indexOf('cloud.189.cn') !== -1 || u.indexOf('189.cn') !== -1 || u.indexOf('content.21cn.com') !== -1) return '天翼云盘';
            if (u.indexOf('guangyapan.com') !== -1) return '光鸭云盘';
            if (u.indexOf('magnet:?') === 0) return '磁力';
            if (u.indexOf('ed2k://') === 0) return '电驴';
            if (u.indexOf('http://') === 0 || u.indexOf('https://') === 0) return '直链';

            return pStr || '网盘';
        }

        function renderLinks() {
            var container = document.getElementById('linksListContainer');
            var isTV = checkIsSeries(state.currentMovie, state.links);
            var tvSection = document.getElementById('tvShowEpisodeSection');
            var heading = document.getElementById('linksSectionHeading');

            if (!isTV) {
                if (tvSection) tvSection.style.display = 'none';
                if (heading) heading.innerText = '播放链接与资源列表 (' + state.links.length + ')';

                if (state.links.length === 0) {
                    var emptyTip = isCurrentLibReadOnly() ? '当前订阅库暂无播放源，请点击同步更新' : '点击右上角【+ 添加链接】添加网盘、磁力或直链';
                    container.innerHTML = '<div class="empty-state"><div class="empty-icon">🔗</div><div style="font-size: 16px; font-weight: 600; color: #fff;">暂无播放链接</div><div>' + emptyTip + '</div></div>';
                    return;
                }

                renderLinkItemsHtml(state.links, container, false);
                return;
            }

            // =============== 剧集专属交互逻辑 ===============
            if (tvSection) tvSection.style.display = 'block';

            // 1. 汇总所有季
            var seasonsSet = {};
            for (var i = 0; i < state.links.length; i++) {
                var sNum = (state.links[i].season_number !== undefined && state.links[i].season_number !== null && state.links[i].season_number >= 0) ? state.links[i].season_number : 1;
                seasonsSet[sNum] = true;
            }
            // 也包含 extra_meta_json 里有的季
            for (var k in state.tvMetaMap) {
                var parts = k.split('_');
                seasonsSet[parseInt(parts[0], 10)] = true;
            }
            var seasonsList = Object.keys(seasonsSet).map(Number).sort(function(a,b){ return a - b; });
            if (seasonsList.length === 0) seasonsList = [1];
            if (!seasonsSet[state.currentSeason]) {
                state.currentSeason = seasonsList[0];
            }

            // 渲染季 Tabs
            var tabsContainer = document.getElementById('seasonTabsContainer');
            if (tabsContainer) {
                var tabsHtml = '';
                for (var si = 0; si < seasonsList.length; si++) {
                    var sn = seasonsList[si];
                    var actClass = (sn === state.currentSeason) ? ' active' : '';
                    var sTabLabel = (sn === 0) ? '特别篇 (第 0 季)' : ('第 ' + sn + ' 季');
                    tabsHtml += '<button class="season-tab-btn' + actClass + '" onclick="selectSeasonTab(' + sn + ')">' + sTabLabel + '</button>';
                }
                tabsContainer.innerHTML = tabsHtml;
            }

            // 2. 汇总当前季所有集
            var episodesSet = {};
            var epLinksCount = {};
            for (var j = 0; j < state.links.length; j++) {
                var lk = state.links[j];
                var lkSeason = (lk.season_number !== undefined && lk.season_number !== null && lk.season_number >= 0) ? lk.season_number : 1;
                var lkEp = lk.episode_number || 1;
                if (lkSeason === state.currentSeason) {
                    episodesSet[lkEp] = true;
                    epLinksCount[lkEp] = (epLinksCount[lkEp] || 0) + 1;
                }
            }
            // 也包含元数据里的集
            for (var key in state.tvMetaMap) {
                var ps = key.split('_');
                var metaS = parseInt(ps[0], 10);
                var metaE = parseInt(ps[1], 10);
                if (metaS === state.currentSeason) {
                    episodesSet[metaE] = true;
                }
            }
            var episodesList = Object.keys(episodesSet).map(Number).sort(function(a,b){ return a - b; });
            if (episodesList.length === 0) episodesList = [1];
            if (!episodesSet[state.currentEpisode]) {
                state.currentEpisode = episodesList[0];
            }

            var countText = document.getElementById('seasonEpisodesCountText');
            if (countText) {
                countText.innerText = '第 ' + state.currentSeason + ' 季选集 (共 ' + episodesList.length + ' 集)';
            }

            // 渲染分集网格
            var gridContainer = document.getElementById('episodesGridContainer');
            if (gridContainer) {
                var gridHtml = '';
                for (var ei = 0; ei < episodesList.length; ei++) {
                    var ep = episodesList[ei];
                    var isAct = (ep === state.currentEpisode);
                    var lCount = epLinksCount[ep] || 0;
                    var badge = lCount > 0 ? ('<div class="ep-grid-badge">' + lCount + ' 源</div>') : ('<div class="ep-grid-badge ep-none">未配置</div>');
                    var epPad = ep < 10 ? ('0' + ep) : ep;
                    gridHtml += '<div class="ep-grid-btn' + (isAct ? ' active' : '') + '" onclick="selectEpisodeItem(' + ep + ')">';
                    gridHtml += '<div class="ep-grid-num">' + epPad + '</div>';
                    gridHtml += badge;
                    gridHtml += '</div>';
                }
                gridContainer.innerHTML = gridHtml;
            }

            // 3. 渲染当前选中集的情报卡片
            var infoCard = document.getElementById('selectedEpisodeInfoCard');
            var metaKey = state.currentSeason + '_' + state.currentEpisode;
            var epMeta = state.tvMetaMap[metaKey];
            var thumbImg = document.getElementById('selectedEpisodeThumb');
            var headingEp = document.getElementById('selectedEpisodeHeading');
            var airDate = document.getElementById('selectedEpisodeAirDate');
            var overview = document.getElementById('selectedEpisodeOverview');

            var matchedLinks = [];
            for (var mIdx = 0; mIdx < state.links.length; mIdx++) {
                var currL = state.links[mIdx];
                var s = (currL.season_number !== undefined && currL.season_number !== null && currL.season_number >= 0) ? currL.season_number : 1;
                var e = currL.episode_number || 1;
                if (s === state.currentSeason && e === state.currentEpisode) {
                    matchedLinks.push(currL);
                }
            }

            if (epMeta || matchedLinks.length > 0) {
                if (infoCard) infoCard.style.display = 'block';
                var epTitle = (epMeta && epMeta.name) ? (' · ' + epMeta.name) : '';
                if (matchedLinks.length > 0 && matchedLinks[0].episode_title && !epTitle) {
                    epTitle = ' · ' + matchedLinks[0].episode_title;
                }
                var sLabel = (state.currentSeason === 0) ? '特别篇 (第 0 季)' : ('第 ' + state.currentSeason + ' 季');
                if (headingEp) headingEp.innerText = sLabel + ' 第 ' + state.currentEpisode + ' 集' + epTitle;
                if (airDate) airDate.innerText = (epMeta && epMeta.air_date) ? ('首播时间: ' + epMeta.air_date) : '';
                if (overview) overview.innerText = (epMeta && epMeta.overview) ? epMeta.overview : '暂无单集详细剧情。';

                if (thumbImg) {
                    if (epMeta && epMeta.still_path) {
                        thumbImg.src = epMeta.still_path;
                        thumbImg.style.display = 'block';
                    } else {
                        thumbImg.style.display = 'none';
                    }
                }
            } else if (infoCard) {
                infoCard.style.display = 'none';
            }

            // 4. 渲染当前选中集的播放源列表
            if (heading) {
                heading.innerText = '第 ' + state.currentSeason + ' 季 第 ' + state.currentEpisode + ' 集 播放源 (' + matchedLinks.length + ')';
            }
            if (matchedLinks.length === 0) {
                var emptyMsg = isCurrentLibReadOnly() ? '该集暂未配置播放源' : '该集暂无播放源，请点击上方【+ 手动添加链接】为第 ' + state.currentEpisode + ' 集添加源';
                container.innerHTML = '<div class="empty-state"><div class="empty-icon">📺</div><div style="font-size: 15px; font-weight: 600; color: #fff;">暂无本集播放源</div><div>' + emptyMsg + '</div></div>';
                return;
            }

            renderLinkItemsHtml(matchedLinks, container);
        }

        function selectSeasonTab(seasonNum) {
            state.currentSeason = seasonNum;
            state.currentEpisode = 1;
            renderLinks();
        }

        function selectEpisodeItem(epNum) {
            state.currentEpisode = epNum;
            renderLinks();
        }

        function refreshCurrentMovieTvMeta() {
            if (!state.currentMovie) return;
            var btn = document.getElementById('btnRefreshTvMeta');
            if (btn) {
                btn.disabled = true;
                btn.innerText = '正在抓取中...';
            }
            showToast('正在向 TMDB 请求拉取全剧各季各集深度元数据...');
            fetch('/api/private/movies/' + state.currentMovie.id + '/refresh_tv_meta', { method: 'POST' })
                .then(function(res) { return res.json(); })
                .then(function(data) {
                    if (btn) {
                        btn.disabled = false;
                        btn.innerText = '🔄 抓取/更新全剧分集元数据';
                    }
                    if (data && data.success) {
                        showToast(data.message || '抓取成功！');
                        state.currentMovie.type_id = 2;
                        if (data.data) {
                            state.currentMovie.extra_meta_json = JSON.stringify(data.data);
                            state.tvMetaMap = {};
                            if (data.data.seasons) {
                                for (var sI = 0; sI < data.data.seasons.length; sI++) {
                                    var sObj = data.data.seasons[sI];
                                    if (sObj.episodes) {
                                        for (var eI = 0; eI < sObj.episodes.length; eI++) {
                                            var epObj = sObj.episodes[eI];
                                            state.tvMetaMap[epObj.season_number + '_' + epObj.episode_number] = epObj;
                                        }
                                    }
                                }
                            }
                        }
                        var badge = document.getElementById('currentMovieTypeBadge');
                        if (badge) {
                            badge.innerText = '剧集';
                            badge.style.background = 'rgba(56, 189, 248, 0.2)';
                            badge.style.color = '#38bdf8';
                            badge.style.borderColor = 'rgba(56, 189, 248, 0.4)';
                        }
                        renderLinks();
                    } else {
                        showToast('抓取失败: ' + ((data && (data.message || data.error)) || '未知错误'));
                    }
                })
                .catch(function(err) {
                    if (btn) {
                        btn.disabled = false;
                        btn.innerText = '🔄 抓取/更新全剧分集元数据';
                    }
                    showToast('抓取请求失败: ' + err.message);
                });
        }

        function renderLinkItemsHtml(links, container, isTVParam) {
            var isSubLib = isCurrentLibReadOnly();
            var isTV = (isTVParam !== undefined) ? isTVParam : checkIsSeries(state.currentMovie, state.links);
            var html = '';
            for (var i = 0; i < links.length; i++) {
                var l = links[i];
                var badgeClass = 'lt-pan';
                var typeName = getProviderDisplayName(l.provider, l.link_type, l.url);
                if (l.link_type === 'magnet') { badgeClass = 'lt-magnet'; }
                else if (l.link_type === 'http') { badgeClass = 'lt-http'; }
                else if (l.link_type === 'ed2k') { badgeClass = 'lt-ed2k'; }
                else if (l.link_type === 'user_pan' || (l.url && l.url.indexOf('user_pan://') === 0)) { badgeClass = 'lt-user-pan'; }

                var editBtns = isSubLib ? '' : '<button class="icon-btn" onclick="event.stopPropagation(); openEditLinkModal(\'' + l.id + '\')">✏️</button><button class="icon-btn" style="color: #fca5a5;" onclick="event.stopPropagation(); deleteLink(\'' + l.id + '\')">🗑️</button>';

                var remarkDisplay = l.remark || '未填写备注';
                // 仅当是剧集且具有特殊单集标题时，才在备注前展示单集标题
                if (isTV && l.episode_title) {
                    remarkDisplay = '【' + l.episode_title + '】 ' + remarkDisplay;
                }

                html += '<div class="link-item-card" onclick="openLinkDetailModal(\'' + l.id + '\')" title="点击查看播放链接详细信息与全部参数">';
                html += '<div class="link-item-left"><div class="link-type-badge ' + badgeClass + '">' + typeName + '</div>';
                html += '<div class="link-item-details"><div class="link-remark">' + escapeHtml(remarkDisplay) + '</div><div class="link-url-text">' + escapeHtml(l.url || '') + '</div></div></div>';
                html += '<div class="link-item-right" onclick="event.stopPropagation()">';
                html += '<button class="btn btn-secondary" style="padding: 6px 12px; font-size: 13px;" onclick="event.stopPropagation(); testPlayLink(\'' + l.id + '\')">▶ 播放</button>';
                html += editBtns;
                html += '<span style="font-size: 15px; color: var(--text-muted); padding-left: 2px;" title="查看详情">›</span>';
                html += '</div></div>';
            }
            container.innerHTML = html;
        }

        function openAddLinkModal() {
            if (checkReadOnlyGuard()) return;
            state.activeEditingLinkId = null;
            document.getElementById('linkModalTitle').innerText = '添加播放链接';
            document.getElementById('linkTypeSelect').value = 'pan';
            document.getElementById('linkUrlInput').value = '';
            document.getElementById('linkPwdInput').value = '';
            document.getElementById('linkRemarkInput').value = '';
            var parentFolderEl = document.getElementById('linkParentFolderInput');
            if (parentFolderEl) parentFolderEl.value = '';

            var isTV = checkIsSeries(state.currentMovie, state.links);
            var seasonEpGroup = document.getElementById('linkSeasonEpGroup');
            var epTitleGroup = document.getElementById('linkEpisodeTitleGroup');
            if (isTV) {
                if (seasonEpGroup) seasonEpGroup.style.display = 'flex';
                if (epTitleGroup) epTitleGroup.style.display = 'block';
                document.getElementById('linkSeasonInput').value = state.currentSeason || 1;
                document.getElementById('linkEpisodeInput').value = state.currentEpisode || 1;
                var metaKey = (state.currentSeason || 1) + '_' + (state.currentEpisode || 1);
                var epMeta = state.tvMetaMap ? state.tvMetaMap[metaKey] : null;
                document.getElementById('linkEpisodeTitleInput').value = (epMeta && epMeta.name) ? epMeta.name : '';
            } else {
                if (seasonEpGroup) seasonEpGroup.style.display = 'none';
                if (epTitleGroup) epTitleGroup.style.display = 'none';
                document.getElementById('linkSeasonInput').value = '1';
                document.getElementById('linkEpisodeInput').value = '1';
                document.getElementById('linkEpisodeTitleInput').value = '';
            }

            openModal('linkModal');
        }

        function openEditLinkModal(id) {
            if (checkReadOnlyGuard()) return;
            var link = null;
            for (var i = 0; i < state.links.length; i++) {
                if (state.links[i].id === id) { link = state.links[i]; break; }
            }
            if (!link) return;
            state.activeEditingLinkId = id;
            document.getElementById('linkModalTitle').innerText = '修改播放链接';
            document.getElementById('linkTypeSelect').value = link.link_type || 'pan';
            document.getElementById('linkUrlInput').value = link.url || '';
            document.getElementById('linkPwdInput').value = link.password || '';
            document.getElementById('linkRemarkInput').value = link.remark || '';
            var parentFolderEditEl = document.getElementById('linkParentFolderInput');
            if (parentFolderEditEl) parentFolderEditEl.value = link.parent_folder_path || link.parent_folder_name || '';

            var isTV = checkIsSeries(state.currentMovie, state.links);
            var seasonEpGroup = document.getElementById('linkSeasonEpGroup');
            var epTitleGroup = document.getElementById('linkEpisodeTitleGroup');
            if (isTV) {
                if (seasonEpGroup) seasonEpGroup.style.display = 'flex';
                if (epTitleGroup) epTitleGroup.style.display = 'block';
                document.getElementById('linkSeasonInput').value = (link.season_number !== undefined && link.season_number !== null && link.season_number >= 0) ? link.season_number : 1;
                document.getElementById('linkEpisodeInput').value = link.episode_number || 1;
                document.getElementById('linkEpisodeTitleInput').value = link.episode_title || '';
            } else {
                if (seasonEpGroup) seasonEpGroup.style.display = 'none';
                if (epTitleGroup) epTitleGroup.style.display = 'none';
                document.getElementById('linkSeasonInput').value = '1';
                document.getElementById('linkEpisodeInput').value = '1';
                document.getElementById('linkEpisodeTitleInput').value = '';
            }

            openModal('linkModal');
        }

        function onLinkInputChanged() {
            var url = (document.getElementById('linkUrlInput').value || '').trim();
            var pwd = (document.getElementById('linkPwdInput').value || '').trim();
            var typeSelect = document.getElementById('linkTypeSelect');
            var remarkInput = document.getElementById('linkRemarkInput');

            if (!url) return;

            // 1. 自动判断并切换链接类型
            var lower = url.toLowerCase();
            if (lower.indexOf('ed2k://') === 0) {
                typeSelect.value = 'ed2k';
            } else if (lower.indexOf('magnet:?') === 0) {
                typeSelect.value = 'magnet';
            } else if (lower.indexOf('http://') === 0 || lower.indexOf('https://') === 0) {
                if (isPanShareLink(lower)) {
                    typeSelect.value = 'pan';
                } else {
                    typeSelect.value = 'http';
                }
            }

            // 2. 如果备注尚未填写，自动从文件名或网盘只读嗅探提取智能画质备注与季集
            if (!remarkInput.value.trim()) {
                var linkName = extractNameFromLink(url);
                if (linkName) {
                    var smartRemark = extractSmartRemark(linkName, '');
                    if (smartRemark) remarkInput.value = smartRemark;
                } else if (typeSelect.value === 'pan') {
                    sniffPanShareFileName(url, pwd).then(function(fn) {
                        if (fn && !remarkInput.value.trim()) {
                            var r = extractSmartRemark(fn, '');
                            if (r) remarkInput.value = r;
                        }
                    });
                }
            }
        }

        function submitSaveLink() {
            if (checkReadOnlyGuard()) return;
            var link_type = document.getElementById('linkTypeSelect').value;
            var url = document.getElementById('linkUrlInput').value.trim();
            var password = document.getElementById('linkPwdInput').value.trim();
            var remark = document.getElementById('linkRemarkInput').value.trim();
            var parentFolderEl = document.getElementById('linkParentFolderInput');
            var parent_folder_path = parentFolderEl ? parentFolderEl.value.trim() : '';
            var parsedSeason = parseInt(document.getElementById('linkSeasonInput').value, 10);
            var season_number = (!isNaN(parsedSeason) && parsedSeason >= 0) ? parsedSeason : 1;
            var episode_number = parseInt(document.getElementById('linkEpisodeInput').value, 10) || 1;
            var episode_title = (document.getElementById('linkEpisodeTitleInput').value || '').trim();

            if (!url) {
                showToast('请输入播放链接');
                return;
            }

            var reqUrl = '/api/private/movies/' + state.currentMovie.id + '/links';
            var method = 'POST';
            if (state.activeEditingLinkId) {
                reqUrl = '/api/private/links/' + state.activeEditingLinkId;
                method = 'PUT';
            }

            var payload = {
                link_type: link_type,
                url: url,
                password: password,
                remark: remark,
                parent_folder_path: parent_folder_path,
                parent_folder_name: parent_folder_path,
                season_number: season_number,
                episode_number: episode_number,
                episode_title: episode_title
            };

            fetch(reqUrl, {
                method: method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (data && !data.success) {
                    showToast(data.message || '保存失败');
                } else {
                    showToast(state.activeEditingLinkId ? '修改成功' : '添加成功');
                    closeModal('linkModal');
                    loadLinks();
                }
            })
            .catch(function(err) {
                showToast('保存失败: ' + err.message);
            });
        }

        function deleteLink(linkId) {
            if (checkReadOnlyGuard()) return;
            if (!confirm('确定要删除该链接吗？')) return;
            fetch('/api/private/links/' + linkId, { method: 'DELETE' })
                .then(function(res) { return res.json(); })
                .then(function(data) {
                    if (data && !data.success) {
                        showToast(data.message || '删除失败');
                    } else {
                        showToast('已删除');
                        loadLinks();
                    }
                })
                .catch(function(err) {
                    showToast('删除失败: ' + err.message);
                });
        }

        function testPlayLink(linkId) {
            var link = null;
            for (var i = 0; i < state.links.length; i++) {
                if (state.links[i].id === linkId) { link = state.links[i]; break; }
            }
            if (!link) return;

            var isTV = checkIsSeries(state.currentMovie, state.links);
            var movieTitle = state.currentMovie ? state.currentMovie.title : '';
            var playTitle = movieTitle;
            if (isTV) {
                var sNum = (link.season_number !== undefined && link.season_number !== null) ? link.season_number : 1;
                var eNum = (link.episode_number && link.episode_number > 0) ? link.episode_number : 1;
                var sStr = String(sNum).padStart(2, '0');
                var eStr = String(eNum).padStart(2, '0');
                playTitle += ' S' + sStr + 'E' + eStr;
                if (link.episode_title) playTitle += ' ' + link.episode_title;
            } else if (link.remark) {
                playTitle += ' (' + link.remark + ')';
            } else if (link.file_name) {
                playTitle += ' - ' + link.file_name;
            }

            var typeIdVal = (state.currentMovie && state.currentMovie.type_id) ? parseInt(state.currentMovie.type_id, 10) : (isTV ? 2 : 1);

            var lType = link.link_type || '';
            var pName = link.provider || '';
            var fId = link.file_id || '';
            var u = (link.url || '').trim();

            if (u.indexOf('user_pan://') === 0 || lType === 'user_pan') {
                lType = 'user_pan';
                if (u.indexOf('user_pan://') === 0) {
                    var rawParts = u.substring('user_pan://'.length).split('/');
                    if (rawParts.length >= 1 && !pName) pName = rawParts[0];
                    if (rawParts.length >= 2 && !fId) fId = rawParts[1];
                }
            }

            fetch('/api/push', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    url: u,
                    code: link.password || '',
                    title: playTitle,
                    vod_title: movieTitle,
                    movie_id: (state.currentMovie && (state.currentMovie.id || state.currentMovie.movie_id)) || '',
                    vod_id: (state.currentMovie && (state.currentMovie.vod_id || state.currentMovie.id)) || '',
                    pic: (state.currentMovie && state.currentMovie.cover_url) || '',
                    backdropPath: (state.currentMovie && state.currentMovie.backdrop_url) || '',
                    file_name: link.file_name || '',
                    pan_name: pName,
                    provider: pName,
                    type_id: typeIdVal,
                    is_tv: isTV ? "1" : "0",
                    season_number: isTV ? link.season_number : 0,
                    episode_number: isTV ? link.episode_number : 0,
                    episode_title: isTV ? (link.episode_title || '') : '',
                    remark: link.remark || '',
                    link_type: lType,
                    file_id: fId
                })
            })
            .then(function(res) {
                if (!res.ok) {
                    return res.json().then(function(data) {
                        throw new Error(data.error || ('HTTP ' + res.status));
                    });
                }
                showToast('已向 Kodi 电视端发送播放指令！');
            })
            .catch(function(err) {
                showToast('推送播放失败: ' + err.message);
            });
        }

        function closeMovieDetailModal() {
            var v3 = document.getElementById('viewLevel3');
            if (v3) {
                v3.classList.remove('active');
                v3.style.display = 'none';
            }
            document.body.style.overflow = '';
            state.currentLevel = 2;
            state.currentMovie = null;
            // 绝不重新调用 loadMovies()，保护底层列表已有 DOM 与滚动位置完好无损！
        }

        function goBackLevel() {
            if (state.currentLevel === 3) {
                closeMovieDetailModal();
                return;
            } else if (state.currentLevel === 2) {
                state.currentLevel = 1;
                state.currentLib = null;
                document.getElementById('viewLevel2').style.display = 'none';
                document.getElementById('viewLevel1').style.display = 'block';
                document.getElementById('headerBackBtn').style.display = 'none';
                document.getElementById('pageMainTitle').innerText = '我的私有库';
                loadLibraries();
            }
        }

        function formatBytes(bytes) {
            if (!bytes || bytes <= 0) return '0 B';
            var k = 1024;
            var sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
            var i = Math.floor(Math.log(bytes) / Math.log(k));
            if (i < 0) i = 0;
            if (i >= sizes.length) i = sizes.length - 1;
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        }

        function formatDateTime(ts) {
            if (!ts) return '未记录';
            var d = new Date(ts * 1000);
            var pad = function(n) { return n < 10 ? '0' + n : n; };
            return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) + ' ' +
                   pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds());
        }

        function copyTextToClipboard(text, successTip) {
            if (!text) return;
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text).then(function() {
                    showToast(successTip || '已成功复制到剪贴板！');
                }).catch(function() {
                    fallbackCopyText(text, successTip);
                });
            } else {
                fallbackCopyText(text, successTip);
            }
        }

        function fallbackCopyText(text, successTip) {
            var ta = document.createElement('textarea');
            ta.value = text;
            ta.style.position = 'fixed';
            ta.style.opacity = '0';
            document.body.appendChild(ta);
            ta.select();
            try {
                document.execCommand('copy');
                showToast(successTip || '已成功复制到剪贴板！');
            } catch(e) {
                showToast('复制失败，请长按手动复制');
            }
            document.body.removeChild(ta);
        }

        function openLinkDetailModal(linkId) {
            var link = null;
            if (state.links && state.links.length > 0) {
                for (var i = 0; i < state.links.length; i++) {
                    if (state.links[i].id === linkId) { link = state.links[i]; break; }
                }
            }
            if (!link) return;

            var body = document.getElementById('linkDetailModalBody');
            var footer = document.getElementById('linkDetailModalFooter');
            if (!body || !footer) return;

            var typeName = getProviderDisplayName(link.provider, link.link_type, link.url);
            var isTV = checkIsSeries(state.currentMovie, state.links);

            var html = '<div class="link-detail-prop-table">';

            // 1. 网盘与协议类型
            html += '<div class="link-detail-prop-row">';
            html += '<div class="link-detail-prop-label"><span>所属网盘 / 协议类型</span><span style="font-size:11px;color:#94a3b8;">' + escapeHtml(link.link_type || '') + '</span></div>';
            html += '<div class="link-detail-prop-value" style="display:flex;align-items:center;gap:8px;">';
            html += '<span class="movie-type-badge" style="background:rgba(59,130,246,0.2);color:#60a5fa;border-color:rgba(59,130,246,0.4);">' + escapeHtml(typeName) + '</span>';
            if (link.provider) {
                html += '<span style="font-size:12px;color:#cbd5e1;">(' + escapeHtml(link.provider) + ')</span>';
            }
            html += '</div></div>';

            // 2. 备注说明 (Remark)
            html += '<div class="link-detail-prop-row">';
            html += '<div class="link-detail-prop-label"><span>备注说明 (Remark)</span></div>';
            html += '<div class="link-detail-prop-value" style="font-weight:600;color:#38bdf8;">' + (escapeHtml(link.remark) || '<span style="color:var(--text-muted);font-weight:normal;">未填写备注</span>') + '</div>';
            html += '</div>';

            // 3. 网盘全部上级目录
            var parentFolderPath = link.parent_folder_path || link.parent_folder_name || '';
            var isCanSync = (link.link_type === 'user_pan' || (link.url && link.url.indexOf('user_pan://') === 0) || link.provider === 'CLOUD115' || link.provider === '115网盘');

            html += '<div class="link-detail-prop-row">';
            html += '<div class="link-detail-prop-label"><span>网盘上级目录</span>';
            html += '<div id="parentFolderAction_' + link.id + '">';
            if (parentFolderPath) {
                html += '<button class="btn btn-secondary btn-sm" style="padding:2px 8px;font-size:11px;" onclick="copyTextToClipboard(\'' + escapeHtml(parentFolderPath).replace(/'/g, "\\'") + '\', \'已复制上级目录路径\')">📋 复制</button>';
            } else if (isCanSync) {
                html += '<button class="btn btn-secondary btn-sm" id="btnSyncFolder_' + link.id + '" style="padding:2px 8px;font-size:11px;color:#38bdf8;" onclick="syncSingleLinkParentFolder(\'' + link.id + '\')">🔄 自动获取网盘路径</button>';
            }
            html += '</div></div>';
            html += '<div class="link-detail-prop-value" id="parentFolderValue_' + link.id + '" style="font-family:monospace;font-size:12px;color:' + (parentFolderPath ? '#34d399' : 'var(--text-muted)') + ';word-break:break-all;">' + (escapeHtml(parentFolderPath) || '未记录上级目录') + '</div>';
            html += '</div>';

            // 4. 电视剧季集（仅电视剧/剧集时展示，电影不展示剧集归属）
            if (isTV) {
                var sNum = link.season_number !== undefined && link.season_number !== null ? link.season_number : 1;
                var eNum = link.episode_number || 1;
                var sTxt = (sNum === 0) ? '特别篇 (第0季)' : ('第 ' + sNum + ' 季');
                var epFull = sTxt + ' 第 ' + eNum + ' 集';
                if (link.episode_title) {
                    epFull += ' · ' + link.episode_title;
                }
                html += '<div class="link-detail-prop-row">';
                html += '<div class="link-detail-prop-label"><span>剧集归属</span></div>';
                html += '<div class="link-detail-prop-value" style="color:#a5b4fc;font-weight:600;">' + escapeHtml(epFull) + '</div>';
                html += '</div>';
            }

            // 4. 真实文件名
            if (link.file_name) {
                html += '<div class="link-detail-prop-row">';
                html += '<div class="link-detail-prop-label"><span>真实文件名 (FileName)</span></div>';
                html += '<div class="link-detail-prop-value" style="font-family:monospace;word-break:break-all;">' + escapeHtml(link.file_name) + '</div>';
                html += '</div>';
            }

            // 5. 文件大小
            if (link.file_size && link.file_size > 0) {
                var sizeText = formatBytes(link.file_size) + ' (' + Number(link.file_size).toLocaleString() + ' 字节)';
                html += '<div class="link-detail-prop-row">';
                html += '<div class="link-detail-prop-label"><span>文件大小 (FileSize)</span></div>';
                html += '<div class="link-detail-prop-value" style="color:#6ee7b7;font-weight:600;">' + escapeHtml(sizeText) + '</div>';
                html += '</div>';
            }

            // 6. 文件 ID / PickCode
            if (link.file_id) {
                html += '<div class="link-detail-prop-row">';
                html += '<div class="link-detail-prop-label"><span>网盘文件 ID / PickCode (FileID)</span>';
                html += '<button class="btn btn-secondary btn-sm" style="padding:2px 8px;font-size:11px;" onclick="copyTextToClipboard(\'' + escapeHtml(link.file_id).replace(/'/g, "\\'") + '\', \'已复制文件 ID\')">📋 复制</button>';
                html += '</div>';
                html += '<div class="link-detail-prop-value" style="font-family:monospace;color:#93c5fd;">' + escapeHtml(link.file_id) + '</div>';
                html += '</div>';
            }

            // 7. SHA1 指纹
            if (link.sha1 || link.sha) {
                var shaVal = link.sha1 || link.sha;
                html += '<div class="link-detail-prop-row">';
                html += '<div class="link-detail-prop-label"><span>SHA1 文件指纹</span>';
                html += '<button class="btn btn-secondary btn-sm" style="padding:2px 8px;font-size:11px;" onclick="copyTextToClipboard(\'' + escapeHtml(shaVal).replace(/'/g, "\\'") + '\', \'已复制 SHA1 指纹\')">📋 复制</button>';
                html += '</div>';
                html += '<div class="link-detail-prop-value" style="font-family:monospace;font-size:12px;color:#cbd5e1;word-break:break-all;">' + escapeHtml(shaVal) + '</div>';
                html += '</div>';
            }

            // 8. 提取码 / 密码
            if (link.password) {
                html += '<div class="link-detail-prop-row">';
                html += '<div class="link-detail-prop-label"><span>提取码 / 访问密码</span>';
                html += '<button class="btn btn-secondary btn-sm" style="padding:2px 8px;font-size:11px;" onclick="copyTextToClipboard(\'' + escapeHtml(link.password).replace(/'/g, "\\'") + '\', \'已复制提取码\')">📋 复制</button>';
                html += '</div>';
                html += '<div class="link-detail-prop-value" style="color:#fde047;font-weight:700;">' + escapeHtml(link.password) + '</div>';
                html += '</div>';
            }

            // 9. 完整播放链接 URL
            html += '<div class="link-detail-prop-row">';
            html += '<div class="link-detail-prop-label"><span>完整播放链接 (URL)</span>';
            html += '<button class="btn btn-secondary btn-sm" style="padding:2px 8px;font-size:11px;" onclick="copyTextToClipboard(\'' + escapeHtml(link.url || '').replace(/'/g, "\\'") + '\', \'已复制完整播放链接\')">📋 复制完整链接</button>';
            html += '</div>';
            html += '<div class="link-detail-code-box">' + escapeHtml(link.url || '') + '</div>';
            html += '</div>';

            // 10. 元数据时间与主键 ID
            html += '<div class="link-detail-prop-row" style="background:rgba(0,0,0,0.2);">';
            html += '<div style="display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;font-size:11px;color:var(--text-muted);">';
            html += '<span>创建: ' + formatDateTime(link.created_at) + '</span>';
            html += '<span>更新: ' + formatDateTime(link.updated_at) + '</span>';
            html += '<span>记录ID: ' + escapeHtml(link.id || '') + '</span>';
            html += '</div></div>';

            html += '</div>';
            body.innerHTML = html;

            // 底部操作按钮
            var isSubLib = isCurrentLibReadOnly();
            var footerHtml = '<button class="btn" style="padding:6px 16px;font-size:13px;" onclick="closeModal(\'linkDetailModal\'); testPlayLink(\'' + link.id + '\');">▶ 立即播放</button>';
            if (!isSubLib) {
                footerHtml += '<button class="btn btn-secondary" style="padding:6px 14px;font-size:13px;" onclick="closeModal(\'linkDetailModal\'); openEditLinkModal(\'' + link.id + '\');">✏️ 编辑</button>';
            }
            footer.innerHTML = footerHtml;

            openModal('linkDetailModal');

            // 若尚未记录上级目录且为个人网盘，打开弹窗时后台静默自动反查一次
            if (!parentFolderPath && isCanSync) {
                syncSingleLinkParentFolder(link.id, true);
            }
        }

        function syncSingleLinkParentFolder(linkId, silent) {
            var btn = document.getElementById('btnSyncFolder_' + linkId);
            if (btn) {
                btn.disabled = true;
                btn.innerText = '⏳ 获取中...';
            }
            if (!silent) {
                showToast('正在反查网盘目录路径...');
            }
            fetch('/api/private/links/' + linkId + '/sync_parent_folder', {
                method: 'POST'
            })
            .then(function(res) { return res.json(); })
            .then(function(json) {
                if (json && json.success && json.parent_folder_path) {
                    var newPath = json.parent_folder_path;
                    if (state.links) {
                        for (var i = 0; i < state.links.length; i++) {
                            if (state.links[i].id === linkId) {
                                state.links[i].parent_folder_path = newPath;
                                state.links[i].parent_folder_name = newPath;
                                break;
                            }
                        }
                    }
                    var valEl = document.getElementById('parentFolderValue_' + linkId);
                    if (valEl) {
                        valEl.innerText = newPath;
                        valEl.style.color = '#34d399';
                    }
                    var actEl = document.getElementById('parentFolderAction_' + linkId);
                    if (actEl) {
                        actEl.innerHTML = '<button class="btn btn-secondary btn-sm" style="padding:2px 8px;font-size:11px;" onclick="copyTextToClipboard(\'' + escapeHtml(newPath).replace(/'/g, "\\'") + '\', \'已复制上级目录路径\')">📋 复制</button>';
                    }
                    if (!silent) {
                        showToast('网盘路径获取成功！');
                    }
                } else {
                    if (btn) {
                        btn.disabled = false;
                        btn.innerText = '🔄 自动获取网盘路径';
                    }
                    if (!silent) {
                        showToast(json && json.error ? json.error : '未能获取到网盘目录路径');
                    }
                }
            })
            .catch(function(err) {
                if (btn) {
                    btn.disabled = false;
                    btn.innerText = '🔄 自动获取网盘路径';
                }
                if (!silent) {
                    showToast('获取网盘路径异常: ' + err.message);
                }
            });
        }

        // ------------------ 站内搜索选片与详情选源/选集 (带分页与跨页批量选片) ------------------

        function openSearchAddModal() {
            if (checkReadOnlyGuard()) return;
            state.searchResultsList = [];
            state.checkedSearchVideos = {};
            state.searchQuery = '';
            state.searchPage = 1;
            state.searchTotalPages = 1;
            state.searchTotal = 0;
            document.getElementById('videoSearchInput').value = '';
            document.getElementById('videoSearchResults').innerHTML = '';
            document.getElementById('searchModalPagination').style.display = 'none';
            var box = document.getElementById('searchAddModalBox');
            if (box) box.classList.add('modal-fullscreen');
            updateSearchBatchBtn();
            openModal('searchAddModal');
            setTimeout(function() {
                var input = document.getElementById('videoSearchInput');
                if (input) input.focus();
            }, 100);
        }

        function searchVideos(targetPage) {
            var q = document.getElementById('videoSearchInput').value.trim();
            if (!q) {
                showToast('请输入片名或搜索关键词');
                return;
            }

            var isNewSearch = (typeof targetPage !== 'number');
            var page = isNewSearch ? 1 : targetPage;
            if (page < 1) page = 1;

            if (isNewSearch) {
                state.searchQuery = q;
                state.checkedSearchVideos = {}; // 新的关键字搜索时重置勾选
            }

            state.searchPage = page;
            var resBox = document.getElementById('videoSearchResults');
            var pagBox = document.getElementById('searchModalPagination');

            resBox.innerHTML = '<div style="text-align:center;color:var(--text-muted);padding:32px;"><div style="font-size:24px;margin-bottom:8px;">⏳</div>正在检索第 ' + page + ' 页影片...</div>';
            pagBox.style.display = 'none';

            fetch('/api/mv/videos/search?q=' + encodeURIComponent(state.searchQuery) + '&page=' + page + '&pageSize=' + state.searchPageSize)
                .then(function(res) { return res.json(); })
                .then(function(data) {
                    var items = data.data && data.data.items ? data.data.items : [];
                    var pag = data.data && data.data.pagination ? data.data.pagination : {};
                    state.searchResultsList = items;
                    state.searchTotal = pag.total || items.length;
                    state.searchTotalPages = pag.totalPages || Math.ceil(state.searchTotal / state.searchPageSize) || 1;

                    if (items.length === 0) {
                        resBox.innerHTML = '<div style="text-align:center;color:var(--text-muted);padding:32px;">未搜索到与 “' + state.searchQuery + '” 相关的影片</div>';
                        pagBox.style.display = 'none';
                        updateSearchBatchBtn();
                        return;
                    }

                    var html = '';
                    for (var i = 0; i < items.length; i++) {
                        var v = items[i];
                        var isChecked = !!state.checkedSearchVideos[v.id];
                        html += '<div class="search-video-item">';
                        html += '<input type="checkbox" class="search-video-chk" value="' + v.id + '"' + (isChecked ? ' checked' : '') + ' onchange="onSearchVideoCheckChange(this, ' + v.id + ')">';
                        var vTitleEsc = (v.title || '').replace(/'/g, "\\'");
                        var vTmdb = v.tmdbId || 0;
                        html += '<div class="search-video-clickable" onclick="openVideoDetailModal(' + v.id + ', \'create_movie\', ' + vTmdb + ', \'' + vTitleEsc + '\')">';
                        html += '<img referrerpolicy="no-referrer" src="' + (v.pic || '') + '" style="width:44px;height:62px;object-fit:cover;border-radius:6px;background:#1e293b;flex-shrink:0;" onerror="this.src=\'data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%2244%22 height=%2262%22><rect width=%22100%25%22 height=%22100%25%22 fill=%22%231e293b%22/><text x=%2250%25%22 y=%2250%25%22 fill=%22%2364748b%22 font-size=%2210%22 text-anchor=%22middle%22 dominant-baseline=%22middle%22>无封面</text></svg>\'">';
                        html += '<div style="flex:1;min-width:0;">';
                        html += '<div class="search-item-title" style="font-weight:700;color:#fff;font-size:15px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + v.title + '</div>';
                        html += '<div style="font-size:12px;color:var(--text-muted);margin-top:4px;">' + (v.year || '未知年代') + (v.typeName ? ' · ' + v.typeName : '') + (v.remark ? ' · <span style="color:#a5b4fc;">' + v.remark + '</span>' : '') + '</div>';
                        html += '</div></div>';
                        html += '<button class="btn btn-secondary" style="padding:4px 10px;font-size:12px;" onclick="openVideoDetailModal(' + v.id + ', \'create_movie\', ' + vTmdb + ', \'' + vTitleEsc + '\')">选源/选集</button>';
                        html += '</div>';
                    }
                    resBox.innerHTML = html;
                    resBox.scrollTop = 0;

                    // 渲染分页控件
                    document.getElementById('searchPageSummary').innerText = '共 ' + state.searchTotal + ' 部影视';
                    document.getElementById('searchPageInfo').innerText = '第 ' + state.searchPage + ' / ' + state.searchTotalPages + ' 页';
                    document.getElementById('searchPrevPageBtn').disabled = (state.searchPage <= 1);
                    document.getElementById('searchNextPageBtn').disabled = (state.searchPage >= state.searchTotalPages);
                    pagBox.style.display = 'flex';

                    updateSearchBatchBtn();
                })
                .catch(function(err) {
                    resBox.innerHTML = '<div style="color:#fca5a5;padding:14px;">搜索失败: ' + err.message + '</div>';
                    pagBox.style.display = 'none';
                    updateSearchBatchBtn();
                });
        }

        function onSearchVideoCheckChange(chk, vid) {
            if (chk.checked) {
                state.checkedSearchVideos[vid] = true;
            } else {
                delete state.checkedSearchVideos[vid];
            }
            updateSearchBatchBtn();
        }

        function toggleSelectAllSearchVideos() {
            var chks = document.querySelectorAll('.search-video-chk');
            if (chks.length === 0) return;
            var anyUnchecked = false;
            for (var i = 0; i < chks.length; i++) {
                if (!chks[i].checked) { anyUnchecked = true; break; }
            }
            for (var j = 0; j < chks.length; j++) {
                var chk = chks[j];
                chk.checked = anyUnchecked;
                var vid = chk.value;
                if (anyUnchecked) {
                    state.checkedSearchVideos[vid] = true;
                } else {
                    delete state.checkedSearchVideos[vid];
                }
            }
            updateSearchBatchBtn();
        }

        function updateSearchBatchBtn() {
            var checkedCount = Object.keys(state.checkedSearchVideos || {}).length;
            var btn = document.getElementById('btnBatchAddVideos');
            var countSpan = document.getElementById('searchSelectedCount');
            if (countSpan) countSpan.innerText = checkedCount;
            if (!btn) return;
            if (checkedCount > 0) {
                btn.disabled = false;
                btn.style.opacity = '1';
                btn.innerText = '批量添加入库 (已选 ' + checkedCount + ' 部)';
            } else {
                btn.disabled = true;
                btn.style.opacity = '0.5';
                btn.innerText = '批量添加入库 (0)';
            }
        }

        function changeSearchPage(delta) {
            var targetPage = state.searchPage + delta;
            if (targetPage < 1 || targetPage > state.searchTotalPages) return;
            searchVideos(targetPage);
        }

        function batchAddCheckedVideos() {
            if (!state.currentLib) return;
            var ids = Object.keys(state.checkedSearchVideos || {});
            if (ids.length === 0) {
                showToast('请先勾选需要入库的影片');
                return;
            }

            showToast('正在批量获取 ' + ids.length + ' 部影片并入库中...');
            var fetchPromises = ids.map(function(vid) {
                return fetch('/api/mv/videos/' + vid)
                    .then(function(res) { return res.json(); })
                    .then(function(data) {
                        var v = data.data;
                        var cleaned = cleanSeasonFromTitle(v.title);
                        var finalTitle = cleaned.title || v.title;
                        var finalTypeId = (cleaned.season >= 0) ? 2 : (v.typeId || 1);
                        // 未单独选源/集时，仅添加影片元数据，不添加全量海量播放源
                        return fetch('/api/private/libraries/' + state.currentLib.id + '/movies', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                vod_id: String(v.id),
                                tmdb_id: v.tmdbId || 0,
                                type_id: finalTypeId,
                                title: finalTitle,
                                year: String(v.year || ''),
                                cover_url: v.pic || '',
                                backdrop_url: formatBackdropUrl(v.backdropPath || v.backdrop_path || ''),
                                summary: v.content || '',
                                genres: Array.isArray(v.tags) ? v.tags.join(',') : '',
                                directors: v.director || '',
                                actors: v.starring || '',
                                area: v.area || '',
                                links: []
                            })
                        });
                    });
            });

            Promise.all(fetchPromises)
                .then(function() {
                    showToast('已成功批量导入 ' + ids.length + ' 部影片！');
                    state.checkedSearchVideos = {};
                    closeModal('searchAddModal');
                    loadMovies();
                })
                .catch(function(err) {
                    showToast('批量入库失败: ' + err.message);
                });
        }

        // 为指定视频的各播放源打上季号标记 (season_number)
        function tagSourcesWithSeason(v, sNum) {
            if (!v) return;
            for (var p in (v.panList || {})) {
                var list = v.panList[p] || [];
                for (var j = 0; j < list.length; j++) {
                    list[j].season_number = sNum;
                }
            }
            if (Array.isArray(v.downList)) {
                for (var k = 0; k < v.downList.length; k++) {
                    v.downList[k].season_number = sNum;
                }
            }
        }

        // 通过 TMDB ID 与片名并发双轨探查属于该剧在云端的所有季记录
        async function fetchAllSeasonsForVideo(baseVideo, explicitTmdbId, explicitTitle) {
            var targetTmdbId = explicitTmdbId || baseVideo.tmdbId || 0;
            var cleanedObj = cleanSeasonFromTitle(explicitTitle || baseVideo.title);
            var cleanTitle = cleanedObj.title || explicitTitle || baseVideo.title;
            var isTv = isSeriesTypeId(baseVideo.typeId) || (cleanedObj.season >= 0);

            // 仅对剧集或明确存在 TMDB ID 的作品执行多季探查
            if (!isTv && targetTmdbId <= 0) {
                return [baseVideo];
            }

            var candidateItemsMap = {};
            candidateItemsMap[String(baseVideo.id)] = {
                id: baseVideo.id,
                title: baseVideo.title,
                tmdbId: targetTmdbId,
                video: baseVideo
            };

            var searchPromises = [];
            // 轨 1：若有 TMDB ID，直接精准查询同属该 TMDB ID 的所有季
            if (targetTmdbId > 0) {
                searchPromises.push(
                    fetch('/api/mv/videos/search?tmdbId=' + targetTmdbId)
                        .then(function(res) { return res.json(); })
                        .then(function(data) {
                            return (data.data && data.data.items) || [];
                        })
                        .catch(function() { return []; })
                );
            }

            // 轨 2：根据干净片名检索包含“第N季”的候选条目
            if (cleanTitle) {
                searchPromises.push(
                    fetch('/api/mv/videos/search?q=' + encodeURIComponent(cleanTitle))
                        .then(function(res) { return res.json(); })
                        .then(function(data) {
                            return (data.data && data.data.items) || [];
                        })
                        .catch(function() { return []; })
                );
            }

            var resultsArray = await Promise.all(searchPromises);
            for (var r = 0; r < resultsArray.length; r++) {
                var list = resultsArray[r];
                for (var k = 0; k < list.length; k++) {
                    var item = list[k];
                    var itemClean = cleanSeasonFromTitle(item.title);
                    var isSameTmdb = (targetTmdbId > 0 && item.tmdbId && Number(item.tmdbId) === Number(targetTmdbId));
                    var isSameTitle = (cleanTitle && itemClean.title === cleanTitle);
                    if (isSameTmdb || isSameTitle) {
                        if (!candidateItemsMap[String(item.id)]) {
                            candidateItemsMap[String(item.id)] = {
                                id: item.id,
                                title: item.title,
                                tmdbId: item.tmdbId || targetTmdbId,
                                video: null
                            };
                        }
                    }
                }
            }

            var allKeys = Object.keys(candidateItemsMap);
            if (allKeys.length <= 1) {
                return [baseVideo];
            }

            // 并发获取其他季条目的详情数据
            var detailPromises = allKeys.map(function(k) {
                var c = candidateItemsMap[k];
                if (c.video) return Promise.resolve(c.video);
                return fetch('/api/mv/videos/' + c.id)
                    .then(function(res) { return res.json(); })
                    .then(function(data) {
                        return data.data;
                    })
                    .catch(function() { return null; });
            });

            var fetchedVideos = await Promise.all(detailPromises);
            return fetchedVideos.filter(Boolean);
        }

        // 将所有季的数据聚合成单一全景视频大对象 (按季号升序排列)
        function mergeAllSeasonsIntoSingleVideo(videoList, explicitTitle) {
            if (!videoList || videoList.length === 0) return null;

            // 预先提取每季的季号
            var parsedList = [];
            for (var vi = 0; vi < videoList.length; vi++) {
                var vItem = videoList[vi];
                var sObj = cleanSeasonFromTitle(vItem.title);
                var sNum = (sObj.season >= 0) ? sObj.season : (vi + 1);
                parsedList.push({ video: vItem, season: sNum });
            }

            // 按季号升序排列
            parsedList.sort(function(a, b) { return a.season - b.season; });

            if (parsedList.length === 1) {
                var single = parsedList[0].video;
                tagSourcesWithSeason(single, parsedList[0].season);
                single.seasonList = [parsedList[0].season];
                return single;
            }

            var base = parsedList[0].video;
            var cleanMainTitle = explicitTitle ? cleanSeasonFromTitle(explicitTitle).title : (cleanSeasonFromTitle(base.title).title || base.title);

            var merged = Object.assign({}, base);
            merged.title = cleanMainTitle;
            merged.typeId = 2; // 明确标为剧集
            merged.panList = {};
            merged.downList = [];

            var seasonsSet = {};
            for (var j = 0; j < parsedList.length; j++) {
                var itemV = parsedList[j].video;
                var seasonNum = parsedList[j].season;
                seasonsSet[seasonNum] = true;

                tagSourcesWithSeason(itemV, seasonNum);

                // 合并 panList
                for (var panName in (itemV.panList || {})) {
                    if (!merged.panList[panName]) merged.panList[panName] = [];
                    merged.panList[panName] = merged.panList[panName].concat(itemV.panList[panName] || []);
                }

                // 合并 downList
                if (Array.isArray(itemV.downList)) {
                    merged.downList = merged.downList.concat(itemV.downList);
                }
            }

            var seasonsArr = Object.keys(seasonsSet).map(Number).sort(function(a, b) { return a - b; });
            merged.seasonList = seasonsArr;
            return merged;
        }

        // 打开影片详情选源弹框 (mode: 'create_movie' 添加入库，'append_links' 追加链接至已有影片，支持 preferredTmdbId 跨季聚合)
        function openVideoDetailModal(vodId, mode, preferredTmdbId, preferredTitle) {
            state.detailModalMode = mode || 'create_movie';
            state.currentDetailVideo = null;
            state.currentActiveSourceTab = 'all';
            state.currentActiveSeasonTab = 'all';

            var seasonTabsEl = document.getElementById('vdSeasonTabs');
            if (seasonTabsEl) {
                seasonTabsEl.style.display = 'none';
                seasonTabsEl.innerHTML = '';
            }
            document.getElementById('vdSourceGroupTabs').innerHTML = '';
            document.getElementById('detailSourcesList').innerHTML = '<div style="text-align:center;color:var(--text-muted);padding:24px;"><div style="font-size:24px;margin-bottom:8px;">⏳</div>正在加载片源与全季聚合数据...</div>';

            var btnCancel = document.getElementById('btnCancelDetailModal');
            var btnConfirm = document.getElementById('btnConfirmDetailAdd');
            var headerEl = document.getElementById('detailVideoHeader');
            var listEl = document.getElementById('detailSourcesList');

            if (state.detailModalMode === 'append_links') {
                if (btnCancel) btnCancel.innerText = '取消关闭';
                if (btnConfirm) btnConfirm.innerText = '确认追加所选源到当前影片';
                if (headerEl) headerEl.style.display = 'none';
                if (listEl) { listEl.style.maxHeight = 'none'; listEl.style.flex = '1'; }
            } else {
                if (btnCancel) btnCancel.innerText = '返回搜索列表';
                if (btnConfirm) btnConfirm.innerText = '确认添加入库';
                if (headerEl) headerEl.style.display = 'flex';
                if (listEl) { listEl.style.maxHeight = 'none'; listEl.style.flex = '1'; }
            }

            openModal('videoDetailModal');

            // 1. 获取首条基准片源详情
            fetch('/api/mv/videos/' + vodId)
                .then(function(res) { return res.json(); })
                .then(async function(data) {
                    var baseV = data.data;
                    if (!baseV) throw new Error('未获取到视频数据');

                    // 2. 自动通过 TMDB ID 与片名探测云端是否具有全剧各季记录并聚合
                    var allSeasonVideos = await fetchAllSeasonsForVideo(baseV, preferredTmdbId, preferredTitle);
                    var v = mergeAllSeasonsIntoSingleVideo(allSeasonVideos, preferredTitle);
                    state.currentDetailVideo = v;

                    var isMultiSeason = v.seasonList && v.seasonList.length > 1;
                    var tmdbHint = (preferredTmdbId || v.tmdbId) ? ('<span style="background:rgba(56,189,248,0.2);color:#38bdf8;border:1px solid rgba(56,189,248,0.4);padding:1px 6px;border-radius:4px;font-size:11px;font-weight:700;margin-left:6px;">TMDB: ' + (preferredTmdbId || v.tmdbId) + (isMultiSeason ? ' (已聚合全部 ' + v.seasonList.length + ' 季)' : '') + '</span>') : '';

                    var modalTitle = (state.detailModalMode === 'append_links') ?
                        ('为《' + (state.currentMovie ? state.currentMovie.title : v.title) + '》追加播放源与选集') :
                        (v.title + (isMultiSeason ? ' (全 ' + v.seasonList.length + ' 季全景)' : '') + ' - 选源与选集');
                    document.getElementById('vdModalTitle').innerText = modalTitle;
                    document.getElementById('vdTitleText').innerText = v.title;
                    document.getElementById('vdCoverImg').src = v.pic || '';
                    document.getElementById('vdTaglineText').innerHTML = (v.year || '未知年代') + ' · ' + (isMultiSeason ? ('全 ' + v.seasonList.length + ' 季 · ') : '') + (v.typeName || '') + (v.area ? ' · ' + v.area : '') + tmdbHint;
                    document.getElementById('vdCastText').innerText = '导演: ' + (v.director || '未知') + '  主演: ' + (v.starring || '未知');
                    var descEl = document.getElementById('vdDescText');
                    if (descEl) {
                        descEl.innerText = v.content || '暂无详细剧情简介。';
                        descEl.setAttribute('data-full-desc', v.content || '');
                        descEl.title = v.content ? ('点击可查看完整简介：\n' + v.content) : '暂无详细剧情简介';
                    }

                    renderSeasonTabs(v);
                    renderSourceGroupTabs(v);
                    renderDetailSourcesList(v);
                })
                .catch(function(err) {
                    document.getElementById('detailSourcesList').innerHTML = '<div style="color:#fca5a5;padding:14px;">获取详情失败: ' + err.message + '</div>';
                });
        }

        // 第三级页面：为当前影片打开站内选源与选集弹框 (智能通过 TMDB ID 聚齐各季)
        function openSelectSourcesForCurrentMovie() {
            if (!state.currentMovie) return;
            var movie = state.currentMovie;
            var vodId = movie.vod_id;
            var tmdbId = movie.tmdb_id || 0;
            var cleanObj = cleanSeasonFromTitle(movie.title || '');
            var searchTitle = cleanObj.title || movie.title || '';

            // 若已有有效的站内 vod_id，同时透传 tmdbId 与主剧名
            if (vodId && vodId !== movie.id && !isNaN(Number(vodId))) {
                openVideoDetailModal(vodId, 'append_links', tmdbId, searchTitle);
                return;
            }

            if (!searchTitle && !tmdbId) {
                alert('影片片名与 TMDB ID 均为空，无法进行站内搜索');
                return;
            }

            showToast('正在通过 TMDB ID / 片名检索全部季播放源...');
            var searchUrl = (tmdbId > 0) ? ('/api/mv/videos/search?tmdbId=' + tmdbId) : ('/api/mv/videos/search?q=' + encodeURIComponent(searchTitle));

            fetch(searchUrl)
                .then(function(res) { return res.json(); })
                .then(function(data) {
                    var list = (data.data && data.data.items) || data.list || [];
                    if (!list || list.length === 0) {
                        // 若按 tmdbId 搜索为空，平滑降级按片名搜索
                        if (tmdbId > 0 && searchTitle) {
                            return fetch('/api/mv/videos/search?q=' + encodeURIComponent(searchTitle))
                                .then(function(r) { return r.json(); })
                                .then(function(d2) {
                                    var l2 = (d2.data && d2.data.items) || [];
                                    if (!l2 || l2.length === 0) {
                                        alert('站内未找到与《' + searchTitle + '》相关的影视片源');
                                        return;
                                    }
                                    state.currentMovie.vod_id = String(l2[0].id);
                                    openVideoDetailModal(l2[0].id, 'append_links', tmdbId, searchTitle);
                                });
                        }
                        alert('站内未找到与《' + searchTitle + '》相关的影视片源');
                        return;
                    }

                    // 优先寻找同名或第一个季
                    var matched = list[0];
                    for (var i = 0; i < list.length; i++) {
                        var itClean = cleanSeasonFromTitle(list[i].title);
                        if (itClean.title === searchTitle) {
                            matched = list[i];
                            break;
                        }
                    }

                    state.currentMovie.vod_id = String(matched.id);
                    openVideoDetailModal(matched.id, 'append_links', tmdbId, searchTitle);
                })
                .catch(function(err) {
                    alert('站内搜索失败: ' + err.message);
                });
        }

        // 选源弹框底部确认操作分发
        function handleDetailModalConfirm() {
            if (state.detailModalMode === 'append_links') {
                confirmAppendLinksToMovie();
            } else {
                confirmAddDetailVideo();
            }
        }

        // 从选源弹框勾选项中精准提取全部播放链接 (包含全网盘分享链接、子文件、外挂字幕与磁力/ED2K)
        function extractLinksFromCheckedInputs() {
            var sourceChks = document.querySelectorAll('.source-item-chk:checked');
            var fileChks = document.querySelectorAll('.file-item-chk:checked');

            var links = [];
            for (var i = 0; i < sourceChks.length; i++) {
                var sc = sourceChks[i];
                var sNum = parseInt(sc.dataset.seasonNumber, 10) || 1;
                links.push({
                    link_type: sc.dataset.type,
                    provider: sc.dataset.provider || '',
                    url: sc.dataset.url,
                    password: sc.dataset.pwd || '',
                    remark: sc.dataset.remark || '',
                    season_number: sNum,
                    episode_number: 1
                });
            }

            for (var j = 0; j < fileChks.length; j++) {
                var fc = fileChks[j];
                var panIdx = fc.dataset.panIdx;
                var panName = fc.dataset.provider || '';
                var panDisplay = PROVIDER_NAMES[panName] || panName;
                var fullUrl = fc.dataset.fullUrl || '';
                var pwd = fc.dataset.pwd || '';
                var cid = fc.dataset.cid || '';
                var fid = fc.dataset.fid || '';
                if (fid && fid.indexOf('eyJ') !== -1) {
                    try {
                        var dec = JSON.parse(atob(fid));
                        if (dec && (dec.fid || dec.file_id || dec.target_id || dec.fs_id)) {
                            fid = String(dec.fid || dec.file_id || dec.target_id || dec.fs_id);
                        }
                    } catch (e) {}
                }
                var fname = fc.dataset.fname || '';
                var fsize = parseInt(fc.dataset.size, 10) || 0;
                var sNum = parseInt(fc.dataset.seasonNumber, 10) || 1;
                var fsha = fc.dataset.sha || '';

                var parsedEp = 0;
                var parsedSe = 0;
                if (fname) {
                    var mSe = fname.match(/(?:S(\d{1,2}))?E(\d{1,4})/i);
                    if (mSe) {
                        if (mSe[1]) parsedSe = parseInt(mSe[1], 10);
                        if (mSe[2]) parsedEp = parseInt(mSe[2], 10);
                    } else {
                        var mEpOnly = fname.match(/(?:EP|第)\s*(\d{1,4})\s*[集话]?/i);
                        if (mEpOnly && mEpOnly[1]) {
                            parsedEp = parseInt(mEpOnly[1], 10);
                        }
                    }
                }
                var finalSe = parsedSe > 0 ? parsedSe : sNum;
                var finalEp = parsedEp > 0 ? parsedEp : (j + 1);

                // 查找同目录下用户勾选的字幕
                var subChks = document.querySelectorAll('.file-sub-chk[data-pan-idx="' + panIdx + '"]:checked');
                var selectedSubs = [];
                for (var s = 0; s < subChks.length; s++) {
                    selectedSubs.push({
                        fid: subChks[s].dataset.fid,
                        name: subChks[s].dataset.name
                    });
                }

                // 必须剥离原 URL 上的所有现有 hash 片段 (#...)，获取纯净的基础分享 URL，彻底防止多重嵌套
                var baseUrl = fullUrl.split('#')[0];
                if (pwd && baseUrl.indexOf('password=') === -1 && baseUrl.indexOf('pwd=') === -1 && baseUrl.indexOf('code=') === -1) {
                    baseUrl += (baseUrl.indexOf('?') === -1 ? '?' : '&') + 'password=' + pwd;
                }

                var finalUrl = baseUrl;
                var finalRemark = panDisplay + ' / ' + fname;

                if (selectedSubs.length > 0) {
                    var payload = {
                        fid: fid,
                        name: fname,
                        subtitles: selectedSubs
                    };
                    var b64 = btoa(unescape(encodeURIComponent(JSON.stringify(payload))));
                    finalUrl += '#fid=' + b64;
                    if (fsize > 0) {
                        finalUrl += '&size=' + fsize;
                    }
                    finalRemark += ' (+' + selectedSubs.length + '外挂字幕)';
                } else {
                    if (cid) {
                        finalUrl += '#cid=' + cid + '&fid=' + fid;
                    } else {
                        finalUrl += '#fid=' + fid;
                    }
                    if (fsize > 0) {
                        finalUrl += '&size=' + fsize;
                    }
                }

                links.push({
                    link_type: 'pan',
                    provider: panName,
                    url: finalUrl,
                    password: pwd,
                    remark: finalRemark,
                    season_number: finalSe,
                    episode_number: finalEp,
                    file_size: fsize,
                    file_id: fid,
                    file_name: fname,
                    sha1: fsha,
                    sha: fsha
                });
            }

            return links;
        }

        // 追加所选源至已有影片
        function confirmAppendLinksToMovie() {
            if (!state.currentDetailVideo || !state.currentMovie) return;
            var links = extractLinksFromCheckedInputs();

            if (links.length === 0) {
                alert('请先勾选要追加的播放源或具体文件');
                return;
            }

            var cleaned = cleanSeasonFromTitle(state.currentDetailVideo.title);
            for (var li = 0; li < links.length; li++) {
                if (links[li].season_number === undefined || links[li].season_number === null || (links[li].season_number <= 0 && links[li].episode_number <= 0)) {
                    links[li].season_number = (cleaned.season >= 0) ? cleaned.season : 1;
                }
            }

            fetch('/api/private/movies/' + state.currentMovie.id + '/links', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ links: links })
            })
            .then(function(res) { return res.json(); })
            .then(function(resData) {
                if (resData.error || resData.message && !resData.success) {
                    throw new Error(resData.error || resData.message);
                }
                showToast('已成功追加 ' + links.length + ' 条播放源！');
                closeModal('videoDetailModal');
                loadLinks();
                loadMovies();
            })
            .catch(function(err) {
                showToast('追加失败: ' + err.message);
            });
        }

        // 渲染分季切换 Tab (仅当存在多个季时展示)
        function renderSeasonTabs(v) {
            var tabsBox = document.getElementById('vdSeasonTabs');
            if (!tabsBox) return;
            var seasons = v.seasonList || [];
            if (seasons.length <= 1) {
                tabsBox.style.display = 'none';
                return;
            }

            tabsBox.style.display = 'flex';
            var curSeason = state.currentActiveSeasonTab || 'all';

            var html = '';
            html += '<button class="source-group-tab-btn' + (curSeason === 'all' ? ' active' : '') + '" style="border-color:rgba(56,189,248,0.5);" onclick="switchSeasonTab(\'all\')">🌟 全部季 (' + seasons.length + ' 季全景)</button>';
            for (var i = 0; i < seasons.length; i++) {
                var s = seasons[i];
                var isActive = (String(curSeason) === String(s));
                html += '<button class="source-group-tab-btn' + (isActive ? ' active' : '') + '" onclick="switchSeasonTab(' + s + ')">第 ' + s + ' 季</button>';
            }
            tabsBox.innerHTML = html;
        }

        function switchSeasonTab(season) {
            state.currentActiveSeasonTab = season;
            if (state.currentDetailVideo) {
                renderSeasonTabs(state.currentDetailVideo);
                renderSourceGroupTabs(state.currentDetailVideo);
                renderDetailSourcesList(state.currentDetailVideo);
            }
        }

        // 渲染按源类型分组 Tab (联动当前所选季，按网盘保序与磁力跟随规则排列)
        function renderSourceGroupTabs(v) {
            var tabsBox = document.getElementById('vdSourceGroupTabs');
            var panList = v.panList || {};
            var downList = v.downList || [];
            var curSeason = state.currentActiveSeasonTab || 'all';

            var totalPanCount = 0;
            var panCounts = {};
            for (var p in panList) {
                var pList = panList[p] || [];
                var count = 0;
                for (var pi = 0; pi < pList.length; pi++) {
                    if (curSeason === 'all' || String(pList[pi].season_number || 1) === String(curSeason)) {
                        count++;
                    }
                }
                panCounts[p] = count;
                totalPanCount += count;
            }

            var downCount = 0;
            for (var di = 0; di < downList.length; di++) {
                if (curSeason === 'all' || String(downList[di].season_number || 1) === String(curSeason)) {
                    downCount++;
                }
            }
            var totalCount = totalPanCount + downCount;

            var tabItems = [];
            for (var panName in panList) {
                var count = panCounts[panName] || 0;
                if (count > 0 || state.currentActiveSourceTab === panName) {
                    tabItems.push({
                        key: panName,
                        name: PROVIDER_NAMES[panName] || panName,
                        count: count,
                        rank: getSourceLineOrderRank(panName)
                    });
                }
            }

            if (downCount > 0 || state.currentActiveSourceTab === 'down') {
                tabItems.push({
                    key: 'down',
                    name: '磁力和ED2K',
                    count: downCount,
                    rank: getSourceLineOrderRank('down')
                });
            }

            // 严格根据线路保序 rank 升序排列 (115网盘后紧随磁力和ED2K，再到其他网盘)
            tabItems.sort(function(a, b) {
                return a.rank - b.rank;
            });

            var html = '';
            html += '<button class="source-group-tab-btn' + (state.currentActiveSourceTab === 'all' ? ' active' : '') + '" onclick="switchSourceGroupTab(\'all\')">全部源 (' + totalCount + ')</button>';

            for (var ti = 0; ti < tabItems.length; ti++) {
                var item = tabItems[ti];
                var isActive = (state.currentActiveSourceTab === item.key);
                html += '<button class="source-group-tab-btn' + (isActive ? ' active' : '') + '" onclick="switchSourceGroupTab(\'' + item.key + '\')">' + item.name + ' (' + item.count + ')</button>';
            }

            tabsBox.innerHTML = html;
        }

        function switchSourceGroupTab(tabName) {
            state.currentActiveSourceTab = tabName;
            if (state.currentDetailVideo) {
                renderSourceGroupTabs(state.currentDetailVideo);
                renderDetailSourcesList(state.currentDetailVideo);
            }
        }

        function renderDetailSourcesList(v) {
            var container = document.getElementById('detailSourcesList');
            var panList = v.panList || {};
            var downList = v.downList || [];
            var html = '';
            var currentTab = state.currentActiveSourceTab;
            var curSeason = state.currentActiveSeasonTab || 'all';
            var isMultiSeason = v.seasonList && v.seasonList.length > 1;

            var allCards = [];
            var globalPanIdx = 0;

            // 1. 收集网盘源
            for (var panName in panList) {
                var links = panList[panName] || [];
                for (var i = 0; i < links.length; i++) {
                    var link = links[i];
                    var sNum = link.season_number || 1;
                    var thisPanIdx = globalPanIdx++;

                    if (curSeason !== 'all' && String(sNum) !== String(curSeason)) {
                        continue;
                    }
                    if (currentTab !== 'all' && currentTab !== panName) {
                        continue;
                    }

                    allCards.push({
                        type: 'pan',
                        panName: panName,
                        link: link,
                        season: sNum,
                        panIdx: thisPanIdx,
                        rank: getSourceLineOrderRank(panName)
                    });
                }
            }

            // 2. 收集磁力/ED2K源
            if (currentTab === 'all' || currentTab === 'down') {
                for (var j = 0; j < downList.length; j++) {
                    var down = downList[j];
                    var sNumDown = down.season_number || 1;

                    if (curSeason !== 'all' && String(sNumDown) !== String(curSeason)) {
                        continue;
                    }

                    allCards.push({
                        type: 'down',
                        down: down,
                        season: sNumDown,
                        rank: getSourceLineOrderRank('down')
                    });
                }
            }

            // 3. 统一保序：先按 season 升序，同季内严格按照线路 rank 升序 (115网盘 -> 磁力和ED2K -> 百度 -> 夸克...)
            allCards.sort(function(a, b) {
                if (a.season !== b.season) return a.season - b.season;
                return a.rank - b.rank;
            });

            // 4. 渲染卡片
            for (var c = 0; c < allCards.length; c++) {
                var item = allCards[c];
                if (item.type === 'pan') {
                    var link = item.link;
                    var panName = item.panName;
                    var curPanIdx = item.panIdx;
                    var sNum = item.season;
                    var cardId = 'pan_card_' + curPanIdx;
                    var fullShareUrl = toShareUrl(link.url, panName);
                    var panDisplayName = PROVIDER_NAMES[panName] || panName;

                    var apiRemark = (link.remark || link.info || '').trim();
                    var linkTitle = (link.title || '').trim();
                    var finalRemark = (apiRemark ? apiRemark + ' ' : '') + (linkTitle || (panDisplayName + '播放源'));

                    html += '<div class="source-card" id="' + cardId + '">';
                    html += '<div class="source-card-main">';
                    html += '<div class="source-card-left">';
                    html += '<input type="checkbox" class="source-item-chk" data-type="pan" data-season-number="' + sNum + '" data-provider="' + panName + '" data-url="' + fullShareUrl + '" data-pwd="' + (link.code || '') + '" data-remark="' + finalRemark.replace(/"/g, '&quot;') + '">';
                    html += '<div style="flex:1;min-width:0;">';
                    html += '<div style="display:flex;align-items:center;gap:6px;margin-bottom:2px;flex-wrap:wrap;">';
                    if (isMultiSeason || sNum > 0) {
                        html += '<span class="link-type-badge" style="background:#0284c7;color:#fff;font-weight:700;">第 ' + sNum + ' 季</span>';
                    }
                    html += '<span class="link-type-badge lt-pan">' + panDisplayName + '</span>';
                    if (apiRemark) {
                        html += '<span style="background:rgba(99,102,241,0.25);color:#c7d2fe;border:1px solid rgba(99,102,241,0.4);padding:1px 5px;border-radius:4px;font-size:11px;font-weight:700;">' + apiRemark + '</span>';
                    }
                    if (linkTitle) {
                        html += '<span style="font-weight:700;color:#fff;font-size:13px;">' + linkTitle + '</span>';
                    }
                    if (link.code) {
                        html += '<span style="font-size:11px;color:#a5b4fc;background:rgba(255,255,255,0.08);padding:1px 5px;border-radius:4px;flex-shrink:0;">码: ' + link.code + '</span>';
                    }
                    html += '</div>';
                    html += '<div style="font-size:11px;color:var(--text-muted);font-family:monospace;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="' + fullShareUrl + '"><span style="color:#94a3b8;font-weight:600;">链接:</span> ' + fullShareUrl + '</div>';
                    html += '</div></div>';
                    html += '<button class="icon-btn" style="flex-shrink:0;align-self:center;margin-left:8px;padding:4px 10px;font-size:11px;white-space:nowrap;" onclick="toggleExpandPanFiles(' + curPanIdx + ', \'' + fullShareUrl + '\', \'' + (link.code || '') + '\', \'' + panName + '\')">📂 选择具体文件</button>';
                    html += '</div>';
                    html += '<div class="file-tree-container" id="pan_tree_' + curPanIdx + '" style="display:none;"></div>';
                    html += '</div>';
                } else {
                    var down = item.down;
                    var sNumDown = item.season;
                    var magnetTag = (down.quality ? '[' + down.quality + (down.size ? ' ' + formatSizeMB(down.size) : '') + ']' : '').trim();
                    var magnetTitle = (down.title || '磁力下载').trim();
                    var magnetRemark = (magnetTag ? magnetTag + ' ' : '') + magnetTitle;

                    html += '<div class="source-card">';
                    html += '<div class="source-card-main">';
                    html += '<div class="source-card-left">';
                    html += '<input type="checkbox" class="source-item-chk" data-type="magnet" data-season-number="' + sNumDown + '" data-url="' + down.url + '" data-remark="' + magnetRemark.replace(/"/g, '&quot;') + '">';
                    html += '<div style="flex:1;min-width:0;">';
                    html += '<div style="display:flex;align-items:center;gap:6px;margin-bottom:2px;flex-wrap:wrap;">';
                    if (isMultiSeason || sNumDown > 0) {
                        html += '<span class="link-type-badge" style="background:#0284c7;color:#fff;font-weight:700;">第 ' + sNumDown + ' 季</span>';
                    }
                    html += '<span class="link-type-badge lt-magnet">磁力/ED2K</span>';
                    if (magnetTag) {
                        html += '<span style="background:rgba(245,158,11,0.25);color:#fde68a;border:1px solid rgba(245,158,11,0.4);padding:1px 5px;border-radius:4px;font-size:11px;font-weight:700;">' + magnetTag + '</span>';
                    }
                    html += '<span style="font-weight:700;color:#fff;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + magnetTitle + '</span>';
                    html += '</div>';
                    html += '<div style="font-size:11px;color:var(--text-muted);font-family:monospace;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="' + down.url + '"><span style="color:#94a3b8;font-weight:600;">链接:</span> ' + down.url + '</div>';
                    html += '</div></div></div></div>';
                }
            }

            if (!html) {
                html = '<div style="font-size:13px;color:var(--text-muted);padding:20px;text-align:center;">此分类下暂无可解析播放线路</div>';
            }

            container.innerHTML = html;
        }

        // --- 网盘与线路自定义排序模态窗口控制 ---
        var tempPanOrderList = [];

        function openPanOrderModal() {
            tempPanOrderList = currentPanOrder.slice();
            renderPanOrderModalList();
            openModal('panOrderModal');
        }

        function renderPanOrderModalList() {
            var box = document.getElementById('panOrderListContainer');
            if (!box) return;
            var html = '';

            for (var i = 0; i < tempPanOrderList.length; i++) {
                var id = tempPanOrderList[i];
                var pItem = PAN_ORDER_ITEMS.find(function(it) { return it.id === id; });
                var pName = pItem ? pItem.name : (PROVIDER_NAMES[id] || ('网盘 ' + id));

                html += '<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 12px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);border-radius:8px;">';
                html += '<div style="display:flex;align-items:center;gap:10px;">';
                html += '<span style="font-size:12px;color:var(--text-muted);width:20px;font-family:monospace;">' + (i + 1) + '.</span>';
                html += '<span style="font-weight:600;color:#fff;font-size:14px;">' + pName + '</span>';
                if (id === '7') {
                    html += '<span style="font-size:11px;color:#38bdf8;background:rgba(56,189,248,0.15);padding:1px 6px;border-radius:4px;font-weight:700;">115</span>';
                }
                html += '</div>';
                html += '<div style="display:flex;gap:6px;">';
                html += '<button class="icon-btn" style="padding:3px 8px;font-size:12px;" ' + (i === 0 ? 'disabled style="opacity:0.3;"' : '') + ' onclick="movePanOrderItem(' + i + ', -1)">⬆ 上移</button>';
                html += '<button class="icon-btn" style="padding:3px 8px;font-size:12px;" ' + (i === tempPanOrderList.length - 1 ? 'disabled style="opacity:0.3;"' : '') + ' onclick="movePanOrderItem(' + i + ', 1)">⬇ 下移</button>';
                html += '</div>';
                html += '</div>';

                // 在 115网盘 正下方紧随展示磁力和ED2K伴随提示
                if (id === '7') {
                    html += '<div style="display:flex;align-items:center;gap:8px;padding:6px 12px;background:rgba(245,158,11,0.08);border:1px dashed rgba(245,158,11,0.3);border-radius:6px;margin:2px 0 2px 28px;">';
                    html += '<span style="font-size:13px;">🧲</span>';
                    html += '<span style="font-size:12px;color:#fde68a;font-weight:600;">磁力和ED2K链接 (自动紧随 115网盘 之后)</span>';
                    html += '</div>';
                }
            }

            box.innerHTML = html;
        }

        function movePanOrderItem(idx, direction) {
            var targetIdx = idx + direction;
            if (targetIdx < 0 || targetIdx >= tempPanOrderList.length) return;
            var item = tempPanOrderList.splice(idx, 1)[0];
            tempPanOrderList.splice(targetIdx, 0, item);
            renderPanOrderModalList();
        }

        function resetPanOrderToDefault() {
            tempPanOrderList = DEFAULT_PAN_ORDER.slice();
            renderPanOrderModalList();
            showToast('已重置为默认顺序，点击保存后生效');
        }

        function confirmSavePanOrder() {
            savePanOrder(tempPanOrderList, function() {
                closeModal('panOrderModal');
                showToast('线路显示顺序已保存！');
                if (state.currentDetailVideo) {
                    renderSourceGroupTabs(state.currentDetailVideo);
                    renderDetailSourcesList(state.currentDetailVideo);
                }
            });
        }

        function selectAllDetailSources(select) {
            var chks = document.querySelectorAll('.source-item-chk, .file-item-chk');
            for (var i = 0; i < chks.length; i++) {
                chks[i].checked = select;
            }
        }

        // 展开与浏览网盘内的文件树
        function toggleExpandPanFiles(panIdx, shareUrl, pwd, panName, targetFolderId, folderName) {
            var treeBox = document.getElementById('pan_tree_' + panIdx);
            if (!treeBox) return;

            if (!targetFolderId && treeBox.style.display === 'block') {
                treeBox.style.display = 'none';
                return;
            }

            treeBox.style.display = 'block';
            treeBox.innerHTML = '<div style="font-size:12px;color:var(--text-muted);padding:10px;text-align:center;">正在解析网盘目录树...</div>';

            var fullUrl = toShareUrl(shareUrl, panName);
            var queryUrl = '/api/list?share_url=' + encodeURIComponent(fullUrl) +
                           '&code=' + encodeURIComponent(pwd || '') +
                           '&parent_file_id=' + encodeURIComponent(targetFolderId || '') +
                           '&flat=0';

            fetch(queryUrl)
                .then(function(res) {
                    if (!res.ok) {
                        return res.json().then(function(errJson) {
                            throw new Error(errJson.error || errJson.message || ('HTTP ' + res.status));
                        }).catch(function(e) {
                            throw new Error(e.message || ('HTTP ' + res.status));
                        });
                    }
                    return res.json();
                })
                .then(function(data) {
                    var files = data.files || [];
                    if (files.length === 0) {
                        treeBox.innerHTML = '<div style="font-size:12px;color:var(--text-muted);padding:8px;text-align:center;">此目录下未发现媒体文件或子目录</div>';
                        return;
                    }

                    var html = '';
                    html += '<div class="file-tree-breadcrumb">';
                    html += '<span style="cursor:pointer;text-decoration:underline;" onclick="toggleExpandPanFiles(' + panIdx + ', \'' + fullUrl + '\', \'' + pwd + '\', \'' + panName + '\', \'\')">根目录</span>';
                    if (folderName) {
                        html += '<span>&gt;</span><span style="color:#fff;font-weight:600;">' + folderName + '</span>';
                    }
                    html += '</div>';

                    for (var i = 0; i < files.length; i++) {
                        var f = files[i];
                        var fName = f.file_name || '未命名文件';
                        var fId = f.file_id || '';
                        var fSize = f.size_label || '';

                        var ext = (fName.indexOf('.') !== -1 ? fName.split('.').pop().toLowerCase() : '');
                        var isSub = ['srt', 'ass', 'ssa', 'vtt', 'sub'].indexOf(ext) !== -1;

                        var pureFid = fId;
                        if (pureFid && pureFid.indexOf('eyJ') !== -1) {
                            try {
                                var dec = JSON.parse(atob(pureFid));
                                if (dec && (dec.fid || dec.file_id || dec.target_id)) {
                                    pureFid = dec.fid || dec.file_id || dec.target_id;
                                }
                            } catch(e) {}
                        }
                        var pureCid = targetFolderId;
                        if (!pureCid && fullUrl) {
                            var mCid = fullUrl.match(/[#?&/](?:cid|folder_id|parent_id)=([a-zA-Z0-9_-]+)/i);
                            if (mCid) {
                                pureCid = mCid[1];
                            } else {
                                var mPath = fullUrl.match(/[#&]*\/share\/([^?\s#]+)/i);
                                if (mPath) {
                                    var segs = mPath[1].split('/').filter(Boolean);
                                    if (segs.length > 0) {
                                        pureCid = segs[segs.length - 1];
                                    }
                                }
                            }
                        }
                        if (pureCid && pureCid.indexOf('eyJ') !== -1) {
                            try {
                                var decC = JSON.parse(atob(pureCid));
                                if (decC && (decC.cid || decC.folder_id || decC.parent_id)) {
                                    pureCid = decC.cid || decC.folder_id || decC.parent_id;
                                }
                            } catch(e) {}
                        }

                        if (f.is_folder) {
                            html += '<div class="file-tree-item" style="cursor:pointer;" onclick="toggleExpandPanFiles(' + panIdx + ', \'' + fullUrl + '\', \'' + pwd + '\', \'' + panName + '\', \'' + pureFid + '\', \'' + fName.replace(/'/g, "\\'") + '\')">';
                            html += '<div style="display:flex;align-items:center;gap:6px;"><span style="font-size:15px;">📁</span><span style="font-weight:600;color:#fff;">' + fName + '</span></div>';
                            html += '<span style="font-size:12px;color:var(--text-muted);">&gt; 进入目录</span></div>';
                        } else if (isSub) {
                            html += '<div class="file-tree-item" style="background:rgba(99,102,241,0.06);border-left:2px solid #818cf8;">';
                            html += '<div style="display:flex;align-items:center;gap:8px;flex:1;min-width:0;">';
                            html += '<input type="checkbox" class="file-sub-chk" data-pan-idx="' + panIdx + '" data-fid="' + pureFid + '" data-name="' + fName.replace(/"/g, '&quot;') + '">';
                            html += '<span style="font-size:15px;">💬</span>';
                            html += '<span style="color:#c7d2fe;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="' + fName + '"><b style="color:#818cf8;">[外挂字幕]</b> ' + fName + '</span>';
                            html += '</div>';
                            html += '<div style="font-size:11px;color:var(--text-muted);flex-shrink:0;">' + fSize + '</div>';
                            html += '</div>';
                        } else {
                            var parentChk = document.querySelector('#pan_card_' + panIdx + ' .source-item-chk');
                            var parentSeason = (parentChk && parentChk.dataset.seasonNumber) ? parentChk.dataset.seasonNumber : 1;
                            html += '<div class="file-tree-item">';
                            html += '<div style="display:flex;align-items:center;gap:8px;flex:1;min-width:0;">';
                            html += '<input type="checkbox" class="file-item-chk" data-pan-idx="' + panIdx + '" data-season-number="' + parentSeason + '" data-provider="' + panName + '" data-full-url="' + fullUrl + '" data-pwd="' + (pwd || '') + '" data-cid="' + (pureCid || '') + '" data-fid="' + pureFid + '" data-fname="' + fName.replace(/"/g, '&quot;') + '" data-size="' + (f.size || 0) + '" data-sha="' + (f.sha || '') + '">';
                            html += '<span style="font-size:15px;">🎬</span>';
                            html += '<span style="color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="' + fName + '">' + fName + '</span>';
                            html += '</div>';
                            html += '<div style="font-size:11px;color:var(--text-muted);flex-shrink:0;">' + fSize + '</div>';
                            html += '</div>';
                        }
                    }
                    treeBox.innerHTML = html;
                })
                .catch(function(err) {
                    var errMsg = err.message || '网络异常';
                    if (errMsg.indexOf('登录') !== -1 || errMsg.indexOf('token') !== -1) {
                        errMsg = '需要登录：请先在底部【网盘】导航页扫码登录 ' + (PROVIDER_NAMES[panName] || panName);
                    }
                    treeBox.innerHTML = '<div style="font-size:12px;color:#fca5a5;padding:10px;text-align:center;line-height:1.4;">❌ 解析失败: ' + errMsg + '</div>';
                });
        }

        function confirmAddDetailVideo() {
            if (!state.currentDetailVideo || !state.currentLib) return;
            var v = state.currentDetailVideo;
            var cleaned = cleanSeasonFromTitle(v.title);
            var finalTitle = cleaned.title || v.title;
            var isMultiSeason = v.seasonList && v.seasonList.length > 1;
            var finalTypeId = (cleaned.season >= 0 || isMultiSeason) ? 2 : (v.typeId || 1);

            var links = extractLinksFromCheckedInputs();
            for (var li = 0; li < links.length; li++) {
                if (links[li].season_number === undefined || links[li].season_number === null || (links[li].season_number <= 0 && links[li].episode_number <= 0)) {
                    links[li].season_number = (cleaned.season >= 0) ? cleaned.season : 1;
                }
            }

            fetch('/api/private/libraries/' + state.currentLib.id + '/movies', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    vod_id: String(v.id),
                    tmdb_id: v.tmdbId || 0,
                    type_id: finalTypeId,
                    title: finalTitle,
                    year: String(v.year || ''),
                    cover_url: v.pic || '',
                    backdrop_url: formatBackdropUrl(v.backdropPath || v.backdrop_path || ''),
                    summary: v.content || '',
                    genres: Array.isArray(v.tags) ? v.tags.join(',') : '',
                    directors: v.director || '',
                    actors: v.starring || '',
                    area: v.area || '',
                    links: links
                })
            })
            .then(function(res) { return res.json(); })
            .then(function() {
                showToast('已成功添加入库！(包含 ' + links.length + ' 个播放源)');
                closeModal('videoDetailModal');
                closeModal('searchAddModal');
                loadMovies();
            })
            .catch(function(err) {
                showToast('添加失败: ' + err.message);
            });
        }

        // ================== 复制影片到自建媒体库 ==================
        state.copyingMovieIds = [];

        function openCopyMovieModal(movieIds, movieTitle) {
            var ids = [];
            if (Array.isArray(movieIds)) {
                ids = movieIds;
            } else if (movieIds) {
                ids = [movieIds];
            }
            if (ids.length === 0) {
                showToast('未选择需要复制的影片');
                return;
            }
            state.copyingMovieIds = ids;

            var infoEl = document.getElementById('copyModalMovieInfo');
            if (infoEl) {
                if (ids.length === 1) {
                    infoEl.innerHTML = '即将复制影片：<strong style="color: #fff;">' + escapeHtml(movieTitle || '选中的影片') + '</strong>';
                } else {
                    infoEl.innerHTML = '即将批量复制：<strong style="color: #a5b4fc;">' + ids.length + '</strong> 部选中的影片';
                }
            }

            var sel = document.getElementById('copyTargetLibSelect');
            if (sel) {
                sel.innerHTML = '';
                var writableLibs = [];
                if (state.libraries) {
                    for (var i = 0; i < state.libraries.length; i++) {
                        var l = state.libraries[i];
                        // 过滤掉全局聚合库和持续更新只读订阅库 (share_type === 2)
                        if (l.id !== 'all' && l.share_type !== 2) {
                            writableLibs.push(l);
                        }
                    }
                }

                if (writableLibs.length === 0) {
                    sel.innerHTML = '<option value="" disabled selected>暂无可用自建媒体库 (请先在首页创建自建库)</option>';
                } else {
                    var hasSelected = false;
                    for (var j = 0; j < writableLibs.length; j++) {
                        var opt = document.createElement('option');
                        opt.value = writableLibs[j].id;
                        var tag = writableLibs[j].share_type === 1 ? ' [快照]' : ' [自建]';
                        opt.text = writableLibs[j].name + tag + ' (' + (writableLibs[j].item_count || 0) + '部)';
                        // 默认选中非当前库的第一个自建库
                        if (!hasSelected && (!state.currentLib || writableLibs[j].id !== state.currentLib.id)) {
                            opt.selected = true;
                            hasSelected = true;
                        }
                        sel.appendChild(opt);
                    }
                }
            }

            var cb = document.getElementById('copyIncludeLinksCb');
            if (cb) cb.checked = true;

            openModal('copyMovieModal');
        }

        function submitCopyMovie() {
            if (!state.copyingMovieIds || state.copyingMovieIds.length === 0) {
                showToast('未选择需要复制的影片');
                return;
            }

            var sel = document.getElementById('copyTargetLibSelect');
            var targetLibId = sel ? sel.value : '';
            if (!targetLibId) {
                showToast('请选择目标自建媒体库');
                return;
            }

            var cb = document.getElementById('copyIncludeLinksCb');
            var copyLinks = cb ? cb.checked : true;

            var btn = document.getElementById('btnSubmitCopyMovie');
            if (btn) {
                btn.disabled = true;
                btn.innerText = '正在复制...';
            }

            fetch('/api/private/movies/copy', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    movie_ids: state.copyingMovieIds,
                    target_library_id: targetLibId,
                    copy_links: copyLinks
                })
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (btn) {
                    btn.disabled = false;
                    btn.innerText = '确认复制';
                }
                if (data && data.success) {
                    showToast(data.message || '复制成功！');
                    closeModal('copyMovieModal');
                    if (state.selectedMovieIds && state.selectedMovieIds.length > 0) {
                        clearMovieSelection();
                    }
                    if (typeof loadLibraries === 'function') {
                        loadLibraries();
                    }
                } else {
                    showToast('复制失败: ' + ((data && data.message) || '未知错误'));
                }
            })
            .catch(function(err) {
                if (btn) {
                    btn.disabled = false;
                    btn.innerText = '确认复制';
                }
                showToast('请求异常: ' + err.message);
            });
        }

        function batchCopySelectedMovies() {
            if (!state.selectedMovieIds || state.selectedMovieIds.length === 0) {
                showToast('请先勾选需要复制的影片');
                return;
            }
            openCopyMovieModal(state.selectedMovieIds, '');
        }

        // ==================== 🎯 影视重新识别与换绑 ====================
        var rebindState = {
            movieId: '',
            movie: null,
            links: [],
            candidates: [],
            selectedCandidate: null
        };

        function guessSeasonAndEpisode(text, defaultSeason, fallbackEpisode) {
            var season = (defaultSeason !== undefined && defaultSeason !== null) ? defaultSeason : 1;
            var episode = (fallbackEpisode !== undefined && fallbackEpisode !== null) ? fallbackEpisode : 1;
            if (!text) return { season: season, episode: episode };

            // 1. 优先匹配标准 S01E05 / S1E5 / s02e12
            var seMatch = text.match(/[Ss](\d{1,2})\s*[Ee](\d{1,4})/);
            if (seMatch) {
                return {
                    season: parseInt(seMatch[1], 10),
                    episode: parseInt(seMatch[2], 10)
                };
            }

            // 2. 匹配 "第1季第2集" / "第 1 季 第 02 集" / "第1部第2集"
            var cnMatch = text.match(/第\s*(\d{1,2})\s*[季部卷]\s*第\s*(\d{1,4})\s*[集话回期]/);
            if (cnMatch) {
                return {
                    season: parseInt(cnMatch[1], 10),
                    episode: parseInt(cnMatch[2], 10)
                };
            }

            // 3. 匹配单独季数 "第2季" / "Season 2"
            var sOnlyMatch = text.match(/第\s*(\d{1,2})\s*[季部卷]/) || text.match(/[Ss]eason\s*(\d{1,2})/i);
            if (sOnlyMatch) {
                season = parseInt(sOnlyMatch[1], 10);
            }

            // 4. 匹配单独集数 "第12集" / "第12话" / "EP12" / "E12"
            var epMatch = text.match(/第\s*(\d{1,4})\s*[集话回期]/) || text.match(/(?:EP|ep|E|e)\s*(\d{1,4})(?!\d)/);
            if (epMatch) {
                episode = parseInt(epMatch[1], 10);
                return { season: season, episode: episode };
            }

            // 5. 匹配纯数字集数（如 " - 08.mkv", ".08.mp4", "[08]"）
            var numMatch = text.match(/[\s._\-[(](\d{2,3})[\s._\-)\]]/);
            if (numMatch) {
                var n = parseInt(numMatch[1], 10);
                if (n > 0 && n < 1000) {
                    return { season: season, episode: n };
                }
            }

            return { season: season, episode: episode };
        }

        function openRebindMovieModal(movieId) {
            movieId = movieId || (state.currentMovie ? state.currentMovie.id : '');
            if (!movieId) {
                showToast('请先选择需要重新识别的影片');
                return;
            }

            var movie = null;
            if (state.currentMovie && state.currentMovie.id === movieId) {
                movie = state.currentMovie;
            } else if (state.movies && state.movies.length > 0) {
                for (var i = 0; i < state.movies.length; i++) {
                    if (state.movies[i].id === movieId) {
                        movie = state.movies[i];
                        break;
                    }
                }
            }

            if (!movie) {
                showToast('未找到对应影片信息');
                return;
            }

            if (isMovieReadOnly(movie)) {
                showToast('该媒体库为持续更新订阅库 (只读)，不可重新识别');
                return;
            }

            rebindState.movieId = movieId;
            rebindState.movie = movie;
            rebindState.links = (movie.links && movie.links.length > 0) ? movie.links.slice() : ((state.currentMovie && state.currentMovie.id === movieId && state.links) ? state.links.slice() : []);
            rebindState.candidates = [];
            rebindState.selectedCandidate = null;

            var hintEl = document.getElementById('rebindModalCurrentHint');
            if (hintEl) {
                hintEl.innerText = '（当前识别：' + (movie.title || '未知') + (movie.year ? ' ' + movie.year : '') + '）';
            }

            var titleInp = document.getElementById('rebindTitleInput');
            if (titleInp) titleInp.value = movie.title || '';

            var yearInp = document.getElementById('rebindYearInput');
            if (yearInp) yearInp.value = movie.year || '';

            var typeFilter = document.getElementById('rebindTypeFilter');
            if (typeFilter) {
                var tid = parseInt(movie.type_id, 10) || 0;
                typeFilter.value = (tid >= 1 && tid <= 4) ? String(tid) : '0';
            }

            var candBox = document.getElementById('rebindCandidatesContainer');
            if (candBox) {
                candBox.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;gap:10px;padding:36px 0;font-size:13px;color:#38bdf8;"><div class="loading-spinner" style="width:18px;height:18px;border-width:2px;"></div> 正在 TMDB 检索【' + escapeHtml(movie.title || '') + '】...</div>';
            }

            var epTbody = document.getElementById('rebindEpisodesTbody');
            if (epTbody) epTbody.innerHTML = '';

            var footerHint = document.getElementById('rebindFooterHint');
            if (footerHint) footerHint.innerText = '💡 点击任意候选卡片即可直接换绑入库；若为电视剧将弹窗确认季集';

            openModal('rebindMovieModal');

            fetch('/api/private/movies/' + movieId + '/links')
                .then(function(res) { return res.json(); })
                .then(function(d) {
                    if (d && Array.isArray(d.data)) {
                        rebindState.links = d.data;
                    }
                })
                .catch(function(err) {
                    console.warn('[Rebind] 拉取 links 失败:', err);
                });

            executeRebindSearch();
        }

        function executeRebindSearch() {
            var titleInp = document.getElementById('rebindTitleInput');
            var kw = titleInp ? titleInp.value.trim() : '';
            if (!kw) {
                showToast('请输入正确的片名或 TMDB ID');
                return;
            }

            var yearInp = document.getElementById('rebindYearInput');
            var yr = yearInp ? yearInp.value.trim() : '';

            var typeSel = document.getElementById('rebindTypeFilter');
            var typeFilterVal = typeSel ? parseInt(typeSel.value, 10) || 0 : 0;

            var btnSearch = document.getElementById('btnRebindSearch');
            if (btnSearch) {
                btnSearch.disabled = true;
                btnSearch.innerText = '正在检索...';
            }

            var statsEl = document.getElementById('rebindSearchStats');
            if (statsEl) statsEl.innerText = '';

            var candBox = document.getElementById('rebindCandidatesContainer');
            if (candBox) {
                candBox.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;gap:10px;padding:36px 0;font-size:13px;color:#38bdf8;"><div class="loading-spinner" style="width:18px;height:18px;border-width:2px;"></div> 正在 TMDB 检索【' + escapeHtml(kw) + (yr ? ' (' + yr + ')' : '') + '】...</div>';
            }

            rebindState.selectedCandidate = null;

            fetchTmdbSearch(kw, yr)
                .then(function(results) {
                    if (btnSearch) {
                        btnSearch.disabled = false;
                        btnSearch.innerText = '🔍 检索 TMDB';
                    }
                    if (!results || results.length === 0) {
                        if (candBox) {
                            candBox.innerHTML = '<div style="text-align:center;padding:36px 0;color:#94a3b8;font-size:13px;">未在 TMDB 检索到相关影视条目，建议修改片名或年份重新检索</div>';
                        }
                        if (statsEl) statsEl.innerText = '未检索到候选条目';
                        return;
                    }

                    var formattedList = [];
                    for (var i = 0; i < results.length; i++) {
                        var r = results[i];
                        var rTitle = r.title || r.name || r.original_title || '';
                        var rOrig = r.original_title || r.original_name || '';
                        var rYear = r.release_date ? r.release_date.split('-')[0] : (r.first_air_date ? r.first_air_date.split('-')[0] : '');
                        var rPic = r.poster_path ? (r.poster_path.indexOf('http') === 0 ? r.poster_path : ('https://image.tmdb.org/t/p/w500' + r.poster_path)) : (r.pic || '');
                        var rBackdrop = r.backdrop_path ? (r.backdrop_path.indexOf('http') === 0 ? r.backdrop_path : ('https://image.tmdb.org/t/p/original' + r.backdrop_path)) : (r.backdropPath || '');
                        var isTV = (r.media_type === 'tv' || r.typeId === 2);
                        var rating = r.vote_average ? parseFloat(r.vote_average).toFixed(1) : (r.rating ? parseFloat(r.rating).toFixed(1) : '');

                        var typeId = isTV ? 2 : 1;
                        if (r.typeId && r.typeId > 0) typeId = r.typeId;

                        formattedList.push({
                            id: r.id || r.tmdbId,
                            tmdbId: r.id || r.tmdbId,
                            title: rTitle,
                            originalTitle: rOrig,
                            year: rYear,
                            media_type: isTV ? 'tv' : 'movie',
                            typeId: typeId,
                            pic: rPic,
                            backdropPath: rBackdrop,
                            overview: r.overview || r.content || '',
                            rating: rating ? parseFloat(rating) : 0,
                            ratingText: rating
                        });
                    }

                    if (typeFilterVal === 1) {
                        formattedList.sort(function(a, b) {
                            if (a.typeId === 1 && b.typeId !== 1) return -1;
                            if (a.typeId !== 1 && b.typeId === 1) return 1;
                            return 0;
                        });
                    } else if (typeFilterVal === 2) {
                        formattedList.sort(function(a, b) {
                            if (a.typeId === 2 && b.typeId !== 2) return -1;
                            if (a.typeId !== 2 && b.typeId === 2) return 1;
                            return 0;
                        });
                    }

                    rebindState.candidates = formattedList;
                    if (statsEl) statsEl.innerText = '找到 ' + formattedList.length + ' 个候选';

                    var html = '<div style="display: flex; flex-direction: column; gap: 8px;">';
                    for (var c = 0; c < formattedList.length; c++) {
                        var it = formattedList[c];
                        var isTvItem = (it.typeId === 2 || it.media_type === 'tv');
                        var tBadge = isTvItem
                            ? '<span style="font-size: 11px; padding: 1px 6px; border-radius: 4px; background: rgba(56, 189, 248, 0.2); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.4); font-weight: 600;">电视剧</span>'
                            : '<span style="font-size: 11px; padding: 1px 6px; border-radius: 4px; background: rgba(99, 102, 241, 0.2); color: #818cf8; border: 1px solid rgba(99, 102, 241, 0.4); font-weight: 600;">电影</span>';

                        var posterHtml = it.pic
                            ? '<img referrerpolicy="no-referrer" src="' + it.pic + '" style="width: 46px; height: 66px; object-fit: cover; border-radius: 6px; flex-shrink: 0; background: #1e293b;">'
                            : '<div style="width: 46px; height: 66px; background: #1e293b; border-radius: 6px; flex-shrink: 0; display: flex; align-items: center; justify-content: center; font-size: 20px;">🎬</div>';

                        var rateText = it.ratingText ? (' · <span style="color: #fbbf24; font-weight: 600;">★ ' + it.ratingText + '</span>') : '';
                        var origNameText = (it.originalTitle && it.originalTitle !== it.title) ? (' · ' + escapeHtml(it.originalTitle)) : '';
                        var actionTip = isTvItem
                            ? '<span style="color: #38bdf8; font-weight: 600; font-size: 11px;">点击弹窗确认分集并绑定 📺</span>'
                            : '<span style="color: #38bdf8; font-weight: 600; font-size: 11px;">点击卡片立即绑定电影 ✓</span>';

                        html += '<div class="rebind-cand-card" style="display: flex; gap: 12px; padding: 10px 14px; background: rgba(30, 41, 59, 0.65); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 8px; cursor: pointer; align-items: center; position: relative; transition: all 0.2s ease;" onmouseover="this.style.borderColor=\'#38bdf8\'; this.style.background=\'rgba(56, 189, 248, 0.12)\'; this.style.boxShadow=\'0 0 12px rgba(56, 189, 248, 0.25)\';" onmouseout="this.style.borderColor=\'rgba(255, 255, 255, 0.1)\'; this.style.background=\'rgba(30, 41, 59, 0.65)\'; this.style.boxShadow=\'none\';" onclick="onRebindCandidateClicked(' + c + ')">';
                        html += '<button type="button" title="查看 TMDB 详细信息" onclick="event.stopPropagation(); handlePreviewRebindCandidate(' + c + ')" style="position: absolute; top: 10px; right: 12px; background: rgba(15,23,42,0.85); border: 1px solid rgba(255,255,255,0.2); color: #38bdf8; font-size: 11px; padding: 2px 8px; border-radius: 4px; cursor: pointer; display: inline-flex; align-items: center; gap: 4px; z-index: 3; line-height: 1.2;" onmouseover="this.style.borderColor=\'#38bdf8\';this.style.color=\'#fff\'" onmouseout="this.style.borderColor=\'rgba(255,255,255,0.2)\';this.style.color=\'#38bdf8\'">🔍 详情 ↗</button>';
                        html += posterHtml;
                        html += '<div style="flex: 1; min-width: 0; padding-right: 70px;">';
                        html += '  <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">';
                        html += '    <span style="font-size: 14px; font-weight: 700; color: #fff;">' + escapeHtml(it.title) + '</span>';
                        html += tBadge;
                        html += '    <span style="font-size: 11px; color: var(--text-muted);">TMDB: ' + it.tmdbId + '</span>';
                        html += '  </div>';
                        html += '  <div style="font-size: 12px; color: #94a3b8; margin-top: 3px;">' + (it.year ? it.year + ' 年' : '年份未知') + origNameText + rateText + '</div>';
                        if (it.overview) {
                            html += '  <div style="font-size: 11px; color: var(--text-muted); margin-top: 4px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; line-height: 1.4;">' + escapeHtml(it.overview) + '</div>';
                        }
                        html += '  <div style="margin-top: 5px;">' + actionTip + '</div>';
                        html += '</div>';
                        html += '<div style="font-size: 18px; color: #38bdf8; font-weight: 700; flex-shrink: 0; padding-right: 4px;">➔</div>';
                        html += '</div>';
                    }
                    html += '</div>';
                    candBox.innerHTML = html;
                })
                .catch(function(err) {
                    if (btnSearch) {
                        btnSearch.disabled = false;
                        btnSearch.innerText = '🔍 检索 TMDB';
                    }
                    if (candBox) {
                        candBox.innerHTML = '<div style="text-align:center;padding:36px 0;color:#f87171;font-size:13px;">检索失败: ' + escapeHtml(err.message || '网络异常') + '</div>';
                    }
                });
        }

        function handlePreviewRebindCandidate(idx) {
            if (!rebindState.candidates || !rebindState.candidates[idx]) return;
            var cand = rebindState.candidates[idx];
            var isTv = (cand.typeId === 2 || cand.media_type === 'tv');
            var vData = {
                tmdbId: cand.tmdbId || cand.id || 0,
                title: cand.title,
                originalTitle: cand.originalTitle || '',
                year: cand.year || '',
                pic: cand.pic || '',
                backdropPath: cand.backdropPath || '',
                typeId: isTv ? 2 : (cand.typeId || 1),
                content: cand.overview || '',
                remark: cand.ratingText ? ('评分 ' + cand.ratingText) : ''
            };
            openTmdbPreviewModal(-1, vData, true, function() {
                onRebindCandidateClicked(idx);
            });
        }

        function onRebindCandidateClicked(idx) {
            if (!rebindState.candidates || !rebindState.candidates[idx]) return;
            var cand = rebindState.candidates[idx];
            rebindState.selectedCandidate = cand;

            var isTV = (cand.typeId === 2 || cand.media_type === 'tv');
            if (isTV) {
                var modalTitle = document.getElementById('rebindEpisodeModalTitle');
                if (modalTitle) {
                    modalTitle.innerText = '确认剧集分集与季数 - 《' + cand.title + '》';
                }
                renderRebindEpisodes(rebindState.links);
                openModal('rebindEpisodeModal');
            } else {
                executeRebindSubmit(cand, []);
            }
        }

        function renderRebindEpisodes(links) {
            var tbody = document.getElementById('rebindEpisodesTbody');
            if (!tbody) return;

            links = links || [];
            if (links.length === 0) {
                tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; padding: 24px; color: var(--text-muted);">当前影片暂无播放源链接</td></tr>';
                return;
            }

            var html = '';
            for (var i = 0; i < links.length; i++) {
                var l = links[i];
                var provName = getProviderDisplayName(l.provider, l.link_type, l.url);
                var displaySrc = l.remark || l.url || ('源文件 ' + (i + 1));

                var origS = (l.season_number !== undefined && l.season_number !== null && l.season_number >= 0) ? l.season_number : 1;
                var origE = (l.episode_number && l.episode_number > 0) ? l.episode_number : (i + 1);

                var guessed = guessSeasonAndEpisode(l.remark || l.url, origS, origE);
                var finalS = guessed.season;
                var finalE = guessed.episode;

                html += '<tr style="border-bottom: 1px solid rgba(255,255,255,0.06);">';
                html += '  <td style="padding: 8px 10px; max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">';
                html += '    <span style="display: inline-block; font-size: 10px; padding: 1px 5px; border-radius: 3px; background: rgba(99,102,241,0.2); color: #a5b4fc; margin-right: 6px; font-weight: 600;">' + provName + '</span>';
                html += '    <span style="color: #cbd5e1;" title="' + escapeHtml(displaySrc) + '">' + escapeHtml(displaySrc) + '</span>';
                html += '  </td>';
                html += '  <td style="padding: 8px 10px; text-align: center;">';
                html += '    <div style="display: flex; align-items: center; justify-content: center; gap: 4px;">';
                html += '      <span style="color: #94a3b8; font-size: 11px;">第</span>';
                html += '      <input type="number" min="0" max="99" class="form-input rebind-season-input" data-link-id="' + l.id + '" value="' + finalS + '" style="width: 52px; text-align: center; padding: 4px 6px; font-size: 12px;">';
                html += '      <span style="color: #94a3b8; font-size: 11px;">季</span>';
                html += '    </div>';
                html += '  </td>';
                html += '  <td style="padding: 8px 10px; text-align: center;">';
                html += '    <div style="display: flex; align-items: center; justify-content: center; gap: 4px;">';
                html += '      <span style="color: #94a3b8; font-size: 11px;">第</span>';
                html += '      <input type="number" min="1" max="9999" class="form-input rebind-ep-input" data-link-id="' + l.id + '" value="' + finalE + '" style="width: 56px; text-align: center; padding: 4px 6px; font-size: 12px;">';
                html += '      <span style="color: #94a3b8; font-size: 11px;">集</span>';
                html += '    </div>';
                html += '  </td>';
                html += '  <td style="padding: 8px 10px;">';
                html += '    <input type="text" class="form-input rebind-eptitle-input" data-link-id="' + l.id + '" value="' + escapeHtml(l.episode_title || '') + '" placeholder="可选单集标题" style="width: 100%; padding: 4px 8px; font-size: 12px;">';
                html += '  </td>';
                html += '</tr>';
            }
            tbody.innerHTML = html;
        }

        function quickBatchFillEpisodes(season, startEp) {
            season = parseInt(season, 10);
            if (isNaN(season) || season < 0) season = 1;
            startEp = parseInt(startEp, 10);
            if (isNaN(startEp) || startEp <= 0) startEp = 1;

            var sInputs = document.querySelectorAll('.rebind-season-input');
            var eInputs = document.querySelectorAll('.rebind-ep-input');

            for (var i = 0; i < sInputs.length; i++) {
                sInputs[i].value = String(season);
                if (eInputs[i]) {
                    eInputs[i].value = String(startEp + i);
                }
            }

            showToast('已批量填充为第 ' + season + ' 季，从第 ' + startEp + ' 集递增');
        }

        function submitRebindMovieWithEpisodes() {
            if (!rebindState.selectedCandidate) {
                showToast('未选定电视剧条目');
                return;
            }

            var cand = rebindState.selectedCandidate;
            var episodeMappings = [];

            var sInputs = document.querySelectorAll('.rebind-season-input');
            var eInputs = document.querySelectorAll('.rebind-ep-input');
            var tInputs = document.querySelectorAll('.rebind-eptitle-input');

            for (var i = 0; i < sInputs.length; i++) {
                var linkId = sInputs[i].getAttribute('data-link-id');
                var sNum = parseInt(sInputs[i].value, 10);
                if (isNaN(sNum) || sNum < 0) sNum = 1;
                var eNum = parseInt(eInputs[i].value, 10);
                if (isNaN(eNum) || eNum <= 0) eNum = 1;
                var epTitle = tInputs[i] ? tInputs[i].value.trim() : '';

                episodeMappings.push({
                    link_id: linkId,
                    season_number: sNum,
                    episode_number: eNum,
                    episode_title: epTitle
                });
            }

            var btnSubmit = document.getElementById('btnSubmitRebindEpisode');
            executeRebindSubmit(cand, episodeMappings, btnSubmit);
        }

        function executeRebindSubmit(cand, episodeMappings, btnTrigger) {
            if (!cand || !rebindState.movieId) {
                showToast('未选择影片或绑定参数缺失');
                return;
            }

            var isTV = (cand.typeId === 2 || cand.media_type === 'tv');

            if (btnTrigger) {
                btnTrigger.disabled = true;
                btnTrigger.innerText = '正在提交...';
            }

            showToast('正在重新识别并绑定为【' + cand.title + '】...', 4000);

            var payload = {
                tmdb_id: cand.tmdbId || cand.id || 0,
                title: cand.title,
                original_title: cand.originalTitle || '',
                year: cand.year || '',
                type_id: isTV ? 2 : (cand.typeId || 1),
                cover_url: cand.pic || '',
                backdrop_url: cand.backdropPath || '',
                summary: cand.overview || '',
                rating: cand.rating || 0,
                episode_mappings: episodeMappings || []
            };

            fetch('/api/private/movies/' + rebindState.movieId + '/rebind', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (btnTrigger) {
                    btnTrigger.disabled = false;
                    btnTrigger.innerText = '✓ 确认绑定入库';
                }

                if (data && data.success) {
                    showToast(data.message || '影视重新识别并换绑成功！');
                    closeModal('rebindEpisodeModal');
                    closeModal('rebindMovieModal');

                    var finalMovie = data.data;

                    if (state.currentLevel === 3 && state.currentMovie) {
                        if (data.merged && finalMovie && finalMovie.id) {
                            state.currentMovie = finalMovie;
                            enterMovie(finalMovie.id);
                        } else if (finalMovie && finalMovie.id) {
                            state.currentMovie = finalMovie;
                            document.getElementById('pageMainTitle').innerText = finalMovie.title;
                            document.getElementById('currentMovieTitle').innerText = finalMovie.title;
                            document.getElementById('currentMoviePoster').src = formatProxiedImgUrl(finalMovie.cover_url || PRESET_COVERS[0]);
                            document.getElementById('currentMovieSubMeta').innerText = (finalMovie.year || '') + (finalMovie.genres ? ' · ' + finalMovie.genres : '');
                            document.getElementById('currentMovieDesc').innerText = finalMovie.summary || '暂无剧情简介。';
                            loadLinks();
                        }
                    }

                    if (typeof loadMovies === 'function') {
                        loadMovies();
                    }

                    if (typeof loadLibraries === 'function') {
                        loadLibraries();
                    }
                } else {
                    showToast('重新识别失败: ' + ((data && data.message) || '未知错误'));
                }
            })
            .catch(function(err) {
                if (btnTrigger) {
                    btnTrigger.disabled = false;
                    btnTrigger.innerText = '✓ 确认绑定入库';
                }
                showToast('网络请求异常: ' + err.message);
            });
        }


        // ------------------ 批量智能导入 (Excel / 纯文本粘贴) ------------------

        function openExcelImportModal(defaultTab) {
            if (checkReadOnlyGuard()) return;
            resetImportSourceView();
            if (defaultTab === 'text') {
                switchImportSource('text');
            } else if (defaultTab === 'pan') {
                switchImportSource('pan');
            } else if (defaultTab === 'user_pan') {
                switchImportSource('user_pan');
            } else {
                switchImportSource('excel');
            }
            openModal('excelModal');
        }

        var ALL_SUPPORTED_USER_PANS = [
            { key: 'CLOUD115', name: '115网盘', icon: '📦' },
            { key: 'ALIYUN', name: '阿里云盘', icon: '☁️' },
            { key: 'QUARK', name: '夸克网盘', icon: '⚡' },
            { key: 'UC', name: 'UC网盘', icon: '🐿️' },
            { key: 'BAIDU', name: '百度网盘', icon: '🐾' },
            { key: 'XUNLEI', name: '迅雷云盘', icon: '⚡' },
            { key: 'CLOUD123', name: '123云盘', icon: '📁' },
            { key: 'CHINA_MOBILE', name: '移动云盘', icon: '📱' },
            { key: 'CHINA_TELECOM', name: '天翼云盘', icon: '🕊️' },
            { key: 'GUANGYA', name: '光鸭云盘', icon: '🦆' }
        ];

        function switchImportSource(type) {
            var tabExcel = document.getElementById('tabSourceExcel');
            var tabText = document.getElementById('tabSourceText');
            var tabPan = document.getElementById('tabSourcePan');
            var tabUserPan = document.getElementById('tabSourceUserPan');
            var panelExcel = document.getElementById('sourceExcelPanel');
            var panelText = document.getElementById('sourceTextPanel');
            var panelPan = document.getElementById('sourcePanPanel');
            var panelUserPan = document.getElementById('sourceUserPanPanel');

            if (tabExcel) tabExcel.classList.remove('active');
            if (tabText) tabText.classList.remove('active');
            if (tabPan) tabPan.classList.remove('active');
            if (tabUserPan) tabUserPan.classList.remove('active');
            if (panelExcel) panelExcel.style.display = 'none';
            if (panelText) panelText.style.display = 'none';
            if (panelPan) panelPan.style.display = 'none';
            if (panelUserPan) panelUserPan.style.display = 'none';

            if (type === 'excel') {
                if (tabExcel) tabExcel.classList.add('active');
                if (panelExcel) panelExcel.style.display = 'block';
            } else if (type === 'pan') {
                if (tabPan) tabPan.classList.add('active');
                if (panelPan) panelPan.style.display = 'block';
            } else if (type === 'user_pan') {
                if (tabUserPan) tabUserPan.classList.add('active');
                if (panelUserPan) panelUserPan.style.display = 'block';
                loadUserPanStatus();
            } else {
                if (tabText) tabText.classList.add('active');
                if (panelText) panelText.style.display = 'block';
            }
        }

        function loadUserPanStatus() {
            var grid = document.getElementById('userPanListGrid');
            if (!grid) return;
            grid.innerHTML = '<div style="color: var(--text-muted); font-size: 12px; padding: 10px;">正在获取网盘登录状态...</div>';

            fetch('/api/pan/status')
                .then(function(res) { return res.json(); })
                .then(function(res) {
                    var html = '';
                    for (var i = 0; i < ALL_SUPPORTED_USER_PANS.length; i++) {
                        var p = ALL_SUPPORTED_USER_PANS[i];
                        var status = (res && res[p.key]) || {};
                        var isLoggedIn = Boolean(status.logged_in || status.is_logged_in);
                        var isSelected = (state.userPanSelectedProvider === p.key);

                        var cardStyle = 'border-radius: 8px; padding: 10px 12px; cursor: pointer; transition: all 0.2s ease; border: 1px solid ';
                        if (isSelected) {
                            cardStyle += '#38bdf8; background: rgba(56, 189, 248, 0.15);';
                        } else if (isLoggedIn) {
                            cardStyle += 'rgba(255,255,255,0.12); background: rgba(15,23,42,0.6);';
                        } else {
                            cardStyle += 'rgba(255,255,255,0.06); background: rgba(15,23,42,0.3); opacity: 0.85;';
                        }

                        var statusBadge = '';
                        var clickAction = '';
                        if (isLoggedIn) {
                            statusBadge = '<span style="font-size: 10px; color: #34d399; font-weight: 600;">● 已登录</span>';
                            clickAction = 'selectUserPan(\'' + p.key + '\')';
                        } else {
                            statusBadge = '<span style="font-size: 10px; color: #f59e0b; font-weight: 500;">点击扫码登录</span>';
                            clickAction = 'openPanQrLogin(\'' + p.key + '\', \'' + p.name + '\')';
                        }

                        html += '<div style="' + cardStyle + '" onclick="' + clickAction + '">';
                        html += '<div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px;">';
                        html += '<span style="font-size: 16px;">' + p.icon + '</span>';
                        html += statusBadge;
                        html += '</div>';
                        html += '<div style="font-size: 13px; font-weight: 600; color: #fff;">' + p.name + '</div>';
                        html += '</div>';
                    }
                    grid.innerHTML = html;
                })
                .catch(function(err) {
                    grid.innerHTML = '<div style="color: #f87171; font-size: 12px; padding: 10px;">获取网盘状态失败: ' + err.message + '</div>';
                });
        }

        function updateUserPanQpsUI(providerKey) {
            var tagEl = document.getElementById('userPanQpsCurrentTag');
            var selectEl = document.getElementById('userPanQpsSelect');
            var customEl = document.getElementById('userPanQpsCustomInput');
            if (!selectEl) return;

            var defaultQps = (providerKey === 'CLOUD115') ? 1.5 : 0.0;
            if (tagEl) tagEl.innerText = '正在读取...';

            fetch('/api/pan/qps?provider=' + encodeURIComponent(providerKey))
                .then(function(res) { return res.json(); })
                .then(function(res) {
                    var qps = defaultQps;
                    if (res && res.success && res.qps && typeof res.qps[providerKey] === 'number') {
                        qps = res.qps[providerKey];
                    }
                    state.currentUserPanQps = qps;
                    if (tagEl) tagEl.innerText = (qps <= 0) ? '当前: 全速' : ('当前: ' + qps + 's');

                    var found = false;
                    for (var i = 0; i < selectEl.options.length; i++) {
                        var optVal = selectEl.options[i].value;
                        if (optVal !== 'custom' && Math.abs(parseFloat(optVal) - qps) < 0.01) {
                            selectEl.selectedIndex = i;
                            found = true;
                            break;
                        }
                    }
                    if (!found) {
                        selectEl.value = 'custom';
                        if (customEl) {
                            customEl.style.display = 'inline-block';
                            customEl.value = qps;
                        }
                    } else {
                        if (customEl) {
                            customEl.style.display = 'none';
                            customEl.value = qps;
                        }
                    }
                })
                .catch(function() {
                    state.currentUserPanQps = defaultQps;
                    if (tagEl) tagEl.innerText = (defaultQps <= 0) ? '当前: 全速' : ('当前: ' + defaultQps + 's');
                });
        }

        function onUserPanQpsSelectChange() {
            var selectEl = document.getElementById('userPanQpsSelect');
            var customEl = document.getElementById('userPanQpsCustomInput');
            var tagEl = document.getElementById('userPanQpsCurrentTag');
            if (!selectEl) return;

            var val = selectEl.value;
            if (val === 'custom') {
                if (customEl) {
                    customEl.style.display = 'inline-block';
                    customEl.focus();
                }
                return;
            }

            if (customEl) {
                customEl.style.display = 'none';
            }

            var qpsNum = parseFloat(val);
            if (isNaN(qpsNum) || qpsNum < 0) qpsNum = 0;
            state.currentUserPanQps = qpsNum;
            if (tagEl) tagEl.innerText = (qpsNum <= 0) ? '当前: 全速' : ('当前: ' + qpsNum + 's');

            if (state.userPanSelectedProvider) {
                fetch('/api/pan/qps', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        provider: state.userPanSelectedProvider,
                        qps: qpsNum
                    })
                }).then(function(r) { return r.json(); }).then(function(res) {
                    if (res && res.success) {
                        showToast('已更新 ' + state.userPanSelectedProvider + ' QPS 为 ' + (qpsNum <= 0 ? '全速' : qpsNum + 's'));
                    }
                }).catch(function() {});
            }
        }

        function onUserPanQpsCustomChange() {
            var customEl = document.getElementById('userPanQpsCustomInput');
            var tagEl = document.getElementById('userPanQpsCurrentTag');
            if (!customEl) return;

            var qpsNum = parseFloat(customEl.value);
            if (isNaN(qpsNum) || qpsNum < 0) qpsNum = 0;
            if (qpsNum > 60) qpsNum = 60;
            state.currentUserPanQps = qpsNum;
            if (tagEl) tagEl.innerText = (qpsNum <= 0) ? '当前: 全速' : ('当前: ' + qpsNum + 's');

            if (state.userPanSelectedProvider) {
                fetch('/api/pan/qps', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        provider: state.userPanSelectedProvider,
                        qps: qpsNum
                    })
                }).then(function(r) { return r.json(); }).then(function(res) {
                    if (res && res.success) {
                        showToast('已更新 ' + state.userPanSelectedProvider + ' 自定义 QPS: ' + qpsNum + 's');
                    }
                }).catch(function() {});
            }
        }

        function selectUserPan(providerKey) {
            state.userPanSelectedProvider = providerKey;
            state.userPanBreadcrumbs = [{ id: '', name: '根目录' }];
            state.userPanCurrentDir = { id: '', name: '根目录', path: '根目录' };

            loadUserPanStatus();

            var browserSec = document.getElementById('userPanDirBrowserSection');
            var submitSec = document.getElementById('userPanSubmitSection');
            if (browserSec) browserSec.style.display = 'block';
            if (submitSec) submitSec.style.display = 'block';
            updateUserPanBtnText();
            updateUserPanQpsUI(providerKey);

            loadUserPanDir(providerKey, '', '根目录');
        }

        function loadUserPanDir(providerKey, parentFileId, folderName) {
            var listEl = document.getElementById('userPanFolderList');
            var tipEl = document.getElementById('userPanCurrentSelectedTip');
            var breadEl = document.getElementById('userPanBreadcrumbs');

            if (listEl) listEl.innerHTML = '<div style="color: var(--text-muted); font-size: 12px; padding: 16px; text-align: center;">正在读取目录文件...</div>';

            // 更新当前选中信息
            var pObj = ALL_SUPPORTED_USER_PANS.find(function(x) { return x.key === providerKey; });
            var pName = pObj ? pObj.name : providerKey;
            var currentPathStr = state.userPanBreadcrumbs.map(function(b) { return b.name; }).join(' / ');
            if (tipEl) {
                tipEl.innerText = '已选：[' + pName + '] ' + currentPathStr;
            }
            state.userPanCurrentDir = {
                id: parentFileId,
                name: folderName,
                path: currentPathStr
            };

            // 渲染面包屑
            if (breadEl) {
                var bHtml = '';
                for (var bi = 0; bi < state.userPanBreadcrumbs.length; bi++) {
                    var b = state.userPanBreadcrumbs[bi];
                    var isLast = (bi === state.userPanBreadcrumbs.length - 1);
                    if (bi > 0) bHtml += '<span style="color: rgba(255,255,255,0.3);">/</span>';
                    if (isLast) {
                        bHtml += '<span style="color: #38bdf8; font-weight: 600;">' + escapeHtml(b.name) + '</span>';
                    } else {
                        bHtml += '<span style="color: #cbd5e1; cursor: pointer; text-decoration: underline;" onclick="navigateToUserPanBreadcrumb(' + bi + ')">' + escapeHtml(b.name) + '</span>';
                    }
                }
                breadEl.innerHTML = bHtml;
            }

            var url = '/api/user_files?provider=' + encodeURIComponent(providerKey) + '&parent_file_id=' + encodeURIComponent(parentFileId || '');
            fetch(url)
                .then(function(res) { return res.json(); })
                .then(function(res) {
                    if (res && res.error) {
                        listEl.innerHTML = '<div style="color: #f87171; font-size: 12px; padding: 16px; text-align: center;">读取目录失败: ' + escapeHtml(res.error) + '</div>';
                        return;
                    }
                    var files = (res && res.files) || [];
                    var folders = [];
                    var videoFiles = [];
                    for (var i = 0; i < files.length; i++) {
                        var f = files[i];
                        if (f.is_folder || f.is_dir || f.isDir || f.type === 'folder' || f.isFolder) {
                            folders.push(f);
                        } else {
                            var nameLower = (f.file_name || f.name || '').toLowerCase();
                            if (nameLower.match(/\.(mp4|mkv|avi|mov|wmv|flv|ts|m2ts|rmvb|webm|iso|bdmv)$/)) {
                                videoFiles.push(f);
                            }
                        }
                    }

                    if (folders.length === 0 && videoFiles.length === 0) {
                        listEl.innerHTML = '<div style="color: var(--text-muted); font-size: 12px; padding: 18px; text-align: center;">📂 当前目录下未包含任何文件或子文件夹</div>';
                        return;
                    }

                    var fHtml = '<div style="display: flex; flex-direction: column; gap: 4px;">';
                    for (var fi = 0; fi < folders.length; fi++) {
                        var folder = folders[fi];
                        var fId = folder.file_id || folder.id || '';
                        var fName = folder.file_name || folder.name || '未命名文件夹';
                        fHtml += '<div style="display: flex; justify-content: space-between; align-items: center; padding: 7px 10px; border-radius: 6px; background: rgba(255,255,255,0.03); cursor: pointer; transition: background 0.15s ease;" onmouseover="this.style.background=\'rgba(56, 189, 248, 0.15)\'" onmouseout="this.style.background=\'rgba(255,255,255,0.03)\'" onclick="enterUserPanSubDir(\'' + escapeHtml(fId).replace(/'/g, "\\'") + '\', \'' + escapeHtml(fName).replace(/'/g, "\\'") + '\')">';
                        fHtml += '<div style="display: flex; align-items: center; gap: 8px; font-size: 13px; color: #f1f5f9;">';
                        fHtml += '<span>📁</span><span style="font-weight: 500;">' + escapeHtml(fName) + '</span>';
                        fHtml += '</div>';
                        fHtml += '<span style="font-size: 12px; color: var(--text-muted);">进入 ❯</span>';
                        fHtml += '</div>';
                    }

                    if (videoFiles.length > 0) {
                        fHtml += '<div style="margin-top: 6px; padding: 6px 10px; background: rgba(56, 189, 248, 0.08); border: 1px dashed rgba(56, 189, 248, 0.25); border-radius: 6px; font-size: 11px; color: #94a3b8; display: flex; align-items: center; justify-content: space-between;">';
                        fHtml += '<span>🎬 当前层级包含 <b style="color: #38bdf8;">' + videoFiles.length + '</b> 个视频文件</span>';
                        fHtml += '<span style="color: #64748b;">(点击下方按钮将递归导入本层及所有子目录)</span>';
                        fHtml += '</div>';
                    }

                    if (folders.length === 0 && videoFiles.length > 0) {
                        fHtml = '<div style="color: var(--text-muted); font-size: 12px; padding: 12px 10px; text-align: center;">📂 当前目录下无更多子文件夹，已直接检测到 <b style="color: #38bdf8;">' + videoFiles.length + '</b> 个视频文件。可直接点击下方【扫描并导入此文件夹】开始导入。</div>' + fHtml;
                    }

                    fHtml += '</div>';
                    listEl.innerHTML = fHtml;
                })
                .catch(function(err) {
                    listEl.innerHTML = '<div style="color: #f87171; font-size: 12px; padding: 16px; text-align: center;">读取目录失败: ' + err.message + '</div>';
                });
        }

        function enterUserPanSubDir(folderId, folderName) {
            state.userPanBreadcrumbs.push({ id: folderId, name: folderName });
            loadUserPanDir(state.userPanSelectedProvider, folderId, folderName);
        }

        function navigateToUserPanBreadcrumb(index) {
            state.userPanBreadcrumbs = state.userPanBreadcrumbs.slice(0, index + 1);
            var target = state.userPanBreadcrumbs[state.userPanBreadcrumbs.length - 1];
            loadUserPanDir(state.userPanSelectedProvider, target.id, target.name);
        }

        function openPanQrLogin(providerKey, panName) {
            var modal = document.getElementById('panQrLoginModal');
            var titleEl = document.getElementById('panQrModalTitle');
            var loadingEl = document.getElementById('panQrLoading');
            var contentEl = document.getElementById('panQrContent');
            var imgEl = document.getElementById('panQrImage');
            var statusTextEl = document.getElementById('panQrStatusText');

            if (titleEl) titleEl.innerText = (panName || providerKey) + ' 扫码登录';
            if (loadingEl) loadingEl.style.display = 'block';
            if (contentEl) contentEl.style.display = 'none';
            if (statusTextEl) statusTextEl.innerText = '请使用对应的手机客户端扫码';

            if (modal) modal.style.display = 'flex';
            if (state.panQrTimer) {
                clearInterval(state.panQrTimer);
                state.panQrTimer = null;
            }

            fetch('/api/qrcode?provider=' + encodeURIComponent(providerKey))
                .then(function(res) { return res.json(); })
                .then(function(res) {
                    if (!res.base64) {
                        throw new Error(res.error || '未能生成二维码');
                    }
                    if (imgEl) imgEl.src = res.base64;
                    if (loadingEl) loadingEl.style.display = 'none';
                    if (contentEl) contentEl.style.display = 'block';

                    var qrKey = res.key || '';
                    state.panQrTimer = setInterval(function() {
                        fetch('/api/qrcode/status?provider=' + encodeURIComponent(providerKey) + '&key=' + encodeURIComponent(qrKey))
                            .then(function(sRes) { return sRes.json(); })
                            .then(function(sData) {
                                var st = sData.status || '';
                                if (st === 'Confirmed') {
                                    clearInterval(state.panQrTimer);
                                    state.panQrTimer = null;
                                    showToast('🎉 ' + (panName || providerKey) + ' 登录成功！');
                                    closePanQrModal();
                                    loadUserPanStatus();
                                    selectUserPan(providerKey);
                                } else if (st === 'Scanned') {
                                    if (statusTextEl) statusTextEl.innerText = '📱 已扫码，请在手机上确认登录...';
                                } else if (st === 'Expired') {
                                    clearInterval(state.panQrTimer);
                                    state.panQrTimer = null;
                                    if (statusTextEl) statusTextEl.innerText = '⌛ 二维码已过期，请重新点击登录';
                                }
                            })
                            .catch(function() {});
                    }, 1500);
                })
                .catch(function(err) {
                    if (loadingEl) loadingEl.innerHTML = '<div style="color: #f87171; font-size: 13px;">生成二维码失败: ' + err.message + '</div>';
                });
        }

        function closePanQrModal() {
            var modal = document.getElementById('panQrLoginModal');
            if (modal) modal.style.display = 'none';
            if (state.panQrTimer) {
                clearInterval(state.panQrTimer);
                state.panQrTimer = null;
            }
        }

        function startUserPanDirectoryScan() {
            if (!state.userPanSelectedProvider) {
                showToast('请先选择一个个人网盘');
                return;
            }
            if (!state.userPanCurrentDir) {
                showToast('请先选择要导入的目录');
                return;
            }

            var currentLibId = (state.currentLib ? state.currentLib.id : '');
            var minSizeEl = document.getElementById('userPanMinSizeInput');
            var depthEl = document.getElementById('userPanMaxDepthInput');
            var minSize = minSizeEl ? parseInt(minSizeEl.value, 10) : 100;
            var maxDepth = depthEl ? parseInt(depthEl.value, 10) : 10;

            var enableSyncEl = document.getElementById('userPanEnableSyncInput');
            var enableSync = enableSyncEl ? enableSyncEl.checked : true;
            if (enableSync && state.userPanSelectedProvider === 'CLOUD115') {
                var dirId = (state.userPanCurrentDir && state.userPanCurrentDir.id) ? String(state.userPanCurrentDir.id) : '0';
                var dirName = (state.userPanCurrentDir && state.userPanCurrentDir.name) ? state.userPanCurrentDir.name : '根目录';
                var dirPath = (state.userPanCurrentDir && state.userPanCurrentDir.path) ? state.userPanCurrentDir.path : '';
                state.pendingPanSyncInfo = {
                    library_id: currentLibId,
                    provider: state.userPanSelectedProvider,
                    dir_file_id: dirId,
                    dir_name: dirName,
                    dir_path: dirPath,
                    enable_sync: true
                };
            } else {
                state.pendingPanSyncInfo = null;
            }

            var qpsVal = (typeof state.currentUserPanQps === 'number') ? state.currentUserPanQps : 0;
            var qpsSel = document.getElementById('userPanQpsSelect');
            var qpsCust = document.getElementById('userPanQpsCustomInput');
            if (qpsSel) {
                if (qpsSel.value === 'custom' && qpsCust && qpsCust.value !== '') {
                    var cv = parseFloat(qpsCust.value);
                    if (!isNaN(cv) && cv >= 0) qpsVal = cv;
                } else if (qpsSel.value !== 'custom') {
                    var sv = parseFloat(qpsSel.value);
                    if (!isNaN(sv) && sv >= 0) qpsVal = sv;
                }
            }

            var asyncChk = document.getElementById('userPanAsyncInput');
            var isAsync = asyncChk ? asyncChk.checked : true;

            var skipShaChk = document.getElementById('userPanSkipShaDedupInput');
            var isSkipSha = skipShaChk ? skipShaChk.checked : false;
            state.skipShaDedup = isSkipSha;

            var btn = document.getElementById('btnStartUserPanScan');
            if (btn) {
                btn.disabled = true;
                btn.innerText = isAsync ? '正在提交异步任务...' : '正在启动扫描任务...';
            }

            if (isAsync) {
                // 异步全自动导入模式：转入后台静默运行
                document.getElementById('importSourceSelector').style.display = 'none';
                var progressBox = document.getElementById('excelProgressBox');
                if (progressBox) progressBox.style.display = 'block';
                var barContainer = document.getElementById('excelProgressBarContainer');
                if (barContainer) barContainer.style.display = 'block';
                var bar = document.getElementById('excelProgressBar');
                if (bar) bar.style.width = '5%';
                document.getElementById('excelProgressText').innerText = '正在提交个人网盘异步深度扫描与入库任务...';
                document.getElementById('excelProgressSubText').innerText = '正在连接后台网盘驱动，支持转入后台运行并随时关闭此弹窗';

                var btnCancelImp = document.getElementById('btnCancelImportTask');
                if (btnCancelImp) btnCancelImp.style.display = 'inline-block';
                var btnDismiss = document.getElementById('btnDismissAsyncImport');
                if (btnDismiss) btnDismiss.style.display = 'inline-block';
                var btnCancelScan = document.getElementById('btnCancelPanScan');
                if (btnCancelScan) btnCancelScan.style.display = 'none';

                fetch('/api/private/pan/scan_user_dir', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        library_id: currentLibId,
                        provider: state.userPanSelectedProvider,
                        parent_file_id: state.userPanCurrentDir.id || '',
                        folder_name: state.userPanCurrentDir.name || '根目录',
                        dir_path: (state.userPanCurrentDir && state.userPanCurrentDir.path) ? state.userPanCurrentDir.path : '',
                        min_file_size_mb: minSize,
                        max_depth: maxDepth,
                        async: true,
                        enable_sync: enableSync,
                        skip_sha_dedup: isSkipSha,
                        qps: qpsVal
                    })
                })
                .then(function(res) { return res.json(); })
                .then(function(res) {
                    if (btn) {
                        btn.disabled = false;
                        updateUserPanBtnText();
                    }
                    if (res.success && res.task_id) {
                        state.activeImportTaskId = res.task_id;
                        showToast('⚡ 个人网盘后台异步导入任务已启动，可随时关闭窗口');
                        if (window.startGlobalImportTask) {
                            window.startGlobalImportTask({
                                taskId: res.task_id,
                                title: '个人网盘后台导入',
                                libraryId: currentLibId
                            });
                        } else if (window.showGlobalAsyncTaskBar) {
                            window.showGlobalAsyncTaskBar(res.task_id, '个人网盘后台导入');
                        }
                    } else {
                        throw new Error(res.error || res.message || '启动异步任务失败');
                    }
                })
                .catch(function(err) {
                    if (btn) {
                        btn.disabled = false;
                        updateUserPanBtnText();
                    }
                    document.getElementById('excelProgressText').innerText = '提交失败: ' + err.message;
                    document.getElementById('excelProgressSubText').innerText = '请检查网络或网盘登录状态';
                    var btnCancelImp = document.getElementById('btnCancelImportTask');
                    if (btnCancelImp) btnCancelImp.style.display = 'none';
                    var btnDismiss = document.getElementById('btnDismissAsyncImport');
                    if (btnDismiss) btnDismiss.style.display = 'none';
                    showToast('提交失败: ' + err.message);
                    setTimeout(function() {
                        resetImportSourceView();
                    }, 3000);
                });
                return;
            }

            // 同步模式（展开表格供人工确认）
            var btnCancelImp = document.getElementById('btnCancelImportTask');
            if (btnCancelImp) btnCancelImp.style.display = 'none';
            var btnDismiss = document.getElementById('btnDismissAsyncImport');
            if (btnDismiss) btnDismiss.style.display = 'none';

            fetch('/api/private/pan/scan_user_dir', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    library_id: currentLibId,
                    provider: state.userPanSelectedProvider,
                    parent_file_id: state.userPanCurrentDir.id || '',
                    folder_name: state.userPanCurrentDir.name || '根目录',
                    dir_path: (state.userPanCurrentDir && state.userPanCurrentDir.path) ? state.userPanCurrentDir.path : '',
                    min_file_size_mb: minSize,
                    max_depth: maxDepth,
                    async: false,
                    enable_sync: enableSync,
                    skip_sha_dedup: isSkipSha,
                    qps: qpsVal
                })
            })
            .then(function(res) { return res.json(); })
            .then(function(res) {
                if (btn) {
                    btn.disabled = false;
                    updateUserPanBtnText();
                }
                if (!res.success || !res.task_id) {
                    throw new Error(res.error || res.message || '启动扫描任务失败');
                }

                // 启动进度轮询并接入现有流程
                document.getElementById('importSourceSelector').style.display = 'none';
                var progressBox = document.getElementById('excelProgressBox');
                if (progressBox) progressBox.style.display = 'block';
                var barContainer = document.getElementById('excelProgressBarContainer');
                if (barContainer) barContainer.style.display = 'block';
                var btnCancel = document.getElementById('btnCancelPanScan');
                if (btnCancel) btnCancel.style.display = 'inline-block';

                state.currentScanTaskId = res.task_id;
                pollScanTaskProgress(res.task_id);
            })
            .catch(function(err) {
                if (btn) {
                    btn.disabled = false;
                    updateUserPanBtnText();
                }
                showToast('扫描失败: ' + err.message);
            });
        }

        function resetImportSourceView() {
            state.excelMatched = [];
            state.excelUnmatched = [];
            if (state.panScanTimer) {
                clearTimeout(state.panScanTimer);
                state.panScanTimer = null;
            }
            if (state.importTaskTimer) {
                clearTimeout(state.importTaskTimer);
                state.importTaskTimer = null;
            }
            state.currentScanTaskId = null;
            state.pendingPanSyncInfo = null;

            var fileInput = document.getElementById('excelFileInput');
            if (fileInput) fileInput.value = '';
            var box = document.getElementById('excelModalBox');
            if (box) box.classList.remove('modal-fullscreen');
            document.getElementById('importSourceSelector').style.display = 'block';
            document.getElementById('btnReUploadExcel').style.display = 'none';
            document.getElementById('excelProgressBox').style.display = 'none';
            document.getElementById('excelProgressBarContainer').style.display = 'none';
            document.getElementById('btnCancelPanScan').style.display = 'none';
            var btnCancelImp = document.getElementById('btnCancelImportTask');
            if (btnCancelImp) btnCancelImp.style.display = 'none';
            var btnDismiss = document.getElementById('btnDismissAsyncImport');
            if (btnDismiss) btnDismiss.style.display = 'none';
            document.getElementById('excelTabsBox').style.display = 'none';
            document.getElementById('btnConfirmBatchImport').style.display = 'none';
            var lblUpdateMode = document.getElementById('lblExcelUpdateMode');
            if (lblUpdateMode) lblUpdateMode.style.display = 'none';
            var chkUpdateMode = document.getElementById('chkExcelUpdateMode');
            if (chkUpdateMode) chkUpdateMode.checked = false;
            var lblSkipSha = document.getElementById('lblExcelSkipShaDedup');
            if (lblSkipSha) lblSkipSha.style.display = 'none';
            var chkSkipSha = document.getElementById('chkExcelSkipShaDedup');
            if (chkSkipSha) chkSkipSha.checked = false;
            var userPanSkipSha = document.getElementById('userPanSkipShaDedupInput');
            if (userPanSkipSha) userPanSkipSha.checked = false;
            state.skipShaDedup = false;
            var btnExportFooter = document.getElementById('btnExportUnmatchedFooter');
            if (btnExportFooter) btnExportFooter.style.display = 'none';
            var chkUserPanAsync = document.getElementById('userPanAsyncInput');
            if (chkUserPanAsync) chkUserPanAsync.checked = true;
            updateUserPanBtnText();
        }

        function handleCloseExcelModal() {
            if (state.excelUnmatched && state.excelUnmatched.length > 0) {
                var confirmMsg = '当前还有 ' + state.excelUnmatched.length + ' 条待确认影片未导入，确定要关闭并退出吗？\n\n提示：退出后本次内存数据将清空。建议先点击【📥 存入待确认暂存箱】保存至数据库稍后处理，或点击【📥 导出待确认列表】保存为 Excel。';
                if (!confirm(confirmMsg)) {
                    return;
                }
            }
            closeModal('excelModal');
        }

        function updatePanScanBtnText() {
            var chk = document.getElementById('panPackageAsyncInput');
            var btn = document.getElementById('btnStartPanScan');
            if (!btn) return;
            if (chk && chk.checked) {
                btn.innerText = '⚡ 提交后台异步导入';
            } else {
                btn.innerText = '🚀 开始深度扫描大包';
            }
        }

        function updateUserPanBtnText() {
            var chk = document.getElementById('userPanAsyncInput');
            var btn = document.getElementById('btnStartUserPanScan');
            if (!btn) return;
            if (chk && chk.checked) {
                btn.innerText = '⚡ 提交后台异步导入';
            } else {
                btn.innerText = '🚀 扫描并导入此文件夹';
            }
        }

        function handleDismissAsyncImport() {
            closeModal('excelModal');
            resetImportSourceView();
            showToast('已转入后台静默运行，可通过右下角悬浮胶囊随时关注进度');
        }

        // 监听全局导入任务进度事件 (与全局 kodi-remote.js 自动双向同步)
        window.addEventListener('juku:import_progress', function(e) {
            var detail = e.detail || {};
            var prog = detail.progress || {};
            var percent = prog.percent || 10;
            var stage = prog.stage || '正在处理中...';
            var status = detail.status;

            var bar = document.getElementById('excelProgressBar');
            if (bar) bar.style.width = percent + '%';
            var textEl = document.getElementById('excelProgressText');
            var subEl = document.getElementById('excelProgressSubText');

            if (status === 'pending' || status === 'scanning' || status === 'matching' || status === 'saving') {
                if (textEl) textEl.innerText = '⚡ 后台全自动导入进行中 (' + percent + '%)';
                if (subEl) {
                    var extraInfo = '';
                    if (prog.total_files > 0) {
                        extraInfo = ' (已处理 ' + prog.processed_files + '/' + prog.total_files + ' 个文件)';
                    }
                    subEl.innerText = stage + extraInfo + '。可随时关闭窗口或切换至其他页面，任务将常驻保持。';
                }
            }
        });

        // 监听全局导入任务完成事件
        window.addEventListener('juku:import_completed', function(e) {
            var resData = e.detail || {};
            var added = resData.added || 0;
            var merged = resData.merged || 0;
            var unmatched = resData.unmatched || 0;
            var total = resData.total || (added + merged);

            var bar = document.getElementById('excelProgressBar');
            if (bar) bar.style.width = '100%';
            var textEl = document.getElementById('excelProgressText');
            var subEl = document.getElementById('excelProgressSubText');
            if (textEl) textEl.innerText = '🎉 后台全自动导入已圆满完成！';
            if (subEl) subEl.innerText = '成功新增 ' + added + ' 部、合并 ' + merged + ' 部、待确认 ' + unmatched + ' 部。';
            var btnCancelImp = document.getElementById('btnCancelImportTask');
            if (btnCancelImp) btnCancelImp.style.display = 'none';

            if (typeof loadMovies === 'function') {
                loadMovies();
            }
        });

        // 监听全局导入任务失败事件
        window.addEventListener('juku:import_failed', function(e) {
            var res = e.detail || {};
            var textEl = document.getElementById('excelProgressText');
            var subEl = document.getElementById('excelProgressSubText');
            if (textEl) textEl.innerText = '❌ 后台导入失败';
            if (subEl) subEl.innerText = res.error_message || '导入任务执行异常';
            var btnCancelImp = document.getElementById('btnCancelImportTask');
            if (btnCancelImp) btnCancelImp.style.display = 'none';
        });

        // 监听全局导入任务取消事件
        window.addEventListener('juku:import_canceled', function() {
            var textEl = document.getElementById('excelProgressText');
            var subEl = document.getElementById('excelProgressSubText');
            if (textEl) textEl.innerText = '⏹️ 任务已取消';
            if (subEl) subEl.innerText = '导入任务已被用户主动取消';
            var btnCancelImp = document.getElementById('btnCancelImportTask');
            if (btnCancelImp) btnCancelImp.style.display = 'none';
        });

        // --- 网盘大包异步扫描交互 ---
        function startPanPackageScan() {
            var urlInput = document.getElementById('panPackageUrlInput');
            var rawUrl = urlInput ? urlInput.value.trim() : '';
            if (!rawUrl) {
                showToast('请先输入网盘合集分享链接');
                if (urlInput) urlInput.focus();
                return;
            }

            var pwdInput = document.getElementById('panPackagePwdInput');
            var pwd = pwdInput ? pwdInput.value.trim() : '';
            var minSizeSelect = document.getElementById('panPackageMinSizeInput');
            var minSizeMB = minSizeSelect ? parseInt(minSizeSelect.value, 10) : 100;

            var isAsync = false;
            var asyncChk = document.getElementById('panPackageAsyncInput');
            if (asyncChk && asyncChk.checked) {
                isAsync = true;
            }

            if (isAsync) {
                var libId = state.currentLib ? state.currentLib.id : '';
                if (!libId) {
                    showToast('未选择目标私有媒体库');
                    return;
                }

                document.getElementById('importSourceSelector').style.display = 'none';
                document.getElementById('excelProgressBox').style.display = 'block';
                document.getElementById('excelProgressBarContainer').style.display = 'block';
                document.getElementById('excelProgressBar').style.width = '10%';
                document.getElementById('excelProgressText').innerText = '正在向后台提交异步全自动导入任务...';
                document.getElementById('excelProgressSubText').innerText = '任务由后台独立协程执行深度扫描、分词、TMDB批量对齐与单事务入库...';
                document.getElementById('btnCancelPanScan').style.display = 'none';
                var btnCancelImp = document.getElementById('btnCancelImportTask');
                if (btnCancelImp) btnCancelImp.style.display = 'inline-block';
                var btnDismiss = document.getElementById('btnDismissAsyncImport');
                if (btnDismiss) btnDismiss.style.display = 'inline-block';

                fetch('/api/private/import_link', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        library_id: libId,
                        url: rawUrl,
                        password: pwd,
                        min_file_size_mb: minSizeMB,
                        async: true
                    })
                })
                .then(function(res) { return res.json(); })
                .then(function(data) {
                    if (data.success && data.task_id) {
                        state.activeImportTaskId = data.task_id;
                        showToast('⚡ 后台异步导入任务已启动，可随时关闭窗口');
                        if (window.startGlobalImportTask) {
                            window.startGlobalImportTask({
                                taskId: data.task_id,
                                title: '网盘大包后台导入',
                                libraryId: libId
                            });
                        } else if (window.showGlobalAsyncTaskBar) {
                            window.showGlobalAsyncTaskBar(data.task_id, '网盘大包后台导入');
                        }
                    } else {
                        throw new Error(data.message || data.error || '提交异步导入任务失败');
                    }
                })
                .catch(function(err) {
                    document.getElementById('excelProgressText').innerText = '提交失败: ' + err.message;
                    document.getElementById('excelProgressSubText').innerText = '请检查网络或分享链接';
                    var btnCancelImp = document.getElementById('btnCancelImportTask');
                    if (btnCancelImp) btnCancelImp.style.display = 'none';
                    var btnDismiss = document.getElementById('btnDismissAsyncImport');
                    if (btnDismiss) btnDismiss.style.display = 'none';
                    showToast('提交失败: ' + err.message);
                    setTimeout(function() {
                        resetImportSourceView();
                    }, 3000);
                });
                return;
            }

            // 同步扫描模式
            var btnCancelImp = document.getElementById('btnCancelImportTask');
            if (btnCancelImp) btnCancelImp.style.display = 'none';
            var btnDismiss = document.getElementById('btnDismissAsyncImport');
            if (btnDismiss) btnDismiss.style.display = 'none';
            document.getElementById('importSourceSelector').style.display = 'none';
            document.getElementById('excelProgressBox').style.display = 'block';
            document.getElementById('excelProgressBarContainer').style.display = 'block';
            document.getElementById('excelProgressBar').style.width = '5%';
            document.getElementById('excelProgressText').innerText = '正在提交网盘大包深度扫描任务...';
            document.getElementById('excelProgressSubText').innerText = '正在连接后台网盘驱动并递归各层子目录...';
            document.getElementById('btnCancelPanScan').style.display = 'inline-block';

            fetch('/api/private/pan/scan_package', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    url: rawUrl,
                    password: pwd,
                    min_file_size_mb: minSizeMB,
                    max_depth: 5
                })
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (data.success && data.task_id) {
                    state.currentScanTaskId = data.task_id;
                    pollScanTaskProgress(data.task_id);
                } else {
                    throw new Error(data.error || data.message || '启动扫描任务失败');
                }
            })
            .catch(function(err) {
                document.getElementById('excelProgressText').innerText = '启动失败: ' + err.message;
                document.getElementById('excelProgressSubText').innerText = '请检查分享链接或提取码是否正确';
                document.getElementById('btnCancelPanScan').style.display = 'none';
                showToast('扫描启动失败: ' + err.message);
                setTimeout(function() {
                    resetImportSourceView();
                }, 3000);
            });
        }

        function pollScanTaskProgress(taskId) {
            if (state.currentScanTaskId !== taskId) return;

            fetch('/api/private/pan/scan_tasks/' + taskId)
                .then(function(res) { return res.json(); })
                .then(function(res) {
                    if (!res.success || !res.data) {
                        throw new Error(res.error || '获取任务状态异常');
                    }
                    var task = res.data;
                    var progress = task.progress_percent || 10;
                    var bar = document.getElementById('excelProgressBar');
                    if (bar) bar.style.width = progress + '%';

                    var textEl = document.getElementById('excelProgressText');
                    var subEl = document.getElementById('excelProgressSubText');

                    if (task.status === 'scanning') {
                        if (textEl) textEl.innerText = task.stage || '正在扫描网盘目录...';
                        var sCount = task.scanned_files_count || 0;
                        var mCount = task.media_files_count || 0;
                        if (subEl) {
                            if (sCount === 0) {
                                subEl.innerText = '正在深入扫描各层子目录并读取文件清单...';
                            } else {
                                subEl.innerText = '已检索 ' + sCount + ' 个文件，捕获 ' + mCount + ' 个有效视频';
                            }
                        }
                        state.panScanTimer = setTimeout(function() {
                            pollScanTaskProgress(taskId);
                        }, 600);
                    } else if (task.status === 'completed') {
                        if (textEl) textEl.innerText = '🎉 网盘扫描完成！共捕获 ' + (task.results ? task.results.length : 0) + ' 个视频文件';
                        if (subEl) subEl.innerText = '正在进行影视文件名智能清洗与 TMDB 海报对齐...';
                        document.getElementById('btnCancelPanScan').style.display = 'none';

                        var rawItems = (task.results || []).map(function(item) {
                            var cleanFid = item.file_id || '';
                            if (cleanFid && cleanFid.indexOf('eyJ') !== -1) {
                                try {
                                    var dec = JSON.parse(atob(cleanFid));
                                    if (dec && (dec.fid || dec.file_id || dec.target_id || dec.fs_id)) {
                                        cleanFid = String(dec.fid || dec.file_id || dec.target_id || dec.fs_id);
                                    }
                                } catch (e) {}
                            }
                            return {
                                rawFileName: item.raw_file_name,
                                remark: item.remark,
                                linkUrl: item.link_url,
                                sha: item.sha || '',
                                fileSize: item.file_size || 0,
                                parentFolderName: item.parent_folder_path || item.parent_folder_name || '',
                                parentFolderPath: item.parent_folder_path || item.parent_folder_name || '',
                                provider: item.provider || '',
                                fileId: cleanFid,
                                alreadyExpanded: true,
                                isScannedFile: true
                            };
                        });

                        setTimeout(function() {
                            processRawImportItems(rawItems);
                        }, 400);
                    } else if (task.status === 'failed') {
                        if (textEl) textEl.innerText = '❌ 扫描失败';
                        if (subEl) subEl.innerText = task.error_message || '未能成功获取网盘文件';
                        document.getElementById('btnCancelPanScan').style.display = 'none';
                        showToast(task.error_message || '大包扫描失败');
                    } else if (task.status === 'canceled') {
                        resetImportSourceView();
                        showToast('已取消扫描');
                    }
                })
                .catch(function(err) {
                    state.panScanTimer = setTimeout(function() {
                        pollScanTaskProgress(taskId);
                    }, 1200);
                });
        }

        function cancelPanPackageScan() {
            var taskId = state.currentScanTaskId;
            if (!taskId) {
                resetImportSourceView();
                return;
            }
            fetch('/api/private/pan/scan_tasks/' + taskId + '/cancel', { method: 'POST' })
                .then(function() {
                    resetImportSourceView();
                    showToast('已取消扫描任务');
                })
                .catch(function() {
                    resetImportSourceView();
                });
        }

        // 1. 从链接本身提取文件名 (ED2K / Magnet dn / HTTP 视频直链)
        function extractNameFromLink(linkUrl) {
            if (!linkUrl) return '';
            var raw = linkUrl.trim();
            // ED2K 格式: ed2k://|file|文件名|大小|HASH|/
            if (raw.toLowerCase().indexOf('ed2k://|file|') === 0) {
                var parts = raw.split('|');
                if (parts.length >= 3) {
                    try {
                        return decodeURIComponent(parts[2]).trim();
                    } catch (e) {
                        return parts[2].trim();
                    }
                }
            }
            // 磁力链 dn 参数: magnet:?xt=...&dn=文件名
            if (raw.toLowerCase().indexOf('magnet:?') === 0) {
                var match = raw.match(/[?&]dn=([^&]+)/i);
                if (match && match[1]) {
                    try {
                        return decodeURIComponent(match[1].replace(/\+/g, ' ')).trim();
                    } catch (e) {
                        return match[1].trim();
                    }
                }
            }
            // 普通直链 URL 路径末尾包含视频文件名
            if (raw.indexOf('http://') === 0 || raw.indexOf('https://') === 0) {
                try {
                    var uObj = new URL(raw);
                    var p = uObj.pathname;
                    var lastSegment = p.substring(p.lastIndexOf('/') + 1);
                    if (/\.(mp4|mkv|ts|iso|avi|mov|wmv|flv|m2ts|strm|m4v)$/i.test(lastSegment)) {
                        return decodeURIComponent(lastSegment).trim();
                    }
                } catch (e) {}
            }
            return '';
        }

        // 1.2 探测是否属于播放/下载链接 (兼容多行单元格检测)
        function isDirectOrPanLink(str) {
            if (!str) return false;
            var s = String(str).trim();
            var lower = s.toLowerCase();
            if (lower.indexOf('http://') === 0 || lower.indexOf('https://') === 0 ||
                lower.indexOf('magnet:?') === 0 || lower.indexOf('ed2k://') === 0 ||
                isPanShareLink(s)) {
                return true;
            }
            // 兼容多行单元格首行存在空行或内部包含有效链接特征
            if (/ed2k:\/\/\|file\|/i.test(s) || /magnet:\?/i.test(s) || /(?:https?:\/\/[^\s]+)/i.test(s)) {
                var lines = s.split(/\r?\n/).map(function(l) { return l.trim(); }).filter(Boolean);
                for (var li = 0; li < lines.length; li++) {
                    var ll = lines[li].toLowerCase();
                    if (ll.indexOf('http://') === 0 || ll.indexOf('https://') === 0 ||
                        ll.indexOf('magnet:?') === 0 || ll.indexOf('ed2k://') === 0 ||
                        isPanShareLink(lines[li])) {
                        return true;
                    }
                }
            }
            return false;
        }

        // 1.2.1 拆分单元格多行文本（支持换行符切分并清洗空白）
        function splitCellLines(str) {
            if (!str) return [];
            return String(str).split(/\r?\n/).map(function(s) { return s.trim(); }).filter(Boolean);
        }

        // 1.2.2 拆分链接单元格（支持换行符切分以及同一行紧邻黏贴的多个链接切分）
        function splitLinkCell(str) {
            if (!str) return [];
            var lines = String(str).split(/\r?\n/).map(function(s) { return s.trim(); }).filter(Boolean);
            var result = [];
            for (var i = 0; i < lines.length; i++) {
                var line = lines[i];
                // 1. 同行多个 ed2k 链接切分: ed2k://|file|...|/
                if ((line.match(/ed2k:\/\/\|file\|/gi) || []).length > 1) {
                    var ed2kMatches = line.match(/ed2k:\/\/\|file\|[^|]+\|\d+\|[a-fA-F0-9]{32}\|(?:[^|]+\|)?\//g);
                    if (ed2kMatches && ed2kMatches.length > 1) {
                        result.push.apply(result, ed2kMatches);
                        continue;
                    }
                }
                // 2. 同行多个 magnet 磁力链切分
                if ((line.match(/magnet:\?/gi) || []).length > 1) {
                    var magMatches = line.split(/(?=magnet:\?)/i).map(function(s) { return s.trim(); }).filter(Boolean);
                    if (magMatches.length > 1) {
                        result.push.apply(result, magMatches);
                        continue;
                    }
                }
                // 3. 同行多个 http(s) 链接切分 (以空格隔开)
                if (/\s+https?:\/\//i.test(line)) {
                    var httpMatches = line.split(/\s+(?=https?:\/\/)/i).map(function(s) { return s.trim(); }).filter(Boolean);
                    if (httpMatches.length > 1) {
                        result.push.apply(result, httpMatches);
                        continue;
                    }
                }
                result.push(line);
            }
            return result;
        }

        // 1.3 探测文本是否为典型的画质/音轨/版本规格备注
        function looksLikeRemark(str) {
            if (!str) return false;
            var s = String(str).trim();
            var remarkKeywords = [
                '4k', '2160p', '1080p', '720p', 'uhd', 'remux', 'bluray', 'blu-ray', 'bd', 'web-dl', 'webdl',
                'hdtv', 'dovi', 'dolby', '杜比', 'hdr', 'hdr10', 'sdr', 'atmos', '全景声', 'truehd', 'dts',
                '国语', '粤语', '双语', '国配', '中字', '特效字幕', '简繁', '原盘', 'diy', '次时代', '次世代',
                '菜单', '加长版', '剧场版', '未删减', '修复版', '重制', '特别收录', '花絮', '全集', '合集'
            ];
            var lower = s.toLowerCase();
            for (var i = 0; i < remarkKeywords.length; i++) {
                if (lower.indexOf(remarkKeywords[i]) !== -1) return true;
            }
            if (/(?:第\s*\d+\s*[-~至到与和及]?\s*\d*\s*[集话期]|全\s*\d+\s*[集话期]|s\d{1,2}(?:e\d{1,4})?)/i.test(s)) {
                return true;
            }
            return false;
        }

        // 1.4 解析包含多方括号的单元格 (如: [片名][版本/备注说明][文件大小])
        function parseBracketedCell(text) {
            if (!text) return null;
            var matches = [];
            var re = /\[([^\]]+)\]/g;
            var m;
            while ((m = re.exec(text)) !== null) {
                matches.push(m[1].trim());
            }
            if (matches.length >= 2) {
                var titlePart = matches[0];
                var remarkPart = matches[1];
                var extraParts = matches.slice(2).join(' ');
                if (extraParts) {
                    remarkPart += ' ' + extraParts;
                }
                return {
                    title: titlePart,
                    remark: remarkPart
                };
            }
            return null;
        }

        // 1.5 智能规范中文片名全半角冒号
        function normalizeChineseColon(title) {
            if (!title) return '';
            if (/[\u4e00-\u9fa5]/.test(title) && title.indexOf(':') !== -1) {
                return title.replace(/\s*:\s*/g, '：');
            }
            return title;
        }

        // 1.6 智能剥离剧集标题中的“第N季 / Season N”后缀并提取季号
        function cleanSeasonFromTitle(title) {
            if (!title) return { title: '', season: -1 };
            var raw = String(title).trim();
            var seasonNum = -1;

            function parseChineseNum(cn) {
                if (!cn) return 0;
                var n = parseInt(cn, 10);
                if (!isNaN(n)) return n;
                var digitMap = { '零': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9 };
                if (cn === '十') return 10;
                if (cn.indexOf('十') === 0) {
                    return 10 + (digitMap[cn[1]] || 0);
                }
                if (cn.indexOf('十') === 1) {
                    return (digitMap[cn[0]] || 1) * 10 + (digitMap[cn[2]] || 0);
                }
                return (digitMap[cn] !== undefined) ? digitMap[cn] : 0;
            }

            // 0. 先行剥离剧集总集数与完结描述 (如 "全8集", "全24集", "共12集", "全集", "完结", "大结局")
            var totalEpisodesRegex = /(?:^|[\s\._\-\[（(【])(?:(?:全|共)\s*\d+\s*[集话期]|全集|完结|大结局|\d+[-~至到与和及]\d+\s*[集话期]\s*全?)(?:$|[\s\._\-\]）)】])/gi;
            raw = raw.replace(totalEpisodesRegex, ' ');

            // 1. 括号包裹的季数： (第一季), [第2季], 【Season 1】, (第0季)
            var bracketRegex = /[\(（\[【]\s*(?:第\s*([零一二三四五六七八九十\d]+)\s*季|season\s*(\d{1,2})|最终季)\s*[\)）\]】]/i;
            var bMatch = raw.match(bracketRegex);
            if (bMatch) {
                if (bMatch[1]) seasonNum = parseChineseNum(bMatch[1]);
                else if (bMatch[2]) seasonNum = parseInt(bMatch[2], 10);
                raw = raw.replace(bracketRegex, ' ');
            }

            // 2. 空格/标点/末尾季数： " 第一季", ".第一季", "：第一季", " Season 1", " S02", " S00"
            var tailRegex = /(?:[:：\s._\-]+|\b)(?:第\s*([零一二三四五六七八九十\d]+)\s*季(?:全|度)?|season\s*(\d{1,2})|\bS(\d{1,2})\b|最终季)(?:$|[\s\._\-]|(?:全|共)\s*\d+\s*[集话期]|全集)/i;
            var tMatch = raw.match(tailRegex);
            if (tMatch) {
                if (seasonNum < 0) {
                    if (tMatch[1]) seasonNum = parseChineseNum(tMatch[1]);
                    else if (tMatch[2]) seasonNum = parseInt(tMatch[2], 10);
                    else if (tMatch[3]) seasonNum = parseInt(tMatch[3], 10);
                }
                raw = raw.replace(tailRegex, ' ');
            }

            // 再次清理可能残留的总集数描述
            raw = raw.replace(totalEpisodesRegex, ' ');

            var cleaned = raw.trim().replace(/[\s:：\-_/([{\])}]+$/, '').replace(/^[\s:：\-_/([{\])}]+/, '').trim();
            cleaned = cleaned.replace(/\s+/g, ' ');
            return {
                title: cleaned || String(title).trim(),
                season: seasonNum
            };
        }

        // 1.7 将季数转换为规范中文表示（如 2 -> "第二季"）
        function formatSeasonZh(season) {
            var zhDigits = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十"];
            if (season >= 1 && season <= 10) return "第" + zhDigits[season] + "季";
            if (season > 10 && season < 20) return "第十" + zhDigits[season % 10] + "季";
            if (season >= 20 && season < 100) {
                var tens = Math.floor(season / 10);
                var units = season % 10;
                var uStr = (units !== 0) ? zhDigits[units] : "";
                return "第" + zhDigits[tens] + "十" + uStr + "季";
            }
            return "第" + season + "季";
        }

        // 1.9 目录与影视名称智能识别与清洗过滤（防止季目录/年份目录/泛目录造成错误聚合）
        function isSeasonFolderName(name) {
            if (!name) return false;
            var trimmed = String(name).trim();
            return /^(?:season\s*\d+|s\d+(?:[-~]\s*s?\d+)?|第\s*[0-9一二三四五六七八九十]+\s*[季部]|specials?|extras?|sp|ova|花絮|特别篇|预告|彩蛋)$/i.test(trimmed);
        }

        function isYearFolderName(name) {
            if (!name) return false;
            var trimmed = String(name).trim();
            return /^(?:(?:19|20)\d{2}(?:[-~](?:19|20)?\d{2})?|(?:19|20)\d[xX](?:[-~](?:19|20)?\d[xX])?|\d{1,4})$/i.test(trimmed);
        }

        function isGenericFolderName(name) {
            if (!name) return true;
            var trimmed = String(name).trim();
            if (!trimmed) return true;
            if (isSeasonFolderName(trimmed)) return true;
            if (isYearFolderName(trimmed)) return true;
            if (/^(?:日韩|港台|欧美|国产|大陆|华语|海外|韩国|日本|泰剧|美剧|英剧|德剧|法剧)?(?:电影|剧集|电视剧|动漫|动画|综艺|纪录片|短剧|影视|合集|系列|大包|资源|网盘|分享|整理|归档|精选|更新|更新中|已完结|4[kK]|1080[pP]|2160[pP]|原盘|蓝光|BD|HD|Remux|HDR|DoVi|杜比|高码|全集|全\d+集|合集包|夸克|阿里|115|百度|迅雷|UC)(?:[【\[\(（].*?[】\]\)）])?$/i.test(trimmed)) {
                return true;
            }
            return false;
        }

        function isWeakSeriesTitle(title) {
            if (!title) return true;
            var trimmed = String(title).trim();
            if (!trimmed || trimmed.length <= 1) return true;
            if (isSeasonFolderName(trimmed)) return true;
            if (isYearFolderName(trimmed)) return true;
            if (isGenericFolderName(trimmed)) return true;
            if (/^(?:ep?\d+|第\d+集|unknown|未命名|未命名影视|新建文件夹)$/i.test(trimmed)) return true;
            return false;
        }

        function resolveMeaningfulSeriesFolder(fullPath) {
            if (!fullPath) return '';
            var parts = String(fullPath).replace(/\\/g, '/').split('/').map(function(s) { return s.trim(); }).filter(Boolean);
            if (parts.length === 0) return '';
            for (var i = parts.length - 1; i >= 0; i--) {
                var part = parts[i];
                if (!isGenericFolderName(part) && !isSeasonFolderName(part) && !isYearFolderName(part) && !isWeakSeriesTitle(part)) {
                    return part;
                }
            }
            return '';
        }

        // 2. 从文件名智能提炼精简画质/版本备注 (Smart Remark)
        function extractSmartRemark(fileName, existingRemark) {
            if (existingRemark && existingRemark.trim() && existingRemark.trim() !== '批量导入链接') {
                var er = existingRemark.trim();
                var hasSpecificAudioInExisting = /TrueHD|DTS-HD|DTS:X|DTS|DDP|AC3|LPCM|FLAC/i.test(er);
                var fnHasSpecificAudio = fileName && /TrueHD|DTS-HD|DTS-MA|DTSHD|DTS:X|DTS-X|\bDTS\b|DDP|EAC3|E-AC-3|AC3|DD5\.1|LPCM|PCM|FLAC/i.test(fileName);
                if (hasSpecificAudioInExisting || !fnHasSpecificAudio) {
                    return er;
                }
            }
            if (!fileName) return '';
            var fn = fileName.toLowerCase();
            var tags = [];

            // 分辨率
            if (fn.indexOf('2160p') !== -1 || fn.indexOf('4k') !== -1 || fn.indexOf('uhd') !== -1) {
                tags.push('4K');
            } else if (fn.indexOf('1080p') !== -1 || fn.indexOf('fhd') !== -1) {
                tags.push('1080P');
            } else if (fn.indexOf('720p') !== -1 || fn.indexOf('hd') !== -1) {
                tags.push('720P');
            }

            // 压制 / 媒介
            if (fn.indexOf('remux') !== -1) {
                tags.push('REMUX');
            } else if (fn.indexOf('bluray') !== -1 || fn.indexOf('blu-ray') !== -1 || fn.indexOf('bdrip') !== -1) {
                tags.push('BluRay');
            } else if (fn.indexOf('web-dl') !== -1 || fn.indexOf('webdl') !== -1 || fn.indexOf('web-rip') !== -1) {
                tags.push('WEB-DL');
            } else if (fn.indexOf('hdtv') !== -1) {
                tags.push('HDTV');
            }

            // 动态范围
            if (fn.indexOf('dovi') !== -1 || fn.indexOf('dv') !== -1 || fn.indexOf('dolby vision') !== -1 || fn.indexOf('杜比视界') !== -1) {
                tags.push('杜比视界');
            } else if (fn.indexOf('hdr10+') !== -1 || fn.indexOf('hdr10plus') !== -1) {
                tags.push('HDR10+');
            } else if (fn.indexOf('hdr10') !== -1 || fn.indexOf('hdr') !== -1) {
                tags.push('HDR');
            }

            // 探测声道 (7.1, 5.1, 2.0)
            var channel = '';
            if (fn.indexOf('7.1') !== -1) {
                channel = '7.1';
            } else if (fn.indexOf('5.1') !== -1) {
                channel = '5.1';
            } else if (fn.indexOf('2.0') !== -1) {
                channel = '2.0';
            }

            // 智能音轨提炼（显示具体音轨类型与声道，如 TrueHD.7.1、DTS-HD MA 5.1 等）
            var hasAtmos = (fn.indexOf('atmos') !== -1 || fn.indexOf('全景声') !== -1);
            if (fn.indexOf('truehd') !== -1) {
                tags.push(channel ? ('TrueHD.' + channel) : 'TrueHD');
            } else if (fn.indexOf('dts-hd') !== -1 || fn.indexOf('dts-ma') !== -1 || fn.indexOf('dtshd') !== -1) {
                if (fn.indexOf('ma') !== -1 || fn.indexOf('master') !== -1) {
                    tags.push(channel ? ('DTS-HD MA ' + channel) : 'DTS-HD MA');
                } else if (fn.indexOf('hr') !== -1) {
                    tags.push(channel ? ('DTS-HD HR ' + channel) : 'DTS-HD HR');
                } else {
                    tags.push(channel ? ('DTS-HD ' + channel) : 'DTS-HD');
                }
            } else if (fn.indexOf('dts:x') !== -1 || fn.indexOf('dts-x') !== -1 || fn.indexOf('dtsx') !== -1) {
                tags.push(channel ? ('DTS:X ' + channel) : 'DTS:X');
            } else if (/\bdts\b|dts[._\s]/.test(fn)) {
                tags.push(channel ? ('DTS ' + channel) : 'DTS');
            } else if (fn.indexOf('ddp') !== -1 || fn.indexOf('eac3') !== -1 || fn.indexOf('e-ac-3') !== -1) {
                tags.push(channel ? ('DDP ' + channel) : 'DDP');
            } else if (fn.indexOf('ac3') !== -1 || fn.indexOf('dd5.1') !== -1) {
                tags.push(channel ? ('AC3 ' + channel) : 'AC3');
            } else if (fn.indexOf('lpcm') !== -1 || fn.indexOf('pcm') !== -1) {
                tags.push(channel ? ('LPCM ' + channel) : 'LPCM');
            } else if (fn.indexOf('flac') !== -1) {
                tags.push(channel ? ('FLAC ' + channel) : 'FLAC');
            } else if (fn.indexOf('aac') !== -1 && channel === '5.1') {
                tags.push('AAC 5.1');
            }

            if (hasAtmos) {
                tags.push('Atmos');
            }

            // 语言与配音
            if (fn.indexOf('国粤') !== -1 || fn.indexOf('双语') !== -1) {
                tags.push('国粤双语');
            } else if (fn.indexOf('国语') !== -1 || fn.indexOf('国配') !== -1) {
                tags.push('国配');
            } else if (fn.indexOf('粤语') !== -1) {
                tags.push('粤语');
            }

            if (tags.length > 0) {
                return tags.join(' · ');
            }
            return '';
        }

        // 3. 网盘公开分享链接只读嗅探首个主视频文件元数据 (0配额消耗、0空间占用，包含文件名、文件大小与 SHA1)
        function sniffPanShareMediaInfo(linkUrl, password) {
            if (!linkUrl) return Promise.resolve(null);
            if (!isPanShareLink(linkUrl)) return Promise.resolve(null);

            var apiUrl = '/api/list?share_url=' + encodeURIComponent(linkUrl) + '&flat=1';
            if (password) apiUrl += '&code=' + encodeURIComponent(password);

            console.log('[Sniff] 发起网盘只读嗅探:', linkUrl);
            return fetch(apiUrl)
                .then(function(res) {
                    if (!res.ok) throw new Error('HTTP ' + res.status);
                    return res.json();
                })
                .then(function(data) {
                    if (data && Array.isArray(data.files) && data.files.length > 0) {
                        var videoExts = ['.mp4', '.mkv', '.ts', '.iso', '.avi', '.mov', '.wmv', '.flv', '.m2ts', '.strm', '.m4v'];
                        var targetFile = null;
                        for (var i = 0; i < data.files.length; i++) {
                            var f = data.files[i];
                            var fn = (f.name || f.file_name || '').toLowerCase();
                            for (var e = 0; e < videoExts.length; e++) {
                                if (fn.indexOf(videoExts[e]) !== -1) {
                                    targetFile = f;
                                    break;
                                }
                            }
                            if (targetFile) break;
                        }
                        if (!targetFile && data.files[0]) {
                            targetFile = data.files[0];
                        }
                        if (targetFile) {
                            var resName = targetFile.name || targetFile.file_name || '';
                            var resSha = targetFile.sha || targetFile.sha1 || '';
                            var resSize = targetFile.size || targetFile.file_size || 0;
                            console.log('[Sniff] 嗅探成功:', resName, 'SHA:', resSha);
                            return {
                                fileName: resName,
                                sha: resSha ? String(resSha).trim().toUpperCase() : '',
                                fileSize: resSize
                            };
                        }
                    }
                    console.warn('[Sniff] 未返回文件列表:', data);
                    return null;
                })
                .catch(function(err) {
                    console.warn('[Sniff] 嗅探失败:', err);
                    return null;
                });
        }

        function sniffPanShareFileName(linkUrl, password) {
            return sniffPanShareMediaInfo(linkUrl, password).then(function(info) {
                return info ? info.fileName : '';
            });
        }

        // 3.1 自适应网盘大包深度展开 (Fast Path 轻量平铺 + Deep Path 后端穿透接管)
        async function expandPanShareItem(item) {
            if (!item || !item.linkUrl) return [item];
            // 若条目已扫描/已展开，或不是网盘分享链接，或者已经包含具体的子文件定位符 (fid)，则视为单文件，无需展开
            if (item.alreadyExpanded || item.isScannedFile || !isPanShareLink(item.linkUrl) || hasSubFileLocator(item.linkUrl)) {
                return [item];
            }

            var videoExts = ['.mp4', '.mkv', '.ts', '.iso', '.avi', '.mov', '.wmv', '.flv', '.m2ts', '.strm', '.m4v', '.rmvb', '.webm'];
            function isVideoFile(fname) {
                if (!fname) return false;
                var lower = fname.toLowerCase();
                for (var vi = 0; vi < videoExts.length; vi++) {
                    if (lower.indexOf(videoExts[vi]) !== -1) return true;
                }
                return false;
            }

            // 1. Fast Path: 请求轻量探测接口 /api/list?share_url=...&flat=1
            try {
                var apiUrl = '/api/list?share_url=' + encodeURIComponent(item.linkUrl) + '&flat=1';
                if (item.password) apiUrl += '&code=' + encodeURIComponent(item.password);

                var fastRes = await fetch(apiUrl);
                if (fastRes.ok) {
                    var fastData = await fastRes.json();
                    if (fastData && Array.isArray(fastData.files) && fastData.files.length > 0) {
                        var hasFolder = false;
                        var videoFiles = [];
                        for (var fi = 0; fi < fastData.files.length; fi++) {
                            var f = fastData.files[fi];
                            if (f.is_folder || f.type === 'folder' || f.is_dir) {
                                hasFolder = true;
                            }
                            var fName = f.name || f.file_name || '';
                            if (isVideoFile(fName)) {
                                videoFiles.push(f);
                            }
                        }

                        // 若没有文件夹且直接获取到了视频文件，Fast Path 命中
                        if (!hasFolder && videoFiles.length > 0) {
                            console.log('[PanExpand] Fast Path 成功展开 ' + videoFiles.length + ' 个媒体文件:', item.linkUrl);
                            return videoFiles.map(function(vf) {
                                var vfName = vf.name || vf.file_name || '';
                                var vfSha = vf.sha || vf.sha1 || '';
                                var vfSize = vf.size || vf.file_size || 0;
                                var vfId = vf.id || vf.file_id || '';
                                var vfCid = vf.cid || vf.pdir_fid || vf.parent_id || '';
                                var subLink = item.linkUrl;
                                if (vfId) {
                                    if (vfCid && vfCid !== '0' && vfCid !== 'root' && vfCid !== 'ROOT') {
                                        if (subLink.indexOf('#') !== -1) {
                                            subLink = subLink + '&cid=' + encodeURIComponent(vfCid) + '&fid=' + encodeURIComponent(vfId);
                                        } else {
                                            subLink = subLink + '#cid=' + encodeURIComponent(vfCid) + '&fid=' + encodeURIComponent(vfId);
                                        }
                                    } else {
                                        if (subLink.indexOf('#') !== -1) {
                                            subLink = subLink + '&fid=' + encodeURIComponent(vfId);
                                        } else {
                                            subLink = subLink + '#fid=' + encodeURIComponent(vfId);
                                        }
                                    }
                                }
                                var cleanExp = extractTmdbIdAndClean(item.explicitTitle || item.rawFileName || '');
                                var cleanVf = extractTmdbIdAndClean(vfName);
                                var expTmdb = item.tmdbId || cleanExp.tmdbId || cleanVf.tmdbId || 0;
                                var expTitle = cleanExp.title || (item.hasExplicitTitle && item.rawFileName ? item.rawFileName : '');
                                var expYear = item.year || cleanExp.year || cleanVf.year || '';
                                return {
                                    rawFileName: vfName,
                                    linkFileName: vfName,
                                    explicitTitle: expTitle,
                                    tmdbId: expTmdb,
                                    hasExplicitTitle: item.hasExplicitTitle || false,
                                    remark: item.remark || '',
                                    linkUrl: subLink,
                                    password: item.password || '',
                                    year: expYear,
                                    parentFolderName: item.parentFolderName || '',
                                    seasonNumber: item.seasonNumber || 0,
                                    episodeNumber: 0,
                                    sha: vfSha ? String(vfSha).trim().toUpperCase() : '',
                                    fileSize: vfSize
                                };
                            });
                        }
                    }
                }
            } catch (eFast) {
                console.warn('[PanExpand] Fast Path 探测异常，准备进入 Deep Path:', eFast);
            }

            // 2. Deep Path: 调用后端深度展开接口 POST /api/private/pan/expand_link (递归深挖5层并过滤广告与非视频)
            try {
                console.log('[PanExpand] 启动 Deep Path 穿透深度扫描大包:', item.linkUrl);
                var deepRes = await fetch('/api/private/pan/expand_link', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        url: item.linkUrl,
                        password: item.password || '',
                        min_file_size_mb: 15
                    })
                });
                if (deepRes.ok) {
                    var deepData = await deepRes.json();
                    if (deepData && deepData.success && Array.isArray(deepData.files) && deepData.files.length > 0) {
                        console.log('[PanExpand] Deep Path 成功递归展开 ' + deepData.files.length + ' 个视频:', item.linkUrl);
                        return deepData.files.map(function(df) {
                            var dfName = df.raw_file_name || '';
                            var dfSha = df.sha || '';
                            var dfSize = df.file_size || 0;
                            var dfLink = df.link_url || item.linkUrl;
                            var dfFolder = df.parent_folder_name || item.parentFolderName || '';
                            var cleanExp = extractTmdbIdAndClean(item.explicitTitle || item.rawFileName || '');
                            var cleanDf = extractTmdbIdAndClean(dfName);
                            var expTmdb = item.tmdbId || cleanExp.tmdbId || cleanDf.tmdbId || 0;
                            var expTitle = cleanExp.title || (item.hasExplicitTitle && item.rawFileName ? item.rawFileName : '');
                            var expYear = item.year || cleanExp.year || cleanDf.year || '';
                            return {
                                rawFileName: dfName,
                                linkFileName: dfName,
                                explicitTitle: expTitle,
                                tmdbId: expTmdb,
                                hasExplicitTitle: item.hasExplicitTitle || false,
                                remark: item.remark || df.remark || '',
                                linkUrl: dfLink,
                                password: item.password || '',
                                year: expYear,
                                parentFolderName: dfFolder,
                                seasonNumber: item.seasonNumber || 0,
                                episodeNumber: 0,
                                sha: dfSha ? String(dfSha).trim().toUpperCase() : '',
                                fileSize: dfSize
                            };
                        });
                    }
                }
            } catch (eDeep) {
                console.error('[PanExpand] Deep Path 展开失败:', eDeep);
            }

            return [item];
        }

        // 4. 纯文本 / 剪贴板一键粘贴解析
        function handleRawTextParse() {
            var text = (document.getElementById('rawTextInput').value || '').trim();
            if (!text) {
                showToast('请先输入或粘贴文本内容');
                return;
            }

            var lines = text.split('\n');
            var rawItems = [];
            var ed2kRegex = /(ed2k:\/\/\|file\|.+?\|\d+\|[a-fA-F0-9]{32}\|[^\s\n\r]*?\/)/i;
            var magnetRegex = /(magnet:\?[^\s]+)/i;
            var httpRegex = /(https?:\/\/[^\s]+)/i;

            for (var i = 0; i < lines.length; i++) {
                var line = lines[i].trim();
                if (!line) continue;

                var linkUrl = '';
                var ed2kMatch = line.match(ed2kRegex);
                if (ed2kMatch) {
                    linkUrl = ed2kMatch[1];
                } else {
                    var magMatch = line.match(magnetRegex);
                    if (magMatch) {
                        linkUrl = magMatch[1];
                    } else {
                        var httpMatch = line.match(httpRegex);
                        if (httpMatch) {
                            linkUrl = httpMatch[1];
                        }
                    }
                }

                if (linkUrl) {
                    var prefix = line.replace(linkUrl, '').trim();
                    prefix = prefix.replace(/^[【\[\(（]|[\)）\]】]$/g, '').trim();

                    var extractedName = extractNameFromLink(linkUrl);
                    var itemFileName = '';
                    var itemRemark = '';

                    var bp = parseBracketedCell(prefix);
                    if (bp) {
                        itemFileName = bp.title;
                        itemRemark = bp.remark;
                    } else if (looksLikeRemark(prefix)) {
                        itemRemark = prefix;
                        itemFileName = extractedName || '';
                    } else {
                        itemFileName = extractedName || prefix;
                    }

                    rawItems.push({
                        rawFileName: itemFileName,
                        linkFileName: extractedName || '',
                        remark: itemRemark,
                        linkUrl: linkUrl
                    });
                } else if (line.length >= 2) {
                    // 没有直接链接但有纯文本片名
                    rawItems.push({
                        rawFileName: line,
                        remark: '',
                        linkUrl: ''
                    });
                }
            }

            if (rawItems.length === 0) {
                showToast('未能从文本中检测到有效影视信息或播放链接');
                return;
            }

            processRawImportItems(rawItems);
        }

        // 5. Excel / CSV 表格解析 (支持表头感知、自适应 纯链接、[备注+链接]、[片名+链接]、[片名+备注+链接] 及提取码)
        function handleExcelUpload(input) {
            var file = input.files[0];
            if (!file) return;

            function processFile() {
                var reader = new FileReader();
                reader.onload = function(e) {
                    try {
                        var data = new Uint8Array(e.target.result);
                        var workbook = XLSX.read(data, { type: 'array' });
                        var firstSheet = workbook.Sheets[workbook.SheetNames[0]];
                        var rows = XLSX.utils.sheet_to_json(firstSheet, { header: 1 });

                    if (rows.length === 0) {
                        showToast('表格文件为空');
                        return;
                    }

                    // 1. 表头智能感知 (识别列角色，无视排列顺序)
                    var colMap = { title: -1, remark: -1, link: -1, pwd: -1, year: -1, folder: -1, season: -1, episode: -1, season_episode: -1 };
                    var firstRow = rows[0] || [];
                    var isHeaderRow = false;
                    for (var c = 0; c < firstRow.length; c++) {
                        var cellVal = String(firstRow[c] || '').trim().toLowerCase();
                        if (!cellVal) continue;
                        if (/^(?:链接|地址|下载地址|播放地址|网盘地址|网盘链接|下载|播放|url|link|ed2k|magnet)$/i.test(cellVal) || (cellVal.indexOf('链接') !== -1 || cellVal.indexOf('地址') !== -1)) {
                            if (colMap.link === -1) { colMap.link = c; isHeaderRow = true; }
                        } else if (/^(?:年份|年代|上映年份|上映年代|上映时间|上映日期|日期|year|date|release_date)$/i.test(cellVal) || (cellVal.indexOf('年份') !== -1 || cellVal.indexOf('年代') !== -1 || cellVal.indexOf('日期') !== -1)) {
                            if (colMap.year === -1) { colMap.year = c; isHeaderRow = true; }
                        } else if (/^(?:季数|季|第几季|季度|season|s)$/i.test(cellVal) || (cellVal.indexOf('季数') !== -1 || cellVal === '季')) {
                            if (colMap.season === -1) { colMap.season = c; isHeaderRow = true; }
                        } else if (/^(?:集数|集|第几集|分集|话数|episode|ep|e)$/i.test(cellVal) || (cellVal.indexOf('集数') !== -1 || cellVal === '集')) {
                            if (colMap.episode === -1) { colMap.episode = c; isHeaderRow = true; }
                        } else if (/^(?:季集|分集号|s_e)$/i.test(cellVal) || cellVal.indexOf('季集') !== -1) {
                            if (colMap.season_episode === -1) { colMap.season_episode = c; isHeaderRow = true; }
                        } else if (/^(?:所在目录|父目录|文件夹|目录|合集|folder|parent_folder|dir)$/i.test(cellVal) || (cellVal.indexOf('目录') !== -1 || cellVal.indexOf('文件夹') !== -1)) {
                            if (colMap.folder === -1) { colMap.folder = c; isHeaderRow = true; }
                        } else if (/^(?:备注|说明|版本|画质|清晰度|描述|规格|标签|简介|剧情简介|tag|tags|remark|note|notes|desc|summary)$/i.test(cellVal) || (cellVal.indexOf('备注') !== -1 || cellVal.indexOf('版本') !== -1 || cellVal.indexOf('画质') !== -1 || cellVal.indexOf('简介') !== -1 || cellVal.indexOf('描述') !== -1)) {
                            if (colMap.remark === -1) { colMap.remark = c; isHeaderRow = true; }
                        } else if (/^(?:片名|文件名|电影名|影视名|剧集名|名称|标题|影视|电影|电视剧|title|name|filename)$/i.test(cellVal) || (cellVal.indexOf('片名') !== -1 || cellVal.indexOf('文件名') !== -1 || cellVal.indexOf('名称') !== -1 || cellVal.indexOf('标题') !== -1)) {
                            if (colMap.title === -1) { colMap.title = c; isHeaderRow = true; }
                        } else if (/^(?:提取码|密码|访问码|code|pwd|password)$/i.test(cellVal) || (cellVal.indexOf('提取码') !== -1 || cellVal.indexOf('密码') !== -1)) {
                            if (colMap.pwd === -1) { colMap.pwd = c; isHeaderRow = true; }
                        }
                    }

                    var rawItems = [];
                    var startIdx = isHeaderRow ? 1 : 0;
                    // 记录上一行有效的剧集主信息，支持“剧集首行声明、后续分集片名留空自动继承”
                    var prevInheritTitle = '';
                    var prevInheritYear = '';
                    var prevInheritFolder = '';
                    var prevInheritTmdbId = 0;

                    for (var i = startIdx; i < rows.length; i++) {
                        var r = rows[i];
                        if (!r || r.length === 0) continue;

                        var cellTitle = '';
                        var cellRemark = '';
                        var cellLink = '';
                        var cellPwd = '';
                        var cellYear = '';
                        var cellFolder = '';
                        var cellSeason = '';
                        var cellEpisode = '';

                        // 若成功识别到了标准表头列映射，优先走精准按列提取
                        if (isHeaderRow && (colMap.link !== -1 || colMap.title !== -1)) {
                            if (colMap.link !== -1 && r[colMap.link] !== undefined) cellLink = String(r[colMap.link] || '').trim();
                            if (colMap.title !== -1 && r[colMap.title] !== undefined) cellTitle = String(r[colMap.title] || '').trim();
                            if (colMap.remark !== -1 && r[colMap.remark] !== undefined) cellRemark = String(r[colMap.remark] || '').trim();
                            if (colMap.pwd !== -1 && r[colMap.pwd] !== undefined) cellPwd = String(r[colMap.pwd] || '').trim();
                            if (colMap.year !== -1 && r[colMap.year] !== undefined) cellYear = String(r[colMap.year] || '').trim();
                            if (colMap.folder !== -1 && r[colMap.folder] !== undefined) cellFolder = String(r[colMap.folder] || '').trim();
                            if (colMap.season !== -1 && r[colMap.season] !== undefined) cellSeason = String(r[colMap.season] || '').trim();
                            if (colMap.episode !== -1 && r[colMap.episode] !== undefined) cellEpisode = String(r[colMap.episode] || '').trim();
                            var seIdx = colMap.seasonEpisode !== -1 ? colMap.seasonEpisode : (colMap.season_episode !== -1 ? colMap.season_episode : -1);
                            if (seIdx !== -1 && r[seIdx] !== undefined) {
                                var seVal = String(r[seIdx] || '').trim();
                                if (seVal) {
                                    var seMatch = seVal.match(/[sS](\d+)[eE](\d+)/i) || seVal.match(/第?\s*(\d+)\s*季\s*第?\s*(\d+)\s*集/i);
                                    if (seMatch) {
                                        cellSeason = seMatch[1];
                                        cellEpisode = seMatch[2];
                                    } else {
                                        var epOnly = seVal.match(/第?\s*(\d+)\s*集/i) || seVal.match(/^[eE]?(\d+)$/i);
                                        if (epOnly) cellEpisode = epOnly[1];
                                    }
                                }
                            }
                        } else {
                            // 无表头自适应启发式分支
                            var linkCellIdx = -1;
                            for (var k = 0; k < r.length; k++) {
                                var val = String(r[k] || '').trim();
                                if (isDirectOrPanLink(val)) {
                                    linkCellIdx = k;
                                    cellLink = val;
                                    break;
                                }
                            }

                            // 收集非链接列
                            var nonLinkCells = [];
                            for (var k = 0; k < r.length; k++) {
                                if (k !== linkCellIdx) {
                                    var val = String(r[k] || '').trim();
                                    if (val) nonLinkCells.push(val);
                                }
                            }

                            if (nonLinkCells.length === 0) {
                                // 单列纯链接
                            } else if (nonLinkCells.length === 1) {
                                var singleVal = nonLinkCells[0];
                                var bp = parseBracketedCell(singleVal);
                                if (bp) {
                                    // [片名][备注]
                                    cellTitle = bp.title;
                                    cellRemark = bp.remark;
                                } else if (looksLikeRemark(singleVal)) {
                                    // 纯备注 + 链接 组合
                                    cellRemark = singleVal;
                                } else {
                                    // 纯片名 + 链接
                                    cellTitle = singleVal;
                                }
                            } else if (nonLinkCells.length === 2) {
                                // 两列非链接 (如: 片名 + 备注 或 备注 + 密码)
                                var c0 = nonLinkCells[0];
                                var c1 = nonLinkCells[1];
                                if (/^[a-zA-Z0-9]{4,8}$/.test(c1) && (isPanShareLink(cellLink) || !looksLikeRemark(c1))) {
                                    // c1 可能是提取码
                                    cellPwd = c1;
                                    if (looksLikeRemark(c0)) {
                                        cellRemark = c0;
                                    } else {
                                        cellTitle = c0;
                                    }
                                } else if (looksLikeRemark(c0) && !looksLikeRemark(c1)) {
                                    cellRemark = c0;
                                    cellTitle = c1;
                                } else {
                                    cellTitle = c0;
                                    cellRemark = c1;
                                }
                            } else {
                                // 3 列及以上非链接 (片名 + 备注 + 密码)
                                cellTitle = nonLinkCells[0];
                                cellRemark = nonLinkCells[1];
                                cellPwd = nonLinkCells[2];
                            }
                        }

                        // 剧集首行声明与分集继承机制：若当前行片名为空但包含播放链接，自动向下继承上一行的主剧片名与年份！
                        if (cellTitle) {
                            var cleanCell = extractTmdbIdAndClean(cellTitle);
                            prevInheritTitle = cleanCell.title || cellTitle;
                            if (cleanCell.year) prevInheritYear = cleanCell.year;
                            else if (cellYear) prevInheritYear = cellYear;
                            if (cleanCell.tmdbId) prevInheritTmdbId = cleanCell.tmdbId;
                            if (cellFolder) prevInheritFolder = cellFolder;
                        } else if (cellLink && prevInheritTitle) {
                            cellTitle = prevInheritTitle;
                            if (!cellYear && prevInheritYear) cellYear = prevInheritYear;
                            if (!cellFolder && prevInheritFolder) cellFolder = prevInheritFolder;
                        }

                        // 统一多行单元格智能拆解与逐条展开 (支持单单元格多集剧集、多部电影合集列表)
                        var linkList = splitLinkCell(cellLink);
                        var titleList = splitCellLines(cellTitle);
                        var remarkList = splitCellLines(cellRemark);
                        var pwdList = splitCellLines(cellPwd);
                        var yearList = splitCellLines(cellYear);
                        var folderList = splitCellLines(cellFolder);
                        var seasonList = splitCellLines(cellSeason);
                        var episodeList = splitCellLines(cellEpisode);

                        var maxCount = Math.max(linkList.length, titleList.length, 1);
                        for (var k = 0; k < maxCount; k++) {
                            var currLink = (k < linkList.length) ? linkList[k] : (linkList.length === 1 ? linkList[0] : '');
                            var linkName = extractNameFromLink(currLink);
                            var currRemark = (k < remarkList.length) ? remarkList[k] : (remarkList.length === 1 ? remarkList[0] : '');
                            var currPwd = (k < pwdList.length) ? pwdList[k] : (pwdList.length === 1 ? pwdList[0] : '');
                            var currYear = (k < yearList.length) ? yearList[k] : (yearList.length === 1 ? yearList[0] : '');
                            if (currYear) {
                                var cym = currYear.match(/\b(19\d\d|20\d\d)\b/);
                                if (cym) currYear = cym[1];
                            }
                            var currFolder = (k < folderList.length) ? folderList[k] : (folderList.length === 1 ? folderList[0] : '');
                            var currSeason = (k < seasonList.length) ? seasonList[k] : (seasonList.length === 1 ? seasonList[0] : '');
                            var currEpisode = (k < episodeList.length) ? episodeList[k] : (episodeList.length === 1 ? episodeList[0] : '');

                            var currTitle = '';
                            if (titleList.length > 1 && titleList.length >= maxCount) {
                                // 1. 片名多行且行数与链接匹配：一一对应
                                currTitle = titleList[k] || '';
                            } else if (maxCount > 1 && titleList.length <= 1 && linkName) {
                                // 2. 多行剧集/合集且总标题只有1行（或无标题）：各子项优先使用链接提取出的单集具体文件名！
                                currTitle = linkName;
                            } else if (titleList.length > 0) {
                                // 3. 单行条目或无独立链接文件名：使用片名列的内容
                                currTitle = titleList[k] || titleList[0] || '';
                            } else if (linkName) {
                                // 4. 无片名列但链接有文件名
                                currTitle = linkName;
                            }

                            // 如果片名包含类似 [片名][备注说明] 的多括号结构
                            if (currTitle) {
                                var bp = parseBracketedCell(currTitle);
                                if (bp) {
                                    currTitle = bp.title;
                                    currRemark = bp.remark + (currRemark ? ' ' + currRemark : '');
                                }
                            }

                            if (!currTitle && linkName) {
                                currTitle = linkName;
                            }

                            // 核心：调用 extractTmdbIdAndClean 分离 TMDB ID、括号年份并彻底清洗片名
                            var cleanTitleObj = extractTmdbIdAndClean(currTitle);
                            var cleanLinkObj = extractTmdbIdAndClean(linkName);
                            var effectiveCleanTitle = cleanTitleObj.title || cleanLinkObj.title || currTitle || linkName;
                            var effectiveTmdbId = cleanTitleObj.tmdbId || cleanLinkObj.tmdbId || (cellTitle ? 0 : (prevInheritTmdbId || 0));
                            var effectiveYear = currYear || cleanTitleObj.year || cleanLinkObj.year || '';

                            if (effectiveCleanTitle || currLink) {
                                rawItems.push({
                                    rawFileName: effectiveCleanTitle,
                                    linkFileName: cleanLinkObj.title || linkName,
                                    explicitTitle: (colMap.title !== -1 && Boolean(cleanTitleObj.title)) ? cleanTitleObj.title : '',
                                    tmdbId: effectiveTmdbId,
                                    remark: currRemark,
                                    linkUrl: currLink,
                                    password: currPwd,
                                    year: effectiveYear,
                                    parentFolderName: currFolder,
                                    hasExplicitTitle: (colMap.title !== -1 && Boolean(currTitle)),
                                    seasonNumber: parseInt(currSeason, 10) || 0,
                                    episodeNumber: parseInt(currEpisode, 10) || 0
                                });
                            }
                        }
                    }

                    if (rawItems.length === 0) {
                        showToast('未能从表格中提取到有效数据');
                        return;
                    }

                    processRawImportItems(rawItems);
                } catch (err) {
                    showToast('解析表格异常: ' + err.message);
                }
                };
                reader.readAsArrayBuffer(file);
            }

            if (typeof XLSX === 'undefined') {
                showToast('正在加速载入 Excel 解析引擎...');
                var s = document.createElement('script');
                s.src = 'https://lib.baomitu.com/xlsx/0.18.5/xlsx.full.min.js';
                s.onload = function() { processFile(); };
                s.onerror = function() {
                    var s2 = document.createElement('script');
                    s2.src = 'https://registry.npmmirror.com/xlsx/0.18.5/files/dist/xlsx.full.min.js';
                    s2.onload = function() { processFile(); };
                    s2.onerror = function() { showToast('Excel 解析引擎加载失败，请检查网络连接'); };
                    document.head.appendChild(s2);
                };
                document.head.appendChild(s);
                return;
            }
            processFile();
        }

        // 6. 统一批量分词、网盘嗅探与 TMDB 匹配处理管线
        async function processRawImportItems(rawItems) {
            document.getElementById('importSourceSelector').style.display = 'none';
            document.getElementById('excelProgressBox').style.display = 'block';
            document.getElementById('excelProgressText').innerText = '已读取 ' + rawItems.length + ' 行数据，正在自适应展开网盘大包与提取文件特征...';

            // 第一阶段：对网盘根分享链接进行自适应平铺展开，并对缺失文件名的单链接进行按需嗅探
            var expandedItems = [];
            var expandBatchSize = 5;
            for (var exI = 0; exI < rawItems.length; exI += expandBatchSize) {
                var chunk = rawItems.slice(exI, exI + expandBatchSize);
                var chunkResults = await Promise.all(chunk.map(async function(item) {
                    // 若条目已从网盘扫描包中展开，直接保留当前项，避免重复网络调用
                    if (item.alreadyExpanded || item.isScannedFile) {
                        return [item];
                    }
                    if (!item.linkFileName && item.linkUrl) {
                        item.linkFileName = extractNameFromLink(item.linkUrl);
                    }
                    // 若为网盘分享链接且未携带具体子文件定位符 (fid)，进行自适应大包展开 (Fast Path + Deep Path)
                    if (item.linkUrl && isPanShareLink(item.linkUrl) && !hasSubFileLocator(item.linkUrl)) {
                        return await expandPanShareItem(item);
                    }
                    if (!item.rawFileName && item.linkFileName) {
                        item.rawFileName = item.linkFileName;
                        return [item];
                    }
                    if (!item.rawFileName && item.linkUrl && isPanShareLink(item.linkUrl)) {
                        var mediaInfo = await sniffPanShareMediaInfo(item.linkUrl, item.password || '');
                        if (mediaInfo) {
                            item.rawFileName = mediaInfo.fileName;
                            item.sha = mediaInfo.sha;
                            item.fileSize = mediaInfo.fileSize;
                        }
                        return [item];
                    }
                    return [item];
                }));

                for (var cri = 0; cri < chunkResults.length; cri++) {
                    var subList = chunkResults[cri];
                    if (Array.isArray(subList)) {
                        for (var sli = 0; sli < subList.length; sli++) {
                            expandedItems.push(subList[sli]);
                        }
                    }
                }
            }

            var enrichedItems = expandedItems;
            document.getElementById('excelProgressText').innerText = '正在进行智能分词与 TMDB 批量对齐...';

            // 第二阶段：分词提取片名、年份与智能提炼备注 (分批极速批量解析)
            var parseBatchSize = 100;
            var parsedItems = [];
            var totalParseChunks = Math.ceil(enrichedItems.length / parseBatchSize);

            for (var pChunkIdx = 0; pChunkIdx < totalParseChunks; pChunkIdx++) {
                var pStart = pChunkIdx * parseBatchSize;
                var pEnd = Math.min(pStart + parseBatchSize, enrichedItems.length);
                var currPChunk = enrichedItems.slice(pStart, pEnd);

                var progressEl = document.getElementById('excelProgressText');
                if (progressEl) {
                    progressEl.innerText = '正在智能分词与提取 (' + pEnd + '/' + enrichedItems.length + ')...';
                }

                var itemsToParse = currPChunk.map(function(item) {
                    var targetParseName = item.rawFileName;
                    if (!item.hasExplicitTitle && item.linkFileName && (!item.rawFileName || !/\b(19\d\d|20\d\d)\b/.test(item.rawFileName))) {
                        targetParseName = item.linkFileName;
                    }
                    var fn = targetParseName || item.rawFileName || '';
                    return {
                        fileName: fn,
                        parentFolderName: item.parentFolderName || ''
                    };
                });
                var fileNamesToParse = itemsToParse.map(function(it) { return it.fileName; });

                try {
                    var pRes = await fetch('/api/private/parse_name', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ items: itemsToParse, fileNames: fileNamesToParse })
                    });
                    var pData = await pRes.json();
                    var extResults = (pData && pData.success && Array.isArray(pData.data)) ? pData.data : [];

                    for (var pi = 0; pi < currPChunk.length; pi++) {
                        var item = currPChunk[pi];
                        var extracted = extResults[pi] || { title: item.rawFileName, year: '', alt_title: '' };
                        var globalIdx = pStart + pi;
                        var targetParseName = fileNamesToParse[pi];
                        var smartRemark = extractSmartRemark(targetParseName || item.rawFileName, item.remark);

                        var rawExtractedTitle = extracted.title || item.rawFileName;
                        if (item.hasExplicitTitle && item.explicitTitle) {
                            rawExtractedTitle = item.explicitTitle;
                        }
                        var cleanExt = extractTmdbIdAndClean(rawExtractedTitle);
                        var normTitle = normalizeChineseColon(cleanExt.title || rawExtractedTitle);
                        var finalTmdbId = item.tmdbId || cleanExt.tmdbId || extracted.tmdb_id || 0;
                        var finalYear = item.year || cleanExt.year || extracted.year || '';

                        var sNum = (extracted.has_explicit_season || (extracted.season !== undefined && extracted.season !== null && extracted.season >= 0 && extracted.episode > 0) || extracted.season > 0) ? extracted.season : -1;
                        var eNum = extracted.episode || 0;

                        // 若表格中显式指定了季数或集数（从 Excel 导入而来），优先使用表格显式指定值
                        if (item.seasonNumber > 0) sNum = item.seasonNumber;
                        if (item.episodeNumber > 0) eNum = item.episodeNumber;

                        // 智能剥离标题中遗留的“第N季 / Season N”
                        var cleanedTitleObj = cleanSeasonFromTitle(normTitle);
                        normTitle = cleanedTitleObj.title || normTitle;
                        if (sNum < 0 && cleanedTitleObj.season >= 0) {
                            sNum = cleanedTitleObj.season;
                        }
                        if (eNum > 0 && sNum < 0) sNum = 1;
                        if (sNum < 0) sNum = 0;

                        parsedItems.push({
                            key: 'row_' + globalIdx,
                            raw: item,
                            extractedTitle: normTitle,
                            extractedAltTitle: extracted.alt_title || '',
                            extractedYear: finalYear,
                            extractedRemark: item.remark || smartRemark || extracted.remark,
                            imdbId: extracted.imdb_id || '',
                            tmdbId: finalTmdbId,
                            season: sNum,
                            episode: eNum,
                            sha: item.sha || '',
                            parentFolderName: item.parentFolderName || '',
                            parentTitle: extracted.parent_title || ''
                        });
                    }
                } catch (eBatchParse) {
                    for (var pi = 0; pi < currPChunk.length; pi++) {
                        var item = currPChunk[pi];
                        var globalIdx = pStart + pi;
                        var rawFb = (item.hasExplicitTitle && item.explicitTitle) ? item.explicitTitle : item.rawFileName;
                        var cleanFb = extractTmdbIdAndClean(rawFb);
                        var fallbackTitle = normalizeChineseColon(cleanFb.title || rawFb);
                        var cleanedTitleObj = cleanSeasonFromTitle(fallbackTitle);
                        fallbackTitle = cleanedTitleObj.title || fallbackTitle;
                        var fbTmdbId = item.tmdbId || cleanFb.tmdbId || 0;
                        var fbYear = item.year || cleanFb.year || '';
                        var sNum = (item.seasonNumber > 0) ? item.seasonNumber : ((cleanedTitleObj.season >= 0) ? cleanedTitleObj.season : 0);
                        var eNum = item.episodeNumber || 0;
                        if (eNum > 0 && sNum <= 0) sNum = 1;
                        parsedItems.push({
                            key: 'row_' + globalIdx,
                            raw: item,
                            extractedTitle: fallbackTitle,
                            extractedAltTitle: '',
                            extractedYear: fbYear,
                            extractedRemark: item.remark || '',
                            imdbId: '',
                            tmdbId: fbTmdbId,
                            season: sNum,
                            episode: eNum,
                            sha: item.sha || '',
                            parentFolderName: item.parentFolderName || ''
                        });
                    }
                }
            }

            // 第三阶段：剧集预聚合（Pre-Grouping）与单次云端对齐 (整剧只提交 1 次 batch-match，结果瞬间广播给所有分集)
            var groups = {};
            var groupList = [];

            for (var pIdx = 0; pIdx < parsedItems.length; pIdx++) {
                var pItem = parsedItems[pIdx];
                var normT = (pItem.extractedTitle || '').trim().toLowerCase();
                var normY = String(pItem.extractedYear || '').trim();
                var sNum = (pItem.season !== undefined && pItem.season !== null && pItem.season >= 0) ? pItem.season : 0;
                var eNum = pItem.episode || 0;

                // 聚合桶 Key 策略
                var groupKey = '';
                if (sNum > 0 || eNum > 0) {
                    groupKey = 'series:' + normT + ':' + normY + ':s' + sNum;
                } else {
                    groupKey = 'potential:' + normT + ':' + normY;
                }

                if (!groups[groupKey]) {
                    groups[groupKey] = {
                        key: groupKey,
                        title: pItem.extractedTitle,
                        altTitle: pItem.extractedAltTitle,
                        year: pItem.extractedYear,
                        tmdbId: pItem.tmdbId || 0,
                        season: sNum,
                        items: [],
                        repItem: null,
                        matched: false,
                        conflictWarning: '',
                        suggestedVideo: null
                    };
                    groupList.push(groups[groupKey]);
                }
                if (pItem.tmdbId > 0 && !groups[groupKey].tmdbId) {
                    groups[groupKey].tmdbId = pItem.tmdbId;
                }
                groups[groupKey].items.push(pItem);
            }

            // 抽取每个 Group 的最佳代表项 (优选规则: 有 TMDB ID 且第 1 集 > 有 TMDB ID > 第 1 集且有 SHA > 第 1 集 > 有 SHA > 首个条目)
            var repItems = [];
            for (var gIdx = 0; gIdx < groupList.length; gIdx++) {
                var g = groupList[gIdx];
                var bestRep = g.items[0];
                var bestScore = -1;
                for (var bi = 0; bi < g.items.length; bi++) {
                    var it = g.items[bi];
                    var score = 0;
                    if (it.tmdbId > 0) score += 1000;
                    else if (g.tmdbId > 0) score += 500;
                    if (it.episode === 1 && it.sha) score += 200;
                    else if (it.episode === 1) score += 100;
                    else if (it.episode > 0) score += 10;
                    if (it.sha) score += 50;
                    if (score > bestScore) {
                        bestScore = score;
                        bestRep = it;
                    }
                }
                if (g.tmdbId > 0 && (!bestRep.tmdbId || bestRep.tmdbId <= 0)) {
                    bestRep.tmdbId = g.tmdbId;
                }
                g.repItem = bestRep;
                bestRep._parentGroup = g;
                repItems.push(bestRep);
            }

            var batchSize = 50;
            var matchedResults = [];
            var unmatchedResults = [];
            var chunks = [];

            for (var k = 0; k < repItems.length; k += batchSize) {
                chunks.push(repItems.slice(k, k + batchSize));
            }

            var totalChunks = chunks.length;
            for (var cIdx = 0; cIdx < totalChunks; cIdx++) {
                var currChunk = chunks[cIdx];
                var progressEl = document.getElementById('excelProgressText');
                if (progressEl) {
                    progressEl.innerText = '正在批量匹配元数据 (第 ' + (cIdx + 1) + '/' + totalChunks + ' 批，已匹配 ' + matchedResults.length + ' 条)...';
                }

                var matchPayload = {
                    items: currChunk.map(function(c) {
                        var qTitle = c.extractedTitle || '';
                        var qAlt = c.extractedAltTitle || '';
                        if (c.season > 1 && qTitle && qTitle.indexOf('季') === -1 && !/season/i.test(qTitle)) {
                            qTitle = qTitle + ' ' + formatSeasonZh(c.season);
                            if (!qAlt) qAlt = c.extractedTitle;
                        }
                        return {
                            key: c.key,
                            title: qTitle,
                            alt_title: qAlt,
                            year: c.extractedYear,
                            imdb_id: c.imdbId || '',
                            tmdb_id: c.tmdbId || (c._parentGroup && c._parentGroup.tmdbId) || 0,
                            tmdbId: c.tmdbId || (c._parentGroup && c._parentGroup.tmdbId) || 0,
                            sha: (c.sha || (c.raw && c.raw.sha) || ''),
                            file_name: (c.raw && c.raw.rawFileName) || '',
                            file_size: (c.raw && c.raw.fileSize) || 0
                        };
                    })
                };

                // 执行单批匹配 (内置自动重试 1 次)
                var chunkSuccess = false;
                for (var retry = 0; retry < 2; retry++) {
                    try {
                        var res = await fetch('/api/mv/videos/batch-match', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(matchPayload)
                        });
                        if (!res.ok) throw new Error('HTTP ' + res.status);
                        var matchData = await res.json();
                        if (!matchData.success || !matchData.data || !Array.isArray(matchData.data.results)) {
                            throw new Error(matchData.message || '批量匹配返回异常');
                        }
                        var resList = matchData.data.results;
                        for (var m = 0; m < currChunk.length; m++) {
                            var rep = currChunk[m];
                            var group = rep._parentGroup;
                            var found = null;
                            for (var n = 0; n < resList.length; n++) {
                                if (resList[n].key === rep.key) { found = resList[n]; break; }
                            }
                            var isYearConflict = false;
                            var extYearNum = parseInt(String(rep.extractedYear || ''), 10);
                            var vidYearNum = parseInt(String((found && found.video && found.video.year) || ''), 10);
                            if (!isNaN(extYearNum) && extYearNum > 1900 && !isNaN(vidYearNum) && vidYearNum > 1900) {
                                if (Math.abs(extYearNum - vidYearNum) > 1) {
                                    isYearConflict = true;
                                }
                            }

                            // 影视类型安全校验：明确为分集/剧集的，坚决禁止被匹配为电影 (TypeID=1)
                            var isTypeConflict = false;
                            var isExplicitSeries = (rep.episode > 0 || (group && group.items && group.items.some(function(it) { return it.episode > 0; })) || (group && group.items && group.items.length > 1));
                            var hasSeasonOnly = (rep.season > 0 || (group && group.season > 0));
                            var vidTypeId = (found && found.video && (found.video.typeId || found.video.type_id)) || 0;
                            if (vidTypeId === 1) {
                                if (isExplicitSeries) {
                                    isTypeConflict = true;
                                } else if (hasSeasonOnly) {
                                    isTypeConflict = false;
                                }
                            }

                            // TMDB ID 安全校验：若文件或目录显式携带了 TMDB ID，坚决禁止被匹配为不同 TMDB ID 的影片 (防错误 SHA 截胡)
                            var isTmdbConflict = false;
                            var reqTmdbId = rep.tmdbId || (group && group.tmdbId) || 0;
                            var vidTmdbId = (found && found.video && (found.video.tmdb_id || found.video.tmdbId)) || 0;
                            if (reqTmdbId > 0 && vidTmdbId > 0 && reqTmdbId !== vidTmdbId) {
                                isTmdbConflict = true;
                            }

                            if (found && found.matched && found.video && !isYearConflict && !isTypeConflict && !isTmdbConflict) {
                                // 匹配成功：广播赋予给该 Group 下的全部分集！
                                var isDowngradedMovie = (vidTypeId === 1 && !isExplicitSeries);
                                for (var gi = 0; gi < group.items.length; gi++) {
                                    var subItem = group.items[gi];
                                    matchedResults.push({
                                        key: subItem.key,
                                        raw: subItem.raw,
                                        extractedTitle: subItem.extractedTitle,
                                        extractedAltTitle: subItem.extractedAltTitle || '',
                                        extractedYear: subItem.extractedYear,
                                        extractedRemark: subItem.extractedRemark,
                                        imdbId: subItem.imdbId || '',
                                        tmdbId: subItem.tmdbId || (group && group.tmdbId) || (found.video && (found.video.tmdb_id || found.video.tmdbId)) || 0,
                                        season: isDowngradedMovie ? 0 : (subItem.season || 0),
                                        episode: isDowngradedMovie ? 0 : (subItem.episode || 0),
                                        video: found.video,
                                        matchType: found.matchType || (group.items.length > 1 ? 'series_broadcast' : ''),
                                        parentFolderName: subItem.parentFolderName || ''
                                    });
                                }
                                group.matched = true;
                            } else {
                                group.matched = false;
                                if (isTmdbConflict) {
                                    group.conflictWarning = 'TMDB ID 不一致（文件 ' + reqTmdbId + ' vs 匹配 ' + vidTmdbId + '）';
                                    group.suggestedVideo = found.video;
                                } else if (isYearConflict) {
                                    group.conflictWarning = '年份冲突（文件 ' + extYearNum + ' vs 库内 ' + vidYearNum + '）';
                                    group.suggestedVideo = found.video;
                                } else if (isTypeConflict) {
                                    group.conflictWarning = '类型冲突（剧集 vs 电影 ' + ((found.video && found.video.title) || '') + '）';
                                    group.suggestedVideo = found.video;
                                }
                            }
                        }
                        chunkSuccess = true;
                        break;
                    } catch (err) {
                        console.warn('[BatchMatch] 第 ' + (cIdx + 1) + ' 批尝试 ' + (retry + 1) + ' 失败:', err);
                        if (retry === 0) {
                            await new Promise(function(resolve) { setTimeout(resolve, 500); });
                        }
                    }
                }

                if (!chunkSuccess) {
                    for (var fi = 0; fi < currChunk.length; fi++) {
                        var fRep = currChunk[fi];
                        if (fRep._parentGroup) fRep._parentGroup.matched = false;
                    }
                }
            }

            // 第三点五阶段：对第一轮未命中 Group 发起以 AltTitle / 去空格片名 / 父目录备选片名为查询词的第二轮批量对齐
            var pass2Groups = [];
            for (var gi = 0; gi < groupList.length; gi++) {
                var g = groupList[gi];
                if (g.matched) continue;
                var rep = g.repItem;
                var altQuery = rep.extractedAltTitle;
                if (!altQuery && rep.season > 1 && rep.extractedTitle && rep.extractedTitle.indexOf('季') === -1) {
                    altQuery = rep.extractedTitle;
                }
                if (!altQuery && rep.extractedTitle && /[\u4e00-\u9fa5]/.test(rep.extractedTitle) && /\d+/.test(rep.extractedTitle)) {
                    var noSp = rep.extractedTitle.replace(/\s+/g, '');
                    if (noSp !== rep.extractedTitle) {
                        altQuery = noSp;
                    }
                }
                if (altQuery && altQuery.trim().length > 1) {
                    pass2Groups.push({ group: g, query: altQuery.trim(), matchType: 'alt_title' });
                } else if (rep.parentTitle && rep.parentTitle.trim().length > 1 && rep.parentTitle.trim() !== rep.extractedTitle) {
                    pass2Groups.push({ group: g, query: rep.parentTitle.trim(), matchType: 'parent_folder' });
                }
            }

            if (pass2Groups.length > 0) {
                var pass2Chunks = [];
                for (var p2k = 0; p2k < pass2Groups.length; p2k += batchSize) {
                    pass2Chunks.push(pass2Groups.slice(p2k, p2k + batchSize));
                }
                var p2Total = pass2Chunks.length;
                for (var p2Idx = 0; p2Idx < p2Total; p2Idx++) {
                    var currP2Chunk = pass2Chunks[p2Idx];
                    var p2ProgressEl = document.getElementById('excelProgressText');
                    if (p2ProgressEl) {
                        p2ProgressEl.innerText = '正在执行副标题二次精准对齐 (第 ' + (p2Idx + 1) + '/' + p2Total + ' 批，已匹配 ' + matchedResults.length + ' 条)...';
                    }
                    var p2Payload = {
                        items: currP2Chunk.map(function(c) {
                            return {
                                key: c.group.repItem.key,
                                title: c.query,
                                year: c.group.repItem.extractedYear,
                                imdb_id: c.group.repItem.imdbId || '',
                                tmdb_id: c.group.repItem.tmdbId || (c.group && c.group.tmdbId) || 0,
                                tmdbId: c.group.repItem.tmdbId || (c.group && c.group.tmdbId) || 0,
                                sha: '', // 二轮备选检索强制清空 SHA，杜绝 SHA 劫持
                                file_name: (c.group.repItem.raw && c.group.repItem.raw.rawFileName) || '',
                                file_size: (c.group.repItem.raw && c.group.repItem.raw.fileSize) || 0
                            };
                        })
                    };
                    try {
                        var p2Res = await fetch('/api/mv/videos/batch-match', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(p2Payload)
                        });
                        if (p2Res.ok) {
                            var p2Data = await p2Res.json();
                            if (p2Data.success && p2Data.data && Array.isArray(p2Data.data.results)) {
                                var p2List = p2Data.data.results;
                                for (var p2m = 0; p2m < currP2Chunk.length; p2m++) {
                                    var cand = currP2Chunk[p2m];
                                    var p2Found = null;
                                    for (var p2n = 0; p2n < p2List.length; p2n++) {
                                        if (p2List[p2n].key === cand.group.repItem.key) { p2Found = p2List[p2n]; break; }
                                    }
                                    if (p2Found && p2Found.matched && p2Found.video) {
                                        var isYearConf = false;
                                        var extY = parseInt(String(cand.group.repItem.extractedYear || ''), 10);
                                        var vidY = parseInt(String(p2Found.video.year || ''), 10);
                                        if (!isNaN(extY) && extY > 1900 && !isNaN(vidY) && vidY > 1900) {
                                            if (Math.abs(extY - vidY) > 1) {
                                                isYearConf = true;
                                            }
                                        }

                                        // 影视类型安全校验：剧集分集决不能被匹配为单片电影 (TypeID=1)
                                        var isTypeConf = false;
                                        var isExplicitSeriesP2 = ((cand.group.repItem && cand.group.repItem.episode > 0) || (cand.group.items && cand.group.items.some(function(it) { return it.episode > 0; })) || (cand.group.items && cand.group.items.length > 1));
                                        var hasSeasonOnlyP2 = (cand.group.season > 0 || (cand.group.repItem && cand.group.repItem.season > 0));
                                        var p2VidTypeId = (p2Found.video && (p2Found.video.typeId || p2Found.video.type_id)) || 0;
                                        if (p2VidTypeId === 1) {
                                            if (isExplicitSeriesP2) {
                                                isTypeConf = true;
                                            } else if (hasSeasonOnlyP2) {
                                                isTypeConf = false;
                                            }
                                        }

                                        // TMDB ID 安全校验：防错误 SHA 截胡
                                        var isTmdbConf = false;
                                        var reqTmdbIdP2 = (cand.group.repItem && cand.group.repItem.tmdbId) || cand.group.tmdbId || 0;
                                        var vidTmdbIdP2 = (p2Found.video && (p2Found.video.tmdb_id || p2Found.video.tmdbId)) || 0;
                                        if (reqTmdbIdP2 > 0 && vidTmdbIdP2 > 0 && reqTmdbIdP2 !== vidTmdbIdP2) {
                                            isTmdbConf = true;
                                        }

                                        if (!isYearConf && !isTypeConf && !isTmdbConf) {
                                            // 二轮匹配成功：广播给该 Group 下的全部分集！
                                            var isDowngradedMovieP2 = (p2VidTypeId === 1 && !isExplicitSeriesP2);
                                            for (var gi = 0; gi < cand.group.items.length; gi++) {
                                                var subItem = cand.group.items[gi];
                                                matchedResults.push({
                                                    key: subItem.key,
                                                    raw: subItem.raw,
                                                    extractedTitle: subItem.extractedTitle,
                                                    extractedAltTitle: subItem.extractedAltTitle || '',
                                                    extractedYear: subItem.extractedYear,
                                                    extractedRemark: subItem.extractedRemark,
                                                    imdbId: subItem.imdbId || '',
                                                    tmdbId: subItem.tmdbId || (cand.group && cand.group.tmdbId) || (p2Found.video && (p2Found.video.tmdb_id || p2Found.video.tmdbId)) || 0,
                                                    season: isDowngradedMovieP2 ? 0 : (subItem.season || 0),
                                                    episode: isDowngradedMovieP2 ? 0 : (subItem.episode || 0),
                                                    video: p2Found.video,
                                                    matchType: p2Found.matchType || 'alt_title',
                                                    parentFolderName: subItem.parentFolderName || ''
                                                });
                                            }
                                            cand.group.matched = true;
                                        } else {
                                            if (isTmdbConf) {
                                                cand.group.conflictWarning = 'TMDB ID 不一致（文件 ' + reqTmdbIdP2 + ' vs 匹配 ' + vidTmdbIdP2 + '）';
                                                cand.group.suggestedVideo = p2Found.video;
                                            } else if (isTypeConf) {
                                                cand.group.conflictWarning = '类型冲突（剧集 vs 电影 ' + ((p2Found.video && p2Found.video.title) || '') + '）';
                                                cand.group.suggestedVideo = p2Found.video;
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    } catch (eP2) {
                        console.warn('[BatchMatch] 二次对齐异常:', eP2);
                    }
                }
            }

            // 第三点六阶段：对仍未命中的 Group，若带有有效 tmdbId，通过 /api/mv/videos/search?tmdbId= 执行精准直达检索
            var tmdbPendingGroups = [];
            for (var gi = 0; gi < groupList.length; gi++) {
                var g = groupList[gi];
                if (!g.matched && ((g.repItem && g.repItem.tmdbId > 0) || (g.tmdbId && g.tmdbId > 0))) {
                    tmdbPendingGroups.push(g);
                }
            }
            if (tmdbPendingGroups.length > 0) {
                for (var tgIdx = 0; tgIdx < tmdbPendingGroups.length; tgIdx++) {
                    var tg = tmdbPendingGroups[tgIdx];
                    var tid = (tg.repItem && tg.repItem.tmdbId > 0) ? tg.repItem.tmdbId : tg.tmdbId;
                    try {
                        var tRes = await fetch('/api/mv/videos/search?tmdbId=' + tid);
                        if (tRes.ok) {
                            var tData = await tRes.json();
                            var tItems = (tData && tData.data && Array.isArray(tData.data.items)) ? tData.data.items : [];
                            if (tItems.length > 0) {
                                var pickVideo = tItems[0];
                                if (tg.season > 0) {
                                    for (var ti = 0; ti < tItems.length; ti++) {
                                        var sc = cleanSeasonFromTitle(tItems[ti].title || '');
                                        if (sc.season === tg.season) {
                                            pickVideo = tItems[ti];
                                            break;
                                        }
                                    }
                                }
                                for (var sgi = 0; sgi < tg.items.length; sgi++) {
                                    var subItem = tg.items[sgi];
                                    matchedResults.push({
                                        key: subItem.key,
                                        raw: subItem.raw,
                                        extractedTitle: subItem.extractedTitle,
                                        extractedAltTitle: subItem.extractedAltTitle || '',
                                        extractedYear: subItem.extractedYear,
                                        extractedRemark: subItem.extractedRemark,
                                        imdbId: subItem.imdbId || '',
                                        tmdbId: tid,
                                        season: subItem.season || 0,
                                        episode: subItem.episode || 0,
                                        video: pickVideo,
                                        matchType: 'tmdb_direct',
                                        parentFolderName: subItem.parentFolderName || ''
                                    });
                                }
                                tg.matched = true;
                            }
                        }
                    } catch (eTid) {
                        console.warn('[BatchMatch] tmdbId direct search error:', eTid);
                    }
                }
            }

            // （这个会影响速度，暂时停用）第三点七阶段：对仍未命中的 Group，自动尝试通过本地 TMDB 官方 API（fetchTmdbSearch）进行智能对齐兜底
            // var unconfirmedGroups = [];
            // for (var gi = 0; gi < groupList.length; gi++) {
            //     var g = groupList[gi];
            //     if (!g.matched && g.repItem) {
            //         var sT = (g.repItem.extractedTitle || g.title || '').trim();
            //         if (sT && !isWeakSeriesTitle(sT) && sT.length > 1) {
            //             unconfirmedGroups.push(g);
            //         }
            //     }
            // }

            // if (unconfirmedGroups.length > 0) {
            //     var progressEl = document.getElementById('excelProgressText');
            //     if (progressEl) {
            //         progressEl.innerText = '正在通过官方 TMDB 引擎进行智能兜底对齐...';
            //     }
            //     for (var ugIdx = 0; ugIdx < unconfirmedGroups.length; ugIdx++) {
            //         var ug = unconfirmedGroups[ugIdx];
            //         var qTitle = (ug.repItem.extractedTitle || ug.title || '').trim();
            //         var qYear = (ug.repItem.extractedYear || ug.year || '').trim();
            //         var isSeriesGrp = (ug.season > 0 || (ug.repItem && (ug.repItem.season > 0 || ug.repItem.episode > 0)) || (ug.items && ug.items.some(function(it) { return (it.season > 0 || it.episode > 0); })));

            //         try {
            //             var tmdbList = await fetchTmdbSearch(qTitle, qYear);
            //             if (tmdbList && tmdbList.length > 0) {
            //                 // 优先匹配相同类型 (剧集优先匹配 tv，电影优先匹配 movie)
            //                 var pick = tmdbList[0];
            //                 for (var c = 0; c < tmdbList.length; c++) {
            //                     var candItem = tmdbList[c];
            //                     if (isSeriesGrp && candItem.media_type === 'tv') {
            //                         pick = candItem;
            //                         break;
            //                     } else if (!isSeriesGrp && candItem.media_type === 'movie') {
            //                         pick = candItem;
            //                         break;
            //                     }
            //                 }

            //                 var candTitle = pick.title || pick.name || pick.original_title || '';
            //                 var cleanedTarget = cleanSeasonFromTitle(candTitle);
            //                 var cleanTitle = cleanedTarget.title || candTitle;
            //                 var targetTypeId = isSeriesGrp ? 2 : ((pick.media_type === 'tv') ? 2 : 1);
            //                 var pickYear = pick.release_date ? pick.release_date.split('-')[0] : (pick.first_air_date ? pick.first_air_date.split('-')[0] : qYear);
            //                 var picUrl = pick.poster_path ? ('https://image.tmdb.org/t/p/w500' + pick.poster_path) : '';
            //                 var bdUrl = pick.backdrop_path ? ('https://image.tmdb.org/t/p/original' + pick.backdrop_path) : '';

            //                 var targetVideo = {
            //                     id: pick.id,
            //                     title: cleanTitle,
            //                     originalTitle: pick.original_title || pick.original_name || '',
            //                     pic: picUrl,
            //                     backdropPath: bdUrl,
            //                     year: String(pickYear || ''),
            //                     typeId: targetTypeId,
            //                     director: '',
            //                     starring: '',
            //                     bianju: '',
            //                     tags: [],
            //                     area: '',
            //                     language: '',
            //                     stime: '',
            //                     times: '',
            //                     alias: [],
            //                     content: pick.overview || '',
            //                     remark: pick.vote_average ? ('评分 ' + pick.vote_average.toFixed(1)) : '',
            //                     tmdbId: pick.id
            //                 };

            //                 for (var sgi = 0; sgi < ug.items.length; sgi++) {
            //                     var subItem = ug.items[sgi];
            //                     matchedResults.push({
            //                         key: subItem.key,
            //                         raw: subItem.raw,
            //                         extractedTitle: targetVideo.title,
            //                         extractedAltTitle: subItem.extractedAltTitle || '',
            //                         extractedYear: targetVideo.year,
            //                         extractedRemark: subItem.extractedRemark,
            //                         imdbId: subItem.imdbId || '',
            //                         tmdbId: pick.id,
            //                         season: subItem.season || 0,
            //                         episode: subItem.episode || 0,
            //                         video: targetVideo,
            //                         matchType: 'tmdb_auto_fallback',
            //                         parentFolderName: subItem.parentFolderName || ''
            //                     });
            //                 }
            //                 ug.matched = true;
            //             }
            //         } catch (eAutoTmdb) {
            //             console.warn('[BatchMatch] TMDB auto fallback search error for ' + qTitle + ':', eAutoTmdb);
            //         }
            //     }
            // }

            // 将所有仍未命中的 Group 中的条目放入 unmatchedResults
            for (var gi = 0; gi < groupList.length; gi++) {
                var g = groupList[gi];
                if (!g.matched) {
                    for (var ii = 0; ii < g.items.length; ii++) {
                        var it = g.items[ii];
                        if (g.conflictWarning) {
                            it.conflictWarning = g.conflictWarning;
                            it.suggestedVideo = g.suggestedVideo;
                        }
                        unmatchedResults.push(it);
                    }
                }
            }

            state.excelMatched = matchedResults;
            state.excelUnmatched = unmatchedResults;

            document.getElementById('excelProgressBox').style.display = 'none';
            document.getElementById('excelTabsBox').style.display = 'flex';
            document.getElementById('btnReUploadExcel').style.display = 'inline-flex';
            var box = document.getElementById('excelModalBox');
            if (box) box.classList.add('modal-fullscreen');

            try {
                renderExcelMatchedTable();
            } catch (eM) {
                console.error('[BatchMatch] renderExcelMatchedTable error:', eM);
            }
            try {
                renderExcelUnmatched();
            } catch (eU) {
                console.error('[BatchMatch] renderExcelUnmatched error:', eU);
            }

            // 默认显示规则：若有未匹配项则默认显示未匹配tab并将数量标红，否则默认显示已匹配tab
            try {
                updateExcelTabCounts();
            } catch (eT) {
                console.error('[BatchMatch] updateExcelTabCounts error:', eT);
            }

            if (matchedResults.length > 0) {
                var btnConfirm = document.getElementById('btnConfirmBatchImport');
                if (btnConfirm) btnConfirm.style.display = 'inline-flex';
                var lblUpdateMode = document.getElementById('lblExcelUpdateMode');
                if (lblUpdateMode) lblUpdateMode.style.display = 'inline-flex';
                var lblSkipSha = document.getElementById('lblExcelSkipShaDedup');
                if (lblSkipSha) {
                    lblSkipSha.style.display = 'inline-flex';
                    var chkSkipSha = document.getElementById('chkExcelSkipShaDedup');
                    if (chkSkipSha && state.skipShaDedup) chkSkipSha.checked = true;
                }
            }
        }

        function updateExcelTabCounts(preferredTab) {
            var matchedLen = state.excelMatched.length;
            var unmatchedLen = state.excelUnmatched.length;

            var matchedCountEl = document.getElementById('matchedCount');
            var unmatchedCountEl = document.getElementById('unmatchedCount');

            if (matchedCountEl) matchedCountEl.innerText = matchedLen;
            if (unmatchedCountEl) {
                unmatchedCountEl.innerText = unmatchedLen;
                if (unmatchedLen > 0) {
                    unmatchedCountEl.style.color = '#ef4444';
                    unmatchedCountEl.style.fontWeight = '700';
                } else {
                    unmatchedCountEl.style.color = '';
                    unmatchedCountEl.style.fontWeight = '';
                }
            }

            var unmatchedTbCountEl = document.getElementById('unmatchedToolbarCount');
            if (unmatchedTbCountEl) unmatchedTbCountEl.innerText = unmatchedLen;

            var footerExportBtn = document.getElementById('btnExportUnmatchedFooter');
            var footerExportCount = document.getElementById('unmatchedFooterCount');
            if (footerExportBtn) {
                if (unmatchedLen > 0) {
                    footerExportBtn.style.display = 'inline-flex';
                    if (footerExportCount) footerExportCount.innerText = unmatchedLen;
                } else {
                    footerExportBtn.style.display = 'none';
                }
            }

            var btnConfirm = document.getElementById('btnConfirmBatchImport');
            var lblUpdateMode = document.getElementById('lblExcelUpdateMode');
            var lblSkipSha = document.getElementById('lblExcelSkipShaDedup');
            if (matchedLen > 0) {
                if (btnConfirm) btnConfirm.style.display = 'inline-flex';
                if (lblUpdateMode) lblUpdateMode.style.display = 'inline-flex';
                if (lblSkipSha) {
                    lblSkipSha.style.display = 'inline-flex';
                    var chkSkipSha = document.getElementById('chkExcelSkipShaDedup');
                    if (chkSkipSha && state.skipShaDedup) chkSkipSha.checked = true;
                }
            } else {
                if (btnConfirm) btnConfirm.style.display = 'none';
                if (lblUpdateMode) lblUpdateMode.style.display = 'none';
                if (lblSkipSha) lblSkipSha.style.display = 'none';
            }

            var targetTab = preferredTab;
            if (!targetTab) {
                targetTab = (matchedLen > 0) ? 'matched' : 'unmatched';
            }
            switchExcelTab(targetTab);
        }

        function switchExcelTab(tab) {
            if (tab === 'matched') {
                document.getElementById('tabMatched').classList.add('active');
                document.getElementById('tabUnmatched').classList.remove('active');
                document.getElementById('panelMatched').style.display = 'block';
                document.getElementById('panelUnmatched').style.display = 'none';
            } else {
                document.getElementById('tabUnmatched').classList.add('active');
                document.getElementById('tabMatched').classList.remove('active');
                document.getElementById('panelUnmatched').style.display = 'block';
                document.getElementById('panelMatched').style.display = 'none';
                renderExcelUnmatched();
            }
        }

        function openImagePreview(imgUrl, title) {
            if (!imgUrl) return;
            var img = document.getElementById('previewModalImg');
            var titleEl = document.getElementById('previewModalTitle');
            if (img) img.src = imgUrl;
            if (titleEl) titleEl.innerText = title || '';
            openModal('imagePreviewModal');
        }

        function closeImagePreview(e) {
            if (e.target.id === 'imagePreviewModal') {
                closeModal('imagePreviewModal');
            }
        }

        function showFullFileName(fileName, title) {
            var titleEl = document.getElementById('fullFileNameTitle');
            var textEl = document.getElementById('fullFileNameText');
            if (titleEl) titleEl.innerText = title || '📄 完整原文件名';
            if (textEl) {
                textEl.innerText = fileName || '-';
                textEl.setAttribute('data-content', fileName || '');
            }
            openModal('fullFileNameModal');
        }

        function showFullFileNameMatched(idx) {
            var item = state.excelMatched[idx];
            var name = (item && item.raw && item.raw.rawFileName) || '-';
            showFullFileName(name, '📄 完整原文件名 (已匹配项 #' + (idx + 1) + ')');
        }

        function showFullFileNameUnmatched(idx) {
            var item = state.excelUnmatched[idx];
            var name = (item && item.raw && item.raw.rawFileName) || '-';
            showFullFileName(name, '📄 完整原文件名 (待确认项 #' + (idx + 1) + ')');
        }

        function copyFullFileName() {
            var textEl = document.getElementById('fullFileNameText');
            var content = textEl ? (textEl.getAttribute('data-content') || textEl.innerText) : '';
            if (!content || content === '-') return;
            copyToClipboard(content, '已复制完整文件名到剪贴板！');
        }

        function renderExcelMatchedTable() {
            var tbody = document.querySelector('#matchedTable tbody');
            var html = '';
            for (var i = 0; i < state.excelMatched.length; i++) {
                var item = state.excelMatched[i];
                var rawLink = (item.raw && item.raw.linkUrl) || '-';
                var rawName = (item.raw && item.raw.rawFileName) || '-';
                var folderName = (item.raw && item.raw.parentFolderName) || item.parentFolderName || '';
                var folderBadge = folderName ? ('<div style="font-size:11px;color:#94a3b8;margin-top:2px;display:flex;align-items:center;gap:4px;" title="所在父目录: ' + folderName.replace(/"/g, '&quot;') + '"><span style="opacity:0.7;">📁</span> ' + folderName + '</div>') : '';
                var v = item.video || {};
                var picUrl = v.pic || '';
                var movieTitle = (v.title || '').replace(/'/g, "\\'") + (v.year ? ' (' + v.year + ')' : '');

                html += '<tr><td class="poster-cell">';
                if (picUrl) {
                    html += '<img referrerpolicy="no-referrer" src="' + picUrl + '" class="import-poster-thumb" title="点击查看高清大图" onclick="openImagePreview(\'' + picUrl.replace(/'/g, "\\'") + '\', \'' + movieTitle + '\')">';
                } else {
                    html += '<div style="width:52px;height:74px;background:#1e293b;border-radius:6px;display:flex;align-items:center;justify-content:center;font-size:20px;margin:0 auto;">🎬</div>';
                }
                html += '</td>';
                html += '<td class="raw-filename-cell" title="点击查看完整文件名&#10;' + rawName.replace(/"/g, '&quot;') + '" onclick="showFullFileNameMatched(' + i + ')">' + rawName + folderBadge + '</td>';
                var seBadge = '';
                if ((item.season !== undefined && item.season !== null && item.season >= 0 && item.episode > 0) || item.season > 0 || item.episode > 0) {
                    var sP = (item.season !== undefined && item.season !== null && item.season >= 0) ? item.season : 1;
                    var eP = (item.episode > 0 ? item.episode : 1);
                    seBadge = '<span style="font-size:11px;padding:1px 5px;border-radius:4px;background:rgba(56,189,248,0.2);color:#38bdf8;border:1px solid rgba(56,189,248,0.4);margin-right:6px;font-weight:700;">S' + (sP < 10 ? '0' + sP : sP) + 'E' + (eP < 10 ? '0' + eP : eP) + '</span>';
                }
                var matchBadge = '';
                if (item.matchType === 'tmdb_auto') {
                    matchBadge = '<span style="font-size:10px;padding:1px 5px;border-radius:3px;background:rgba(168,85,247,0.2);color:#c084fc;border:1px solid rgba(168,85,247,0.4);margin-left:6px;font-weight:600;" title="云端自动从 TMDB 刮削并收录入库">TMDB收录</span>';
                } else if (item.matchType === 'sha') {
                    matchBadge = '<span style="font-size:10px;padding:1px 5px;border-radius:3px;background:rgba(16,185,129,0.2);color:#34d399;border:1px solid rgba(16,185,129,0.4);margin-left:6px;font-weight:600;" title="基于文件 SHA 指纹秒级精准命中">SHA精准</span>';
                }
                html += '<td style="font-weight:600;color:#fff;">' + seBadge + (v.title || '-') + matchBadge + '</td>';
                html += '<td style="text-align:center;">' + (v.year || '-') + '</td>';
                html += '<td style="color:#a5b4fc;font-weight:500;">' + (item.extractedRemark || '-') + '</td>';
                html += '<td class="link-cell">' + rawLink + '</td></tr>';
            }
            tbody.innerHTML = html;
        }

        function exportUnmatchedToExcel() {
            if (!state.excelUnmatched || state.excelUnmatched.length === 0) {
                showToast('当前没有待确认的条目可导出');
                return;
            }

            function doExport() {
                var rawList = [];
                for (var i = 0; i < state.excelUnmatched.length; i++) {
                    var item = state.excelUnmatched[i];
                    var titleInput = document.getElementById('unmatch_title_' + i);
                    var yearInput = document.getElementById('unmatch_year_' + i);

                    var currentTitle = (titleInput ? titleInput.value.trim() : '') || item.extractedTitle || '';
                    var currentYear = (yearInput ? yearInput.value.trim() : '') || item.extractedYear || '';
                    var rawLink = (item.raw && item.raw.linkUrl) || '';
                    var rawPwd = (item.raw && item.raw.password) || '';
                    var rawRemark = item.extractedRemark || (item.raw && item.raw.remark) || '';
                    var rawFileName = (item.raw && item.raw.rawFileName) || '';
                    var parentFolder = (item.raw && item.raw.parentFolderName) || item.parentFolderName || '';
                    var reason = item.conflictWarning || (item.extractedTitle ? '未命中TMDB' : '未提取到有效片名');

                    var sVal = (item.season !== undefined && item.season !== null && item.season > 0) ? item.season : '';
                    var eVal = (item.episode !== undefined && item.episode !== null && item.episode > 0) ? item.episode : '';
                    if (!sVal && !eVal && rawFileName) {
                        var seM = rawFileName.match(/[sS](\d+)[eE](\d+)/i) || rawFileName.match(/第?\s*(\d+)\s*季\s*第?\s*(\d+)\s*集/i);
                        if (seM) {
                            sVal = parseInt(seM[1], 10) || 1;
                            eVal = parseInt(seM[2], 10) || 1;
                        } else {
                            var epM = rawFileName.match(/(?:[eE]|第|\b)(\d{1,3})(?:集|\b|\.mp4|\.mkv)/i);
                            if (epM) {
                                eVal = parseInt(epM[1], 10) || 1;
                                sVal = 1;
                            }
                        }
                    }

                    var meaningfulFolder = resolveMeaningfulSeriesFolder(parentFolder);
                    var effectiveTitle = !isWeakSeriesTitle(currentTitle) ? currentTitle : (meaningfulFolder || '');

                    var groupKey = '';
                    if (!isWeakSeriesTitle(effectiveTitle)) {
                        groupKey = 'title:' + effectiveTitle.toLowerCase() + (currentYear ? ('_' + currentYear) : '');
                    } else {
                        groupKey = 'single:' + (item.fileId || rawLink || ('idx_' + i));
                    }

                    rawList.push({
                        title: effectiveTitle || currentTitle,
                        year: currentYear,
                        season: sVal,
                        episode: eVal,
                        link: rawLink,
                        pwd: rawPwd,
                        remark: rawRemark,
                        rawFileName: rawFileName,
                        parentFolder: parentFolder,
                        reason: reason,
                        groupKey: groupKey
                    });
                }

                // 剧集聚合分组：同剧分集归类排列，首行输出片名/年份，后续分集留空自动继承
                var groups = {};
                var groupOrder = [];
                for (var g = 0; g < rawList.length; g++) {
                    var itm = rawList[g];
                    if (!groups[itm.groupKey]) {
                        groups[itm.groupKey] = [];
                        groupOrder.push(itm.groupKey);
                    }
                    groups[itm.groupKey].push(itm);
                }

                var rows = [];
                for (var go = 0; go < groupOrder.length; go++) {
                    var gItems = groups[groupOrder[go]];
                    // 组内若有分集号按季数与集数升序排列
                    gItems.sort(function(a, b) {
                        var aSea = parseInt(a.season, 10) || 1;
                        var bSea = parseInt(b.season, 10) || 1;
                        if (aSea !== bSea) return aSea - bSea;
                        var aEp = parseInt(a.episode, 10) || 0;
                        var bEp = parseInt(b.episode, 10) || 0;
                        return aEp - bEp;
                    });

                    for (var gi = 0; gi < gItems.length; gi++) {
                        var it = gItems[gi];
                        var isFirstInGroup = (gi === 0);
                        rows.push({
                            '片名': isFirstInGroup ? (it.title || it.rawFileName) : '',
                            '年份': isFirstInGroup ? it.year : '',
                            '季数': it.season,
                            '集数': it.episode,
                            '播放链接': it.link,
                            '提取码': it.pwd,
                            '备注': it.remark,
                            '原文件名': it.rawFileName,
                            '所在目录': it.parentFolder,
                            '待确认原因': it.reason
                        });
                    }
                }

                try {
                    var ws = XLSX.utils.json_to_sheet(rows, {
                        header: ['片名', '年份', '季数', '集数', '播放链接', '提取码', '备注', '原文件名', '所在目录', '待确认原因']
                    });

                    // 友好列宽设置
                    ws['!cols'] = [
                        { wch: 22 }, // 片名
                        { wch: 8 },  // 年份
                        { wch: 8 },  // 季数
                        { wch: 8 },  // 集数
                        { wch: 50 }, // 播放链接
                        { wch: 10 }, // 提取码
                        { wch: 18 }, // 备注
                        { wch: 35 }, // 原文件名
                        { wch: 22 }, // 所在目录
                        { wch: 22 }  // 待确认原因
                    ];

                    var wb = XLSX.utils.book_new();
                    XLSX.utils.book_append_sheet(wb, ws, '待确认影片列表');

                    var libName = (state.currentLib && state.currentLib.name) ? state.currentLib.name.replace(/[/\\?%*:|"<>]/g, '_') : '媒体库';
                    var now = new Date();
                    var pad = function(n) { return n < 10 ? '0' + n : n; };
                    var ts = now.getFullYear() + '' + pad(now.getMonth() + 1) + '' + pad(now.getDate()) + '_' + pad(now.getHours()) + '' + pad(now.getMinutes());
                    var fileName = '待确认影片列表_' + libName + '_' + ts + '.xlsx';

                    XLSX.writeFile(wb, fileName);
                    showToast('已成功导出 ' + rows.length + ' 条待确认条目（已按剧集聚合：同剧分集只需在首行修改片名/年份，重新导入时自动继承）！');
                } catch (e) {
                    console.error('[exportUnmatchedToExcel] error:', e);
                    showToast('导出 Excel 失败: ' + e.message);
                }
            }

            if (typeof XLSX === 'undefined' || !XLSX.utils || !XLSX.writeFile) {
                showToast('正在加载 Excel 导出组件...');
                var s = document.createElement('script');
                s.src = 'https://lib.baomitu.com/xlsx/0.18.5/xlsx.full.min.js';
                s.onload = function() { doExport(); };
                s.onerror = function() {
                    var s2 = document.createElement('script');
                    s2.src = 'https://registry.npmmirror.com/xlsx/0.18.5/files/dist/xlsx.full.min.js';
                    s2.onload = function() { doExport(); };
                    s2.onerror = function() { showToast('加载 Excel 组件失败，请检查网络'); };
                    document.head.appendChild(s2);
                };
                document.head.appendChild(s);
            } else {
                doExport();
            }
        }

        function switchExcelUnmatchedView(mode) {
            state.excelUnmatchedViewMode = mode;
            var btnSeries = document.getElementById('btnExcelViewSeries');
            var btnFlat = document.getElementById('btnExcelViewFlat');
            var seriesView = document.getElementById('excelUnmatchedSeriesView');
            var tableView = document.getElementById('excelUnmatchedTableView');

            if (mode === 'series') {
                if (btnSeries) {
                    btnSeries.style.background = 'rgba(99,102,241,0.25)';
                    btnSeries.style.color = '#fff';
                    btnSeries.style.borderColor = 'rgba(99,102,241,0.4)';
                }
                if (btnFlat) {
                    btnFlat.style.background = 'transparent';
                    btnFlat.style.color = 'var(--text-muted)';
                    btnFlat.style.borderColor = 'transparent';
                }
                if (seriesView) seriesView.style.display = 'flex';
                if (tableView) tableView.style.display = 'none';
                renderExcelUnmatchedSeriesCards();
            } else {
                if (btnFlat) {
                    btnFlat.style.background = 'rgba(99,102,241,0.25)';
                    btnFlat.style.color = '#fff';
                    btnFlat.style.borderColor = 'rgba(99,102,241,0.4)';
                }
                if (btnSeries) {
                    btnSeries.style.background = 'transparent';
                    btnSeries.style.color = 'var(--text-muted)';
                    btnSeries.style.borderColor = 'transparent';
                }
                if (seriesView) seriesView.style.display = 'none';
                if (tableView) tableView.style.display = 'block';
                renderExcelUnmatchedTable();
            }
        }

        function renderExcelUnmatched() {
            var items = state.excelUnmatched || [];
            var toolbarCount = document.getElementById('unmatchedToolbarCount');
            if (toolbarCount) toolbarCount.innerText = items.length;

            renderExcelUnmatchedSeriesCards();
            renderExcelUnmatchedTable();

            var mode = state.excelUnmatchedViewMode || 'series';
            var seriesView = document.getElementById('excelUnmatchedSeriesView');
            var tableView = document.getElementById('excelUnmatchedTableView');
            if (mode === 'series') {
                if (seriesView) seriesView.style.display = 'flex';
                if (tableView) tableView.style.display = 'none';
            } else {
                if (seriesView) seriesView.style.display = 'none';
                if (tableView) tableView.style.display = 'block';
            }
        }

        function detectGroupMediaType(grp) {
            if (!grp || !grp.items || grp.items.length === 0) return 'movie';
            var items = grp.items;

            // 检查组内是否有条目具备明确的季集特征
            var hasAnyEpisodeFeature = false;
            for (var i = 0; i < items.length; i++) {
                var it = items[i];
                var rawN = (it.raw && it.raw.rawFileName) || it.rawFileName || '';
                var pFolder = it.parentFolderName || (it.raw && it.raw.parentFolderName) || '';

                var sNum = (it.season !== undefined && it.season !== null) ? it.season : 0;
                var eNum = (it.episode !== undefined && it.episode !== null) ? it.episode : 0;
                if (eNum > 0 || sNum > 0) {
                    hasAnyEpisodeFeature = true;
                    break;
                }

                var hasSePattern = /[sS](\d+)[eE](\d+)/i.test(rawN) || 
                                   /第?\s*(\d+)\s*季\s*第?\s*(\d+)\s*集/i.test(rawN) || 
                                   /(?:[eE]|第|\b)(\d{1,3})(?:集|\.mp4|\.mkv|\.ts|\.avi)/i.test(rawN) ||
                                   /[第\s](\d+)[话期回]/i.test(rawN) ||
                                   /season\s*\d+/i.test(pFolder) ||
                                   /^s\d+$/i.test(pFolder.trim());
                if (hasSePattern) {
                    hasAnyEpisodeFeature = true;
                    break;
                }
            }

            if (items.length > 1) {
                return hasAnyEpisodeFeature ? 'tv' : 'movie';
            }

            return hasAnyEpisodeFeature ? 'tv_single' : 'movie';
        }

        function getGroupMetaDisplay(grp) {
            var mediaType = detectGroupMediaType(grp);
            var it0 = (grp && grp.items && grp.items[0]) || {};
            var epNum = it0.episode || 1;
            var total = (grp && grp.items) ? grp.items.length : 0;

            if (mediaType === 'movie') {
                var isMulti = total > 1;
                return {
                    mediaType: 'movie',
                    icon: '🎬',
                    badge: isMulti 
                        ? ('<span style="background:rgba(168,85,247,0.15);color:#c084fc;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:700;border:1px solid rgba(168,85,247,0.3);">电影 (' + total + '个播放源待确认)</span>')
                        : '<span style="background:rgba(168,85,247,0.15);color:#c084fc;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:700;border:1px solid rgba(168,85,247,0.3);">单部电影待确认</span>',
                    bindBtnText: isMulti ? ('🔍 绑定此电影 (' + total + '源)') : '🔍 绑定此电影',
                    bindBtnTitle: '搜索 TMDB 绑定此电影并入库',
                    removeBtnText: isMulti ? '🗑️ 移除此电影(所有源)' : '🗑️ 移除此电影',
                    removeBtnTitle: '从待确认列表移除此电影',
                    colHeader: '规格/类型',
                    itemBadge: '<span style="background:rgba(168,85,247,0.15);color:#c084fc;padding:1px 5px;border-radius:4px;font-size:11px;font-weight:700;">电影正片</span>',
                    candHint: '点击选定绑定此电影 ✓',
                    confirmModalBtn: '✓ 选定并绑定此电影',
                    deleteConfirm: '确定要从待确认列表中移除电影【' + ((grp && grp.title) || '此电影') + '】吗？',
                    successToast: function(title, cnt) { return '🎉 已成功绑定电影《' + title + '》并移入已匹配列表！'; }
                };
            } else if (mediaType === 'tv_single') {
                return {
                    mediaType: 'tv_single',
                    icon: '📺',
                    badge: '<span style="background:rgba(56,189,248,0.15);color:#38bdf8;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:700;border:1px solid rgba(56,189,248,0.3);">剧集 (第' + epNum + '集待确认)</span>',
                    bindBtnText: '🔍 绑定此剧集 (第' + epNum + '集)',
                    bindBtnTitle: '搜索 TMDB 绑定此剧集分集入库',
                    removeBtnText: '🗑️ 移除此分集',
                    removeBtnTitle: '从待确认列表移除此分集',
                    colHeader: '分集',
                    itemBadge: '<span style="background:rgba(56,189,248,0.15);color:#38bdf8;padding:1px 5px;border-radius:4px;font-size:11px;font-weight:700;">S' + (it0.season || 1) + 'E' + epNum + '</span>',
                    candHint: '点击选定绑定此分集 ✓',
                    confirmModalBtn: '✓ 选定并绑定此分集',
                    deleteConfirm: '确定要从待确认列表中移除剧集【' + ((grp && grp.title) || '此剧集') + '】的该分集吗？',
                    successToast: function(title, cnt) { return '🎉 已成功绑定《' + title + '》分集并移入已匹配列表！'; }
                };
            } else {
                return {
                    mediaType: 'tv',
                    icon: '📁',
                    badge: '<span style="background:rgba(56,189,248,0.15);color:#38bdf8;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:700;border:1px solid rgba(56,189,248,0.3);">共 ' + total + ' 集待确认</span>',
                    bindBtnText: '🔍 一键绑定整部剧 (' + total + '集)',
                    bindBtnTitle: '搜索 TMDB 一键将整部剧 ' + total + ' 个分集批量入库',
                    removeBtnText: '🗑️ 移除整剧',
                    removeBtnTitle: '从待确认列表移除整部剧的所有分集',
                    colHeader: '分集',
                    itemBadge: '',
                    candHint: '点击选定一键入库整部剧 ✓',
                    confirmModalBtn: '✓ 选定并绑定整部剧',
                    deleteConfirm: '确定要从待确认列表中移除【' + ((grp && grp.title) || '此剧集') + '】的全部 ' + total + ' 个分集吗？',
                    successToast: function(title, cnt) { return '🎉 已成功将《' + title + '》共 ' + cnt + ' 个分集批量移入已匹配列表！'; }
                };
            }
        }

        function renderExcelUnmatchedSeriesCards() {
            var container = document.getElementById('excelUnmatchedSeriesView');
            if (!container) return;
            var items = state.excelUnmatched || [];
            if (items.length === 0) {
                container.innerHTML = '<div style="text-align:center;padding:30px;color:var(--text-muted);font-size:13px;">🎉 太棒了，当前没有待确认的条目！</div>';
                return;
            }

            // 1. 聚类分组 (优先同剧名，其次有意义剧名目录，再次单文件)
            var groups = {};
            var groupOrder = [];
            for (var i = 0; i < items.length; i++) {
                var it = items[i];
                var pFolder = it.parentFolderName || (it.raw && it.raw.parentFolderName) || '';
                var rawT = (it.extractedTitle || '').trim();
                var cleanT = extractTmdbIdAndClean(rawT);
                rawT = cleanT.title || rawT;
                var rawY = (it.extractedYear || cleanT.year || '').trim();
                var meaningfulFolder = resolveMeaningfulSeriesFolder(pFolder);
                var effectiveTitle = !isWeakSeriesTitle(rawT) ? rawT : (meaningfulFolder || '');

                var key = '';
                if (!isWeakSeriesTitle(effectiveTitle)) {
                    key = 'title:' + effectiveTitle.toLowerCase() + (rawY ? ('_' + rawY) : '');
                } else {
                    key = 'single:' + (it.key || it.fileId || ('idx_' + i));
                }

                if (!groups[key]) {
                    groups[key] = {
                        key: key,
                        dir: pFolder,
                        title: effectiveTitle,
                        year: rawY,
                        tmdbId: it.tmdbId || cleanT.tmdbId || 0,
                        items: []
                    };
                    groupOrder.push(key);
                }
                if (it.tmdbId > 0 && !groups[key].tmdbId) {
                    groups[key].tmdbId = it.tmdbId;
                }
                groups[key].items.push(it);
                if (!groups[key].title && effectiveTitle) groups[key].title = effectiveTitle;
                if (!groups[key].year && rawY) groups[key].year = rawY;
            }

            // 排序：组内各分集按季数、集数升序自然排列
            for (var k in groups) {
                groups[k].items.sort(function(a, b) {
                    var sa = a.season || 1;
                    var sb = b.season || 1;
                    if (sa !== sb) return sa - sb;
                    return (a.episode || 1) - (b.episode || 1);
                });
            }
            state.excelUnmatchedSeriesGroups = groups;

            var html = '';
            for (var g = 0; g < groupOrder.length; g++) {
                var grpKey = groupOrder[g];
                var grp = groups[grpKey];
                var meta = getGroupMetaDisplay(grp);
                var totalEpisodes = grp.items.length;
                var displayTitle = grp.title || resolveMeaningfulSeriesFolder(grp.dir) || '未命名影视';
                var displayYear = grp.year ? (' (' + grp.year + ')') : '';
                var folderBadge = grp.dir ? ('<span style="font-size:11px;color:#94a3b8;margin-left:4px;" title="目录: ' + grp.dir.replace(/"/g, '&quot;') + '">📁 ' + grp.dir + '</span>') : '';

                html += '<div class="unm-series-card" id="excel_unm_grp_card_' + g + '" style="background:rgba(15,23,42,0.65);border:1px solid rgba(255,255,255,0.08);border-radius:8px;padding:12px 16px;display:flex;flex-direction:column;gap:8px;transition:all 0.2s ease;">';
                html += '  <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;">';
                html += '    <div style="display:flex;align-items:center;gap:8px;flex:1;min-width:240px;flex-wrap:wrap;">';
                html += '      <span style="font-size:18px;">' + meta.icon + '</span>';
                html += '      <div style="font-size:14px;font-weight:700;color:#fff;">' + displayTitle + '<span style="font-size:12px;color:var(--text-muted);font-weight:normal;margin-left:4px;">' + displayYear + '</span></div>';
                html +=        meta.badge;
                html +=        folderBadge;
                html += '    </div>';
                html += '    <div style="display:flex;align-items:center;gap:8px;">';
                html += '      <button class="btn btn-secondary" style="padding:4px 10px;font-size:12px;background:rgba(99,102,241,0.2);color:#a5b4fc;border:1px solid rgba(99,102,241,0.4);" onclick="openExcelSeriesBindInline(' + g + ')" title="' + meta.bindBtnTitle + '">' + meta.bindBtnText + '</button>';
                html += '      <button class="btn btn-secondary" id="btnToggleExcelGrp_' + g + '" style="padding:4px 8px;font-size:12px;" onclick="toggleExcelSeriesDetail(' + g + ')">展开明细 ▾</button>';
                html += '      <button class="btn btn-outline" style="padding:4px 8px;font-size:12px;color:#f87171;border-color:rgba(239,68,68,0.3);" onclick="deleteExcelSeriesGroup(' + g + ')" title="' + meta.removeBtnTitle + '">' + meta.removeBtnText + '</button>';
                html += '    </div>';
                html += '  </div>';

                // 搜索展开区
                html += '  <div id="excel_unm_grp_search_' + g + '" style="display:none;background:rgba(30,41,59,0.85);border-radius:6px;padding:12px 14px;border:1px solid rgba(99,102,241,0.25);margin-top:4px;">';
                html += '    <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;flex-wrap:wrap;">';
                html += '      <span style="font-size:12px;color:#a5b4fc;font-weight:600;">检索影视:</span>';
                html += '      <input type="text" class="form-input" id="excel_unm_grp_title_input_' + g + '" value="' + displayTitle.replace(/"/g, '&quot;') + '" placeholder="片名" style="width:160px;height:28px;font-size:12px;padding:2px 8px;" onkeydown="if(event.key===\'Enter\')searchExcelSeriesTmdb(' + g + ')">';
                html += '      <input type="text" class="form-input" id="excel_unm_grp_year_input_' + g + '" value="' + (grp.year || '').replace(/"/g, '&quot;') + '" placeholder="年份" style="width:60px;height:28px;font-size:12px;padding:2px 8px;text-align:center;" onkeydown="if(event.key===\'Enter\')searchExcelSeriesTmdb(' + g + ')">';
                html += '      <button class="btn btn-secondary" style="padding:3px 10px;font-size:12px;" onclick="searchExcelSeriesTmdb(' + g + ')">检索 🔍</button>';
                html += '      <button class="btn btn-outline" style="padding:3px 8px;font-size:11px;margin-left:auto;" onclick="document.getElementById(\'excel_unm_grp_search_' + g + '\').style.display=\'none\'">收起 ✕</button>';
                html += '    </div>';
                html += '    <div id="excel_unm_grp_candidates_' + g + '"></div>';
                html += '  </div>';

                // 明细展开区 (表格)
                html += '  <div id="excel_unm_grp_detail_' + g + '" style="display:none;background:rgba(15,23,42,0.4);border-radius:6px;padding:8px;border:1px solid rgba(255,255,255,0.04);margin-top:4px;overflow-x:auto;">';
                html += '    <table style="width:100%;border-collapse:collapse;font-size:12px;">';
                html += '      <thead><tr style="color:var(--text-muted);border-bottom:1px solid rgba(255,255,255,0.08);"><th style="padding:6px 8px;text-align:left;">' + meta.colHeader + '</th><th style="padding:6px 8px;text-align:left;">原文件名</th><th style="padding:6px 8px;text-align:left;">播放链接</th><th style="padding:6px 8px;text-align:center;width:60px;">操作</th></tr></thead>';
                html += '      <tbody>';
                for (var gi = 0; gi < grp.items.length; gi++) {
                    var itm = grp.items[gi];
                    var rawN = (itm.raw && itm.raw.rawFileName) || itm.rawFileName || '-';
                    var rawL = (itm.raw && itm.raw.linkUrl) || itm.linkUrl || '-';
                    var seBadge = '';
                    if (meta.mediaType === 'movie') {
                        var remarkTxt = itm.extractedRemark || (itm.raw && itm.raw.remark) || '电影正片';
                        seBadge = '<span style="background:rgba(168,85,247,0.15);color:#c084fc;padding:1px 5px;border-radius:4px;font-size:11px;font-weight:700;">' + remarkTxt + '</span>';
                    } else {
                        seBadge = '<span style="background:rgba(56,189,248,0.15);color:#38bdf8;padding:1px 5px;border-radius:4px;font-size:11px;font-weight:700;">S' + (itm.season || 1) + 'E' + (itm.episode || 1) + '</span>';
                    }
                    html += '<tr style="border-bottom:1px solid rgba(255,255,255,0.04);">';
                    html += '  <td style="padding:6px 8px;white-space:nowrap;">' + seBadge + '</td>';
                    html += '  <td style="padding:6px 8px;color:#fff;max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="' + rawN.replace(/"/g, '&quot;') + '">' + rawN + '</td>';
                    html += '  <td style="padding:6px 8px;color:#64748b;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="' + rawL.replace(/"/g, '&quot;') + '">' + rawL + '</td>';
                    html += '  <td style="padding:6px 8px;text-align:center;"><button class="icon-btn" style="color:#f87171;font-size:12px;padding:2px 4px;" onclick="deleteSingleExcelUnmatchedItem(\'' + (itm.key || ('row_' + gi)) + '\')" title="从待确认移除">🗑️</button></td>';
                    html += '</tr>';
                }
                html += '      </tbody>';
                html += '    </table>';
                html += '  </div>';

                html += '</div>';
            }
            container.innerHTML = html;
        }

        function openExcelSeriesBindInline(grpIdx) {
            var box = document.getElementById('excel_unm_grp_search_' + grpIdx);
            if (!box) return;
            box.style.display = 'block';
            searchExcelSeriesTmdb(grpIdx);
        }

        function toggleExcelSeriesDetail(grpIdx) {
            var box = document.getElementById('excel_unm_grp_detail_' + grpIdx);
            var btn = document.getElementById('btnToggleExcelGrp_' + grpIdx);
            if (!box) return;
            if (box.style.display === 'none') {
                box.style.display = 'block';
                if (btn) btn.innerText = '收起明细 ▴';
            } else {
                box.style.display = 'none';
                if (btn) btn.innerText = '展开明细 ▾';
            }
        }

        function deleteExcelSeriesGroup(grpIdx) {
            var grpKeys = Object.keys(state.excelUnmatchedSeriesGroups || {});
            var grpKey = grpKeys[grpIdx];
            var grp = state.excelUnmatchedSeriesGroups[grpKey];
            if (!grp || !grp.items || grp.items.length === 0) return;
            var meta = getGroupMetaDisplay(grp);
            if (!confirm(meta.deleteConfirm)) return;

            var removeKeys = grp.items.map(function(it) { return it.key; });
            state.excelUnmatched = state.excelUnmatched.filter(function(it) {
                return removeKeys.indexOf(it.key) === -1;
            });

            var toastMsg = (meta.mediaType === 'movie') ? '已移除该电影' : ((meta.mediaType === 'tv_single') ? '已移除该分集' : ('已移除该剧集的 ' + grp.items.length + ' 个分集'));
            showToast(toastMsg);
            renderExcelUnmatched();
            updateExcelTabCounts();
        }

        function deleteSingleExcelUnmatchedItem(key) {
            state.excelUnmatched = state.excelUnmatched.filter(function(it) {
                return it.key !== key;
            });
            showToast('已移除该分集');
            renderExcelUnmatched();
            updateExcelTabCounts();
        }

        function openExcelSeriesCandidatePreview(grpIdx, candIdx) {
            var candList = state.excelUnmatchedSeriesCandidatesMap && state.excelUnmatchedSeriesCandidatesMap[grpIdx];
            if (!candList || !candList[candIdx]) return;
            var cand = candList[candIdx];
            var grpKeys = Object.keys(state.excelUnmatchedSeriesGroups || {});
            var grpKey = grpKeys[grpIdx];
            var grp = state.excelUnmatchedSeriesGroups[grpKey];
            var meta = getGroupMetaDisplay(grp);

            openTmdbPreviewModal(grpIdx, cand, true, function() {
                resolveExcelSeriesWithCandidate(grpIdx, candIdx);
            });

            var btnConfirm = document.getElementById('btnConfirmTmdbBind');
            if (btnConfirm) {
                btnConfirm.innerText = meta.confirmModalBtn || '✓ 选定并绑定';
            }
        }

        function searchExcelSeriesTmdb(grpIdx) {
            var titleInput = document.getElementById('excel_unm_grp_title_input_' + grpIdx);
            var yearInput = document.getElementById('excel_unm_grp_year_input_' + grpIdx);
            var candBox = document.getElementById('excel_unm_grp_candidates_' + grpIdx);
            if (!titleInput || !candBox) return;

            var title = titleInput.value.trim();
            var year = yearInput ? yearInput.value.trim() : '';
            var cleanT = extractTmdbIdAndClean(title);
            if (cleanT.title && cleanT.title !== title) {
                title = cleanT.title;
                titleInput.value = title;
            }
            if (!year && cleanT.year) {
                year = cleanT.year;
                if (yearInput) yearInput.value = year;
            }
            if (!title && !cleanT.tmdbId) {
                candBox.innerHTML = '<div style="font-size:12px;color:#f87171;">请输入片名后再搜索</div>';
                return;
            }

            var grpKeys = Object.keys(state.excelUnmatchedSeriesGroups || {});
            var grpKey = grpKeys[grpIdx];
            var grp = state.excelUnmatchedSeriesGroups[grpKey];
            var queryArg = (cleanT.tmdbId > 0) ? String(cleanT.tmdbId) : ((grp && grp.tmdbId > 0) ? String(grp.tmdbId) : title);

            candBox.innerHTML = '<div style="display:flex;align-items:center;gap:10px;font-size:12px;color:#a5b4fc;"><div class="loading-spinner" style="width:16px;height:16px;border-width:2px;"></div> 正在 TMDB 中检索【' + title + (year ? ' (' + year + ')' : '') + '】...</div>';

            fetchTmdbSearch(queryArg, year)
                .then(function(results) {
                    if (!results || results.length === 0) {
                        candBox.innerHTML = '<div style="font-size:12px;color:#94a3b8;padding:8px 0;">未在 TMDB 检索到相关影视条目，建议修改片名重新检索</div>';
                        return;
                    }
                    var candList = [];
                    var grpKeys = Object.keys(state.excelUnmatchedSeriesGroups || {});
                    var grpKey = grpKeys[grpIdx];
                    var grp = state.excelUnmatchedSeriesGroups[grpKey];
                    var meta = getGroupMetaDisplay(grp);

                    var cHtml = '<div style="display:grid;grid-template-columns:repeat(auto-fill, minmax(260px, 1fr));gap:8px;margin-top:8px;">';
                    for (var c = 0; c < Math.min(results.length, 6); c++) {
                        var v = results[c];
                        var vTitle = v.title || v.name || v.original_title || '';
                        var vOrig = v.original_title || v.original_name || '';
                        var vYear = v.release_date ? v.release_date.split('-')[0] : (v.first_air_date ? v.first_air_date.split('-')[0] : '');
                        var vPic = v.poster_path ? ('https://image.tmdb.org/t/p/w500' + v.poster_path) : '';
                        var vBackdrop = v.backdrop_path ? ('https://image.tmdb.org/t/p/original' + v.backdrop_path) : '';
                        var vRating = v.vote_average ? v.vote_average.toFixed(1) : '';
                        var isTV = (v.media_type === 'tv');

                        candList.push({
                            id: v.id,
                            tmdbId: v.id,
                            title: vTitle,
                            originalTitle: vOrig,
                            pic: vPic,
                            backdropPath: vBackdrop,
                            year: vYear,
                            media_type: v.media_type,
                            typeId: isTV ? 2 : 1,
                            overview: v.overview || '',
                            remark: vRating ? '评分 ' + vRating : ''
                        });

                        var typeLabel = isTV ? '<span class="badge" style="background:#0284c7;color:#fff;font-size:10px;padding:1px 5px;border-radius:3px;margin-right:4px;">剧集</span>' : '<span class="badge" style="background:#7c3aed;color:#fff;font-size:10px;padding:1px 5px;border-radius:3px;margin-right:4px;">电影</span>';

                        cHtml += '<div class="unm-cand-card" style="position:relative;display:flex;gap:10px;padding:8px;background:rgba(15,23,42,0.8);border:1px solid rgba(255,255,255,0.08);border-radius:6px;cursor:pointer;align-items:center;" onclick="resolveExcelSeriesWithCandidate(' + grpIdx + ', ' + c + ')">';
                        
                        // 右上角【🔍 详情】按钮
                        cHtml += '  <button type="button" class="btn btn-secondary" style="position:absolute;top:6px;right:6px;padding:2px 6px;font-size:11px;background:rgba(99,102,241,0.25);color:#a5b4fc;border:1px solid rgba(99,102,241,0.4);border-radius:4px;z-index:2;" onclick="event.stopPropagation(); openExcelSeriesCandidatePreview(' + grpIdx + ', ' + c + ');" title="点击查看 TMDB 详细剧情、演职员表与高清海报">🔍 详情</button>';

                        if (vPic) {
                            cHtml += '<img src="' + vPic + '" style="width:38px;height:54px;object-fit:cover;border-radius:4px;flex-shrink:0;cursor:pointer;" title="点击查看详情" onclick="event.stopPropagation(); openExcelSeriesCandidatePreview(' + grpIdx + ', ' + c + ');">';
                        } else {
                            cHtml += '<div style="width:38px;height:54px;background:#1e293b;border-radius:4px;flex-shrink:0;display:flex;align-items:center;justify-content:center;cursor:pointer;" title="点击查看详情" onclick="event.stopPropagation(); openExcelSeriesCandidatePreview(' + grpIdx + ', ' + c + ');">🎬</div>';
                        }
                        cHtml += '<div style="overflow:hidden;flex:1;min-width:0;padding-right:48px;">';
                        cHtml += '  <div style="font-size:13px;font-weight:700;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="' + vTitle.replace(/"/g, '&quot;') + '">' + vTitle + '</div>';
                        cHtml += '  <div style="font-size:11px;color:var(--text-muted);margin-top:2px;">' + typeLabel + (vYear ? vYear + ' 年' : '') + (vRating ? ' · ★ ' + vRating : '') + '</div>';
                        cHtml += '  <div style="font-size:11px;color:#38bdf8;margin-top:3px;font-weight:500;">' + meta.candHint + '</div>';
                        cHtml += '</div></div>';
                    }
                    cHtml += '</div>';
                    state.excelUnmatchedSeriesCandidatesMap = state.excelUnmatchedSeriesCandidatesMap || {};
                    state.excelUnmatchedSeriesCandidatesMap[grpIdx] = candList;
                    candBox.innerHTML = cHtml;
                })
                .catch(function(e) {
                    candBox.innerHTML = '<div style="font-size:12px;color:#f87171;">检索异常: ' + e.message + '</div>';
                });
        }

        function resolveExcelSeriesWithCandidate(grpIdx, candIdx) {
            var candList = state.excelUnmatchedSeriesCandidatesMap && state.excelUnmatchedSeriesCandidatesMap[grpIdx];
            if (!candList || !candList[candIdx]) return;

            var grpKeys = Object.keys(state.excelUnmatchedSeriesGroups || {});
            var grpKey = grpKeys[grpIdx];
            var grp = state.excelUnmatchedSeriesGroups[grpKey];
            if (!grp || !grp.items || grp.items.length === 0) return;

            var meta = getGroupMetaDisplay(grp);
            var cand = candList[candIdx];
            var cleanedTarget = cleanSeasonFromTitle(cand.title);
            var cleanTitle = cleanedTarget.title || cand.title;
            var isMovie = (meta.mediaType === 'movie') || (cand.typeId === 1 && meta.mediaType !== 'tv');
            var targetTypeId = isMovie ? 1 : ((cleanedTarget.season >= 0) ? 2 : (cand.typeId || 2));

            var targetVideo = {
                id: cand.tmdbId || cand.id || 0,
                title: cleanTitle,
                originalTitle: cand.originalTitle || '',
                pic: cand.pic || '',
                backdropPath: cand.backdropPath || '',
                year: String(cand.year || ''),
                typeId: targetTypeId,
                director: cand.director || '',
                starring: cand.starring || '',
                bianju: '',
                tags: [],
                area: '',
                language: '',
                stime: '',
                times: '',
                alias: [],
                content: cand.overview || '',
                remark: cand.remark || '',
                tmdbId: cand.tmdbId || cand.id || 0
            };

            for (var i = 0; i < grp.items.length; i++) {
                var it = grp.items[i];
                var targetSeason = null;
                var targetEpisode = null;
                if (!isMovie) {
                    targetSeason = (it.season !== undefined && it.season !== null && it.season >= 0) ? it.season : ((cleanedTarget.season >= 0) ? cleanedTarget.season : 1);
                    targetEpisode = it.episode || 1;
                }
                state.excelMatched.push({
                    key: it.key || ('matched_' + Math.random().toString(36).substr(2, 9)),
                    raw: it.raw,
                    extractedTitle: targetVideo.title,
                    extractedYear: targetVideo.year,
                    extractedRemark: it.extractedRemark,
                    season: targetSeason,
                    episode: targetEpisode,
                    video: targetVideo,
                    parentFolderName: it.parentFolderName || (it.raw && it.raw.parentFolderName) || '',
                    matchType: 'manual'
                });
            }

            var removeKeys = grp.items.map(function(it) { return it.key; });
            state.excelUnmatched = state.excelUnmatched.filter(function(it) {
                return removeKeys.indexOf(it.key) === -1;
            });

            showToast(meta.successToast(targetVideo.title, grp.items.length));
            renderExcelMatchedTable();
            renderExcelUnmatched();

            var btnConfirm = document.getElementById('btnConfirmBatchImport');
            if (btnConfirm) btnConfirm.style.display = 'inline-flex';

            var nextTab = (state.excelUnmatched.length === 0) ? 'matched' : 'unmatched';
            updateExcelTabCounts(nextTab);
            if (nextTab === 'matched') {
                switchExcelTab('matched');
            }
        }

        function renderExcelUnmatchedTable() {
            var tbody = document.querySelector('#unmatchedTable tbody');
            if (!tbody) return;
            var html = '';
            for (var i = 0; i < state.excelUnmatched.length; i++) {
                var item = state.excelUnmatched[i];
                var itemKey = item.key || ('row_' + i);
                var rawLink = (item.raw && item.raw.linkUrl) || item.linkUrl || '-';
                var rawName = (item.raw && item.raw.rawFileName) || item.rawFileName || '-';
                var folderName = (item.raw && item.raw.parentFolderName) || item.parentFolderName || '';
                var folderBadge = folderName ? ('<div style="font-size:11px;color:#94a3b8;margin-top:2px;display:flex;align-items:center;gap:4px;" title="所在父目录: ' + folderName.replace(/"/g, '&quot;') + '"><span style="opacity:0.7;">📁</span> ' + folderName + '</div>') : '';
                var warnHtml = item.conflictWarning ? ('<div style="font-size:11px;color:#f87171;margin-top:2px;line-height:1.3;display:flex;align-items:center;gap:3px;" title="该文件提取的年份与云端候选年份差距较大，为防止张冠李戴已自动拦截并转入待确认">⚠️ ' + item.conflictWarning + '</div>') : '';
                var seBadge = (item.season > 0 || item.episode > 0) ? ('<span style="display:inline-block;background:rgba(56,189,248,0.15);color:#38bdf8;padding:1px 5px;border-radius:4px;font-size:11px;margin-left:4px;">S' + (item.season || 1) + 'E' + (item.episode || 1) + '</span>') : '';
                var isChecked = state.excelUnmatchedSelectedKeys.indexOf(itemKey) !== -1;

                html += '<tr id="unmatch_row_' + i + '">';
                html += '<td style="text-align:center;"><input type="checkbox" class="excel-unm-chk" value="' + itemKey + '" ' + (isChecked ? 'checked' : '') + ' onchange="handleExcelUnmatchedRowCheck(this)"></td>';
                html += '<td class="raw-filename-cell" title="点击查看完整文件名&#10;' + rawName.replace(/"/g, '&quot;') + '" onclick="showFullFileNameUnmatched(' + i + ')">' + rawName + folderBadge + '</td>';
                var cleanUnmTitle = extractTmdbIdAndClean(item.extractedTitle || '').title || item.extractedTitle || '';
                html += '<td><input type="text" class="form-input" style="padding:4px 8px;font-size:12px;width:160px;" value="' + cleanUnmTitle.replace(/"/g, '&quot;') + '" id="unmatch_title_' + i + '" oninput="if(state.excelUnmatched[' + i + ']) state.excelUnmatched[' + i + '].extractedTitle=this.value" onkeydown="if(event.key===\'Enter\') inlineSearchUnmatched(' + i + ')">' + warnHtml + '</td>';
                html += '<td style="text-align:center;"><input type="text" class="form-input" style="padding:4px 8px;font-size:12px;width:60px;text-align:center;" value="' + (item.extractedYear || '').replace(/"/g, '&quot;') + '" id="unmatch_year_' + i + '" oninput="if(state.excelUnmatched[' + i + ']) state.excelUnmatched[' + i + '].extractedYear=this.value"></td>';
                html += '<td style="text-align:center;"><div style="display:flex;gap:5px;justify-content:center;align-items:center;">' +
                    '<button class="btn btn-secondary" style="padding:4px 8px;font-size:11px;white-space:nowrap;" onclick="inlineSearchUnmatched(' + i + ')">🔍 搜索绑定</button>' +
                    '<button class="btn btn-outline" style="padding:4px 8px;font-size:11px;white-space:nowrap;border-color:rgba(16,185,129,0.4);color:#6ee7b7;" onclick="openCustomMovieModal(' + i + ')" title="无需刮削，自由命名作为自建/花絮影片独立入库">➕ 自建入库</button>' +
                    '</div></td>';
                html += '<td style="color:#a5b4fc;font-size:12px;">' + (item.extractedRemark || '-') + seBadge + '</td>';
                html += '<td class="link-cell">' + rawLink + '</td></tr>';
                html += '<tr id="unmatch_expand_' + i + '" style="display:none;"><td colspan="7" style="background:rgba(15,23,42,0.6);padding:10px 16px;"><div id="unmatch_candidates_' + i + '" style="display:flex;flex-direction:column;gap:8px;"></div></td></tr>';
            }
            tbody.innerHTML = html;
        }

        function toggleExcelUnmatchedSelectAll(cb) {
            var chks = document.querySelectorAll('.excel-unm-chk');
            state.excelUnmatchedSelectedKeys = [];
            for (var i = 0; i < chks.length; i++) {
                chks[i].checked = cb.checked;
                if (cb.checked) {
                    state.excelUnmatchedSelectedKeys.push(chks[i].value);
                }
            }
            updateExcelUnmatchedBatchBtns();
        }

        function handleExcelUnmatchedRowCheck(cb) {
            var val = cb.value;
            var idx = state.excelUnmatchedSelectedKeys.indexOf(val);
            if (cb.checked) {
                if (idx === -1) state.excelUnmatchedSelectedKeys.push(val);
            } else {
                if (idx !== -1) state.excelUnmatchedSelectedKeys.splice(idx, 1);
            }
            var allChks = document.querySelectorAll('.excel-unm-chk');
            var selectAll = document.getElementById('excelUnmatchedSelectAll');
            if (selectAll) {
                selectAll.checked = (allChks.length > 0 && state.excelUnmatchedSelectedKeys.length === allChks.length);
            }
            updateExcelUnmatchedBatchBtns();
        }

        function updateExcelUnmatchedBatchBtns() {
            var count = state.excelUnmatchedSelectedKeys.length;
            var btnBind = document.getElementById('btnExcelBatchBind');
            var btnDel = document.getElementById('btnExcelBatchDelete');
            var cntBind = document.getElementById('excelBatchBindCount');
            var cntDel = document.getElementById('excelBatchDeleteCount');
            if (cntBind) cntBind.innerText = count;
            if (cntDel) cntDel.innerText = count;
            if (count > 0) {
                if (btnBind) btnBind.style.display = 'inline-flex';
                if (btnDel) btnDel.style.display = 'inline-flex';
            } else {
                if (btnBind) btnBind.style.display = 'none';
                if (btnDel) btnDel.style.display = 'none';
            }
        }

        // ================= 全局通用批量绑定功能 (支持片名+年份精准检索，多候选结果自主选定) =================
        var batchBindState = {
            mode: 'excel', // 'excel' | 'unmatched_queue'
            keys: [],
            ids: [],
            count: 0,
            candidates: [],
            onConfirm: null
        };

        function openUniversalBatchBindModal(options) {
            options = options || {};
            batchBindState.mode = options.mode || 'excel';
            batchBindState.keys = (options.keys || []).slice();
            batchBindState.ids = (options.ids || []).slice();
            batchBindState.count = options.count || (batchBindState.mode === 'excel' ? batchBindState.keys.length : batchBindState.ids.length);
            batchBindState.candidates = [];
            batchBindState.onConfirm = options.onConfirm || null;

            var cntEl = document.getElementById('batchBindSelectedCount');
            if (cntEl) cntEl.innerText = batchBindState.count;

            var titleInput = document.getElementById('batchBindTitleInput');
            var yearInput = document.getElementById('batchBindYearInput');
            var statsEl = document.getElementById('batchBindResultStats');
            var candBox = document.getElementById('batchBindCandidatesBox');

            if (statsEl) statsEl.innerText = '';
            if (titleInput) titleInput.value = options.defaultTitle || '';
            if (yearInput) yearInput.value = options.defaultYear || '';

            if (candBox) {
                candBox.innerHTML = '<div style="text-align:center;padding:40px 0;color:var(--text-muted);font-size:13px;">请输入影视片名并点击“检索 TMDB”以查找匹配候选</div>';
            }

            openModal('batchBindModal');

            if (options.defaultTitle && options.defaultTitle.trim()) {
                executeBatchBindSearch();
            } else if (titleInput) {
                setTimeout(function() { titleInput.focus(); }, 100);
            }
        }

        function executeBatchBindSearch() {
            var titleInput = document.getElementById('batchBindTitleInput');
            var yearInput = document.getElementById('batchBindYearInput');
            var candBox = document.getElementById('batchBindCandidatesBox');
            var statsEl = document.getElementById('batchBindResultStats');
            if (!titleInput || !candBox) return;

            var rawTitle = titleInput.value.trim();
            var rawYear = (yearInput ? yearInput.value.trim() : '');

            var cleanObj = extractTmdbIdAndClean(rawTitle);
            var cleanTitle = cleanObj.title || rawTitle;
            cleanTitle = normalizeChineseColon(cleanTitle);
            if (titleInput) titleInput.value = cleanTitle;

            if (!rawYear && cleanObj.year) {
                rawYear = cleanObj.year;
                if (yearInput) yearInput.value = rawYear;
            }

            var tmdbId = cleanObj.tmdbId || 0;
            if (!cleanTitle && tmdbId <= 0) {
                candBox.innerHTML = '<div style="text-align:center;padding:40px 0;color:#f87171;font-size:13px;">⚠️ 请输入有效的影视片名或 TMDB ID 后再进行检索</div>';
                return;
            }

            var queryArg = (tmdbId > 0) ? String(tmdbId) : cleanTitle;
            candBox.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;gap:10px;padding:45px 0;color:#a5b4fc;font-size:13px;">' +
                '<div class="loading-spinner" style="width:20px;height:20px;border-width:2px;"></div>' +
                '正在 TMDB 中检索【' + cleanTitle + (rawYear ? ' (' + rawYear + ')' : '') + '】...</div>';
            if (statsEl) statsEl.innerText = '检索中...';

            fetchTmdbSearch(queryArg, rawYear)
                .then(function(results) {
                    batchBindState.candidates = results || [];
                    renderBatchBindCandidates(results || []);
                })
                .catch(function(err) {
                    if (statsEl) statsEl.innerText = '检索失败';
                    candBox.innerHTML = '<div style="text-align:center;padding:30px 0;color:#f87171;font-size:13px;">检索异常: ' + (err.message || err) + '</div>';
                });
        }

        function renderBatchBindCandidates(results) {
            var candBox = document.getElementById('batchBindCandidatesBox');
            var statsEl = document.getElementById('batchBindResultStats');
            if (!candBox) return;

            if (!results || results.length === 0) {
                if (statsEl) statsEl.innerText = '找到 0 个条目';
                candBox.innerHTML = '<div style="text-align:center;padding:45px 0;color:var(--text-muted);font-size:13px;">' +
                    '<div style="font-size:28px;margin-bottom:8px;">🔍</div>' +
                    '<div>未在 TMDB 检索到相关影视条目</div>' +
                    '<div style="font-size:12px;color:#94a3b8;margin-top:4px;">建议微调上方片名关键词或清空年份重新尝试</div>' +
                    '</div>';
                return;
            }

            if (statsEl) statsEl.innerText = '找到 ' + results.length + ' 个候选条目';

            var cHtml = '<div style="display:grid;grid-template-columns:repeat(auto-fill, minmax(360px, 1fr));gap:10px;">';
            for (var i = 0; i < results.length; i++) {
                var v = results[i];
                var vTitle = v.title || v.name || v.original_title || '';
                var vOrig = v.original_title || v.original_name || '';
                var vYear = v.release_date ? v.release_date.split('-')[0] : (v.first_air_date ? v.first_air_date.split('-')[0] : (v.year || ''));
                var vPic = v.poster_path ? (v.poster_path.startsWith('http') ? v.poster_path : ('https://image.tmdb.org/t/p/w500' + v.poster_path)) : (v.pic || '');
                var vRating = v.vote_average ? v.vote_average.toFixed(1) : (v.rating ? String(v.rating) : '');
                var isTV = (v.media_type === 'tv') || (v.typeId === 2);
                var typeBadge = isTV
                    ? '<span class="badge" style="background:#0284c7;color:#fff;font-size:10px;padding:2px 6px;border-radius:4px;flex-shrink:0;">剧集</span>'
                    : '<span class="badge" style="background:#7c3aed;color:#fff;font-size:10px;padding:2px 6px;border-radius:4px;flex-shrink:0;">电影</span>';
                var overview = v.overview || v.content || '暂无剧情简介';

                cHtml += '<div class="batch-bind-card" style="display:flex;gap:12px;padding:10px 12px;background:rgba(15,23,42,0.75);border:1px solid rgba(255,255,255,0.08);border-radius:8px;position:relative;transition:all 0.2s;" onmouseenter="this.style.borderColor=\'rgba(99,102,241,0.5)\';this.style.background=\'rgba(30,41,59,0.85)\'" onmouseleave="this.style.borderColor=\'rgba(255,255,255,0.08)\';this.style.background=\'rgba(15,23,42,0.75)\'">';

                // 海报图
                if (vPic) {
                    cHtml += '<img src="' + vPic + '" style="width:48px;height:70px;object-fit:cover;border-radius:4px;flex-shrink:0;cursor:pointer;background:#1e293b;" title="点击查看大图与详情" onclick="openBatchBindCandidateDetail(' + i + ')">';
                } else {
                    cHtml += '<div style="width:48px;height:70px;background:#1e293b;border-radius:4px;flex-shrink:0;display:flex;align-items:center;justify-content:center;color:var(--text-muted);cursor:pointer;font-size:20px;" title="点击查看详情" onclick="openBatchBindCandidateDetail(' + i + ')">🎬</div>';
                }

                // 中间主体
                cHtml += '<div style="flex:1;min-width:0;display:flex;flex-direction:column;justify-content:space-between;">';
                cHtml += '  <div>';
                cHtml += '    <div style="display:flex;align-items:center;gap:6px;">';
                cHtml += '      ' + typeBadge;
                cHtml += '      <span style="font-size:13px;font-weight:700;color:#fff;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="' + vTitle.replace(/"/g, '&quot;') + '">' + vTitle + '</span>';
                cHtml += '    </div>';
                cHtml += '    <div style="font-size:11px;color:var(--text-muted);margin-top:3px;display:flex;gap:8px;align-items:center;">';
                if (vYear) cHtml += '<span>' + vYear + ' 年</span>';
                if (vRating) cHtml += '<span style="color:#f59e0b;font-weight:600;">★ ' + vRating + '</span>';
                if (v.id) cHtml += '<span style="color:#64748b;">#' + v.id + '</span>';
                cHtml += '    </div>';
                if (vOrig && vOrig !== vTitle) {
                    cHtml += '    <div style="font-size:11px;color:#64748b;margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="' + vOrig.replace(/"/g, '&quot;') + '">' + vOrig + '</div>';
                }
                cHtml += '    <div style="font-size:11px;color:#94a3b8;margin-top:4px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;line-height:1.35;" title="' + overview.replace(/"/g, '&quot;') + '">' + overview + '</div>';
                cHtml += '  </div>';
                cHtml += '</div>';

                // 右侧操作按钮栏
                cHtml += '<div style="display:flex;flex-direction:column;justify-content:center;gap:6px;flex-shrink:0;margin-left:4px;padding-left:8px;border-left:1px solid rgba(255,255,255,0.06);">';
                cHtml += '  <button type="button" class="btn btn-secondary" style="padding:3px 8px;font-size:11px;white-space:nowrap;color:#a5b4fc;border-color:rgba(99,102,241,0.3);" onclick="openBatchBindCandidateDetail(' + i + ')" title="点击查看 TMDB 完整演职员表与详情">🔍 详情</button>';
                cHtml += '  <button type="button" class="btn" style="padding:4px 10px;font-size:11px;font-weight:600;white-space:nowrap;background:linear-gradient(135deg, #0284c7, #2563eb);color:#fff;border:none;border-radius:5px;" onclick="confirmSelectBatchBindCandidate(' + i + ')">✓ 绑定 (' + batchBindState.count + '项)</button>';
                cHtml += '</div>';

                cHtml += '</div>';
            }
            cHtml += '</div>';
            candBox.innerHTML = cHtml;
        }

        function openBatchBindCandidateDetail(candIdx) {
            var cand = batchBindState.candidates && batchBindState.candidates[candIdx];
            if (!cand) return;

            var cleanedTarget = cleanSeasonFromTitle(cand.title || cand.name || '');
            var cleanTitle = cleanedTarget.title || cand.title || cand.name || '';
            var vYear = cand.release_date ? cand.release_date.split('-')[0] : (cand.first_air_date ? cand.first_air_date.split('-')[0] : (cand.year || ''));
            var isTV = (cand.media_type === 'tv') || (cand.typeId === 2) || (cleanedTarget.season >= 0);

            var previewCand = {
                tmdbId: cand.id || cand.tmdbId || 0,
                title: cleanTitle,
                originalTitle: cand.original_title || cand.original_name || cand.ename || '',
                pic: cand.poster_path ? (cand.poster_path.startsWith('http') ? cand.poster_path : ('https://image.tmdb.org/t/p/w500' + cand.poster_path)) : (cand.pic || ''),
                backdropPath: cand.backdrop_path ? (cand.backdrop_path.startsWith('http') ? cand.backdrop_path : ('https://image.tmdb.org/t/p/original' + cand.backdrop_path)) : (cand.backdropPath || ''),
                year: String(vYear || ''),
                typeId: isTV ? 2 : 1,
                content: cand.overview || cand.content || '',
                remark: (cand.vote_average ? ('评分 ' + cand.vote_average.toFixed(1)) : (cand.remark || ''))
            };

            openTmdbPreviewModal(-1, previewCand, true, function() {
                confirmSelectBatchBindCandidate(candIdx);
            });

            var btnConfirm = document.getElementById('btnConfirmTmdbBind');
            if (btnConfirm) {
                btnConfirm.innerText = '✓ 选定并批量绑定此片 (' + batchBindState.count + '项)';
            }
        }

        function confirmSelectBatchBindCandidate(candIdx) {
            var cand = batchBindState.candidates && batchBindState.candidates[candIdx];
            if (!cand) return;
            if (typeof batchBindState.onConfirm === 'function') {
                batchBindState.onConfirm(cand, batchBindState.count);
            }
        }

        function applyExcelBatchBindConfirm(cand, keys) {
            if (!cand || !keys || keys.length === 0) return;

            var cleanedTarget = cleanSeasonFromTitle(cand.title || cand.name || '');
            var cleanTitle = cleanedTarget.title || cand.title || cand.name || '';
            var vYear = cand.release_date ? cand.release_date.split('-')[0] : (cand.first_air_date ? cand.first_air_date.split('-')[0] : (cand.year || ''));
            var isTV = (cand.media_type === 'tv') || (cand.typeId === 2) || (cleanedTarget.season >= 0);
            var targetTypeId = isTV ? 2 : 1;

            var targetVideo = {
                id: cand.tmdbId || cand.id || 0,
                title: cleanTitle,
                originalTitle: cand.original_title || cand.original_name || cand.ename || '',
                pic: cand.poster_path ? (cand.poster_path.startsWith('http') ? cand.poster_path : ('https://image.tmdb.org/t/p/w500' + cand.poster_path)) : (cand.pic || ''),
                backdropPath: cand.backdrop_path ? (cand.backdrop_path.startsWith('http') ? cand.backdrop_path : ('https://image.tmdb.org/t/p/original' + cand.backdrop_path)) : (cand.backdropPath || ''),
                year: String(vYear || ''),
                typeId: targetTypeId,
                director: cand.director || '',
                starring: cand.starring || '',
                bianju: '',
                tags: [],
                area: '',
                language: '',
                stime: '',
                times: '',
                alias: [],
                content: cand.overview || cand.content || '',
                remark: (cand.vote_average ? ('评分 ' + cand.vote_average.toFixed(1)) : (cand.remark || '')),
                tmdbId: cand.tmdbId || cand.id || 0
            };

            var boundCount = 0;
            for (var i = 0; i < state.excelUnmatched.length; i++) {
                var it = state.excelUnmatched[i];
                if (keys.indexOf(it.key) !== -1) {
                    var sVal = (it.season !== undefined && it.season !== null && it.season > 0) ? it.season : (isTV ? (cleanedTarget.season > 0 ? cleanedTarget.season : 1) : 0);
                    var eVal = (it.episode !== undefined && it.episode !== null && it.episode > 0) ? it.episode : 1;

                    state.excelMatched.push({
                        key: it.key || ('matched_' + Math.random().toString(36).substr(2, 9)),
                        raw: it.raw,
                        extractedTitle: targetVideo.title,
                        extractedYear: targetVideo.year,
                        extractedRemark: it.extractedRemark,
                        season: sVal,
                        episode: eVal,
                        video: targetVideo,
                        parentFolderName: it.parentFolderName || (it.raw && it.raw.parentFolderName) || ''
                    });
                    boundCount++;
                }
            }

            state.excelUnmatched = state.excelUnmatched.filter(function(it) {
                return keys.indexOf(it.key) === -1;
            });
            state.excelUnmatchedSelectedKeys = [];
            updateExcelUnmatchedBatchBtns();

            closeModal('batchBindModal');
            showToast('🎉 成功将选中的 ' + boundCount + ' 个分集批量绑定至【' + targetVideo.title + ' (' + (targetVideo.year || '未知年份') + ')】！');

            renderExcelMatchedTable();
            renderExcelUnmatched();

            var btnConfirm = document.getElementById('btnConfirmBatchImport');
            if (btnConfirm) btnConfirm.style.display = 'inline-flex';

            var nextTab = (state.excelUnmatched.length === 0) ? 'matched' : 'unmatched';
            updateExcelTabCounts(nextTab);
            if (nextTab === 'matched') {
                switchExcelTab('matched');
            }
        }

        function handleExcelUnmatchedBatchBind() {
            var keys = state.excelUnmatchedSelectedKeys || [];
            if (keys.length === 0) {
                showToast('请先勾选要批量绑定的条目');
                return;
            }

            var defaultTitle = '';
            var defaultYear = '';
            for (var i = 0; i < state.excelUnmatched.length; i++) {
                var it = state.excelUnmatched[i];
                if (keys.indexOf(it.key) !== -1) {
                    if (!defaultTitle && it.extractedTitle) {
                        var cleanT = cleanSeasonFromTitle(it.extractedTitle);
                        defaultTitle = cleanT.title || it.extractedTitle;
                    }
                    if (!defaultYear && it.extractedYear) {
                        defaultYear = it.extractedYear;
                    }
                    if (defaultTitle && defaultYear) break;
                }
            }

            if (defaultTitle) {
                var cObj = extractTmdbIdAndClean(defaultTitle);
                if (cObj.title) defaultTitle = cObj.title;
                if (!defaultYear && cObj.year) defaultYear = cObj.year;
            }

            openUniversalBatchBindModal({
                mode: 'excel',
                keys: keys,
                count: keys.length,
                defaultTitle: defaultTitle,
                defaultYear: defaultYear,
                onConfirm: function(selectedCand) {
                    applyExcelBatchBindConfirm(selectedCand, keys);
                }
            });
        }

        function handleExcelUnmatchedBatchDelete() {
            var keys = state.excelUnmatchedSelectedKeys || [];
            if (keys.length === 0) return;
            if (!confirm('确定要批量移除选中的 ' + keys.length + ' 条待确认记录吗？')) return;

            state.excelUnmatched = state.excelUnmatched.filter(function(it) {
                return keys.indexOf(it.key) === -1;
            });
            state.excelUnmatchedSelectedKeys = [];
            updateExcelUnmatchedBatchBtns();
            showToast('已批量移除 ' + keys.length + ' 条记录');
            renderExcelUnmatched();
            updateExcelTabCounts();
        }

        function saveExcelUnmatchedToQueue() {
            var items = state.excelUnmatched || [];
            if (items.length === 0) {
                showToast('当前没有待确认记录可存入暂存箱');
                return;
            }

            var libId = state.currentLibraryId;
            if (!libId) {
                showToast('无法获取当前媒体库 ID');
                return;
            }

            if (!confirm('确定要将当前 ' + items.length + ' 条待确认记录存入私有库待确认暂存箱吗？\n\n存入后随时可在主页【待确认暂存箱】中集中处理。')) {
                return;
            }

            var payloadItems = items.map(function(it) {
                return {
                    url: (it.raw && it.raw.linkUrl) || it.linkUrl || '',
                    password: (it.raw && it.raw.password) || it.password || '',
                    raw_title: it.extractedTitle || '',
                    raw_year: it.extractedYear || '',
                    raw_filename: (it.raw && it.raw.rawFileName) || it.rawFileName || '',
                    parent_folder_name: it.parentFolderName || (it.raw && it.raw.parentFolderName) || '',
                    remark: it.extractedRemark || (it.raw && it.raw.remark) || '',
                    link_type: 'pan',
                    provider: (it.raw && it.raw.provider) || '',
                    season_number: it.season || 1,
                    episode_number: it.episode || 1,
                    episode_title: (it.episode ? ('第' + it.episode + '集') : ''),
                    failure_reason: it.conflictWarning || '未完全对齐'
                };
            });

            showToast('正在存入暂存箱...');
            fetch('/api/private/unmatched/save-batch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    library_id: libId,
                    items: payloadItems
                })
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (data.success) {
                    showToast('🎉 已成功将 ' + (data.saved_count || items.length) + ' 条记录存入待确认暂存箱！');
                    state.excelUnmatched = [];
                    state.excelUnmatchedSelectedKeys = [];
                    renderExcelUnmatched();
                    updateExcelTabCounts();
                    if (state.excelMatched.length > 0) {
                        switchExcelTab('matched');
                    }
                    if (typeof loadUnmatchedQueueCount === 'function') {
                        loadUnmatchedQueueCount();
                    }
                } else {
                    showToast('存入暂存箱失败: ' + (data.message || '未知错误'));
                }
            })
            .catch(function(e) {
                showToast('请求异常: ' + e.message);
            });
        }

        // 7. 未匹配项就地联想搜索与快捷点选绑定 (直接针对 TMDB 官方库精准检索，杜绝多余的空查询)
        function handleSelectCandidate(idx, c) {
            var candList = state.unmatchedCandidatesMap && state.unmatchedCandidatesMap[idx];
            if (!candList || !candList[c]) return;
            var cand = candList[c];
            inlineSelectUnmatched(idx, cand, cand.isTmdb);
        }

        function handlePreviewCandidate(idx, c) {
            var candList = state.unmatchedCandidatesMap && state.unmatchedCandidatesMap[idx];
            if (!candList || !candList[c]) return;
            var cand = candList[c];
            openTmdbPreviewModal(idx, cand, cand.isTmdb);
        }

        function inlineSearchUnmatched(idx, mode) {
            var item = state.excelUnmatched[idx];
            var titleInput = document.getElementById('unmatch_title_' + idx);
            var title = (titleInput ? titleInput.value : '').trim();
            var cleanT = extractTmdbIdAndClean(title);
            title = cleanT.title || title;
            title = normalizeChineseColon(title);
            if (titleInput) {
                titleInput.value = title;
            }
            var year = (document.getElementById('unmatch_year_' + idx).value || '').trim();
            if (!year && cleanT.year) {
                year = cleanT.year;
                var yearInput = document.getElementById('unmatch_year_' + idx);
                if (yearInput) yearInput.value = year;
            }
            var altTitle = (item.extractedAltTitle || '').trim();
            var imdbId = (item.imdbId || '').trim();
            var itemTmdbId = item.tmdbId || cleanT.tmdbId || 0;

            var expandRow = document.getElementById('unmatch_expand_' + idx);
            var candBox = document.getElementById('unmatch_candidates_' + idx);
            expandRow.style.display = '';

            mode = mode || 'auto';

            // 渲染顶部多数据源快捷切换 Tab (纯参数传递，绝无引号转义隐患)
            var searchHeaderHtml = '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid rgba(255,255,255,0.1);">';
            searchHeaderHtml += '<div style="display:flex;gap:6px;align-items:center;">';
            searchHeaderHtml += '<span style="font-size:12px;color:var(--text-muted);">搜索源:</span>';
            if (itemTmdbId > 0) {
                searchHeaderHtml += '<button class="btn ' + (mode === 'tmdb_id' ? '' : 'btn-secondary') + '" style="padding:2px 8px;font-size:11px;" onclick="inlineSearchUnmatched(' + idx + ', \'tmdb_id\')">🎯 TMDB ID (' + itemTmdbId + ')</button>';
            }
            if (imdbId) {
                searchHeaderHtml += '<button class="btn ' + (mode === 'imdb' ? '' : 'btn-secondary') + '" style="padding:2px 8px;font-size:11px;" onclick="inlineSearchUnmatched(' + idx + ', \'imdb\')">🎯 IMDb (' + imdbId + ')</button>';
            }
            searchHeaderHtml += '<button class="btn ' + (mode === 'auto' || mode === 'tmdb_zh' ? '' : 'btn-secondary') + '" style="padding:2px 8px;font-size:11px;" onclick="inlineSearchUnmatched(' + idx + ', \'tmdb_zh\')">🌐 TMDB (中文)</button>';
            if (altTitle && altTitle.length > 2 && !['3D', '4K', '2D', 'HD'].includes(altTitle.toUpperCase())) {
                searchHeaderHtml += '<button class="btn ' + (mode === 'tmdb_en' ? '' : 'btn-secondary') + '" style="padding:2px 8px;font-size:11px;" onclick="inlineSearchUnmatched(' + idx + ', \'tmdb_en\')">🌐 TMDB 原名 (' + altTitle.replace(/"/g, '&quot;') + ')</button>';
            }
            searchHeaderHtml += '<button class="btn ' + (mode === 'cloud' ? '' : 'btn-secondary') + '" style="padding:2px 8px;font-size:11px;" onclick="inlineSearchUnmatched(' + idx + ', \'cloud\')">🔍 云端库</button>';
            searchHeaderHtml += '</div>';
            searchHeaderHtml += '<div style="display:flex;gap:8px;align-items:center;">';
            searchHeaderHtml += '<button class="btn btn-outline" style="padding:2px 8px;font-size:11px;border-color:rgba(16,185,129,0.5);color:#6ee7b7;" onclick="openCustomMovieModal(' + idx + ')" title="无需刮削，自由命名作为自建/花絮影片独立入库">➕ 直接自建入库</button>';
            searchHeaderHtml += '<span style="font-size:11px;color:#94a3b8;">支持点选自动收录</span>';
            searchHeaderHtml += '</div>';
            searchHeaderHtml += '</div>';
            searchHeaderHtml += '<div id="unmatch_cards_' + idx + '" style="display:flex;gap:10px;overflow-x:auto;padding-bottom:4px;"><div style="font-size:12px;color:#a5b4fc;padding:8px;">正在检索中...</div></div>';

            candBox.innerHTML = searchHeaderHtml;
            var cardsBox = document.getElementById('unmatch_cards_' + idx);

            var queryKeyword = (mode === 'tmdb_en' && altTitle) ? altTitle : title;
            if (!queryKeyword && !altTitle && !imdbId && !itemTmdbId) {
                cardsBox.innerHTML = '<div style="font-size:12px;color:#f87171;padding:8px;">未输入有效片名关键词，请在上方输入框填写片名后再搜索</div>';
                return;
            }

            // 1. 查云端库 (仅在用户主动点击“云端库”Tab 时调用，严防空请求)
            function searchCloudDb(keyword) {
                if (!keyword || !keyword.trim()) return Promise.resolve([]);
                return fetch('/api/mv/videos/search?q=' + encodeURIComponent(keyword.trim()))
                    .then(function(res) { return res.json(); })
                    .then(function(data) {
                        return (data.data && (data.data.items || data.data.list || data.data.results)) || data.items || data.list || [];
                    })
                    .catch(function(err) {
                        console.error('[searchCloudDb] error:', err);
                        return [];
                    });
            }

            // 2. 查 TMDB (支持精确 IMDb 反查、TMDB ID 与关键字搜索)
            function searchTmdb(keyword, searchYear, searchImdb) {
                if (!keyword && !searchImdb) return Promise.resolve([]);
                var cleanObj = extractTmdbIdAndClean(keyword);
                var cleanKey = cleanObj.title || keyword;
                var cleanYear = searchYear || cleanObj.year || '';
                var tmdbId = cleanObj.tmdbId;
                var trimmedKey = String(cleanKey).trim();

                // 若用户未显式指定 tmdbId，且输入的是大于 2099 的纯长数字（如 530915），才可能是直接粘贴的 TMDb ID
                // 常见的 4 位公历年份数字（如 1000~2099，如 1776, 1917, 1984, 2012 等）为人类历史与影视真实片名，必须作为标题检索！
                if (!tmdbId && /^\d+$/.test(trimmedKey)) {
                    var numVal = parseInt(trimmedKey, 10) || 0;
                    if (numVal > 2099) {
                        tmdbId = numVal;
                    }
                }

                // 若具有 TMDB ID，优先直达检索云端库与 TMDB
                if (tmdbId > 0) {
                    return fetch('/api/mv/videos/search?tmdbId=' + tmdbId)
                        .then(function(res) { return res.json(); })
                        .then(function(data) {
                            var searchType = (data && data.data && data.data.searchType) || '';
                            var items = (data && data.data && Array.isArray(data.data.items)) ? data.data.items : [];
                            // 必须严格校验返回类型为 tmdb 精准匹配，且确实包含该 tmdbId，杜绝未命中时 fallback 为全站最新无关影片
                            if (searchType === 'tmdb' && items.length > 0 && items.some(function(it) { return (it.tmdbId || it.tmdb_id) == tmdbId; })) {
                                return items.filter(function(it) { return (it.tmdbId || it.tmdb_id) == tmdbId; }).map(function(it) {
                                    return {
                                        id: it.tmdbId || it.tmdb_id || tmdbId,
                                        title: it.title,
                                        name: it.title,
                                        original_title: it.ename || it.original_title || '',
                                        release_date: it.year ? (it.year + '-01-01') : '',
                                        first_air_date: it.year ? (it.year + '-01-01') : '',
                                        poster_path: it.pic ? it.pic.replace('https://image.tmdb.org/t/p/w500', '') : '',
                                        backdrop_path: it.backdropPath || it.backdrop_path || '',
                                        vote_average: it.rating ? parseFloat(it.rating) : 0,
                                        media_type: (it.typeId === 2) ? 'tv' : 'movie',
                                        overview: it.content || ''
                                    };
                                });
                            }
                            // 云端库未命中该 TMDb ID，回退至本地 TMDB 接口精准查询电影/剧集详情
                            return fetch('/api/tmdb/movie/' + tmdbId)
                                .then(function(r) { return r.json(); })
                                .then(function(d) {
                                    if (d && d.success && d.data && d.data.id) {
                                        var m = d.data;
                                        return [{
                                            id: m.id,
                                            title: m.title || m.original_title || '',
                                            name: m.title || m.original_title || '',
                                            original_title: m.original_title || '',
                                            release_date: m.release_date || '',
                                            first_air_date: '',
                                            poster_path: m.poster_path || '',
                                            backdrop_path: m.backdrop_path || '',
                                            vote_average: m.vote_average || 0,
                                            media_type: 'movie',
                                            overview: m.overview || ''
                                        }];
                                    }
                                    return [];
                                })
                                .catch(function() { return []; });
                        })
                        .catch(function() { return []; });
                }

                var url = '/api/tmdb/search/movie?';
                if (searchImdb) {
                    url += 'imdb_id=' + encodeURIComponent(searchImdb) + '&query=' + encodeURIComponent(trimmedKey || searchImdb);
                } else {
                    url += 'query=' + encodeURIComponent(trimmedKey);
                }
                if (cleanYear) url += '&year=' + encodeURIComponent(cleanYear);
                return fetch(url)
                    .then(function(res) { return res.json(); })
                    .then(function(data) {
                        if (data && data.data && Array.isArray(data.data.results)) {
                            return data.data.results;
                        }
                        return [];
                    })
                    .catch(function() { return []; });
            }

            // 3. 渲染候选卡片 (使用内存对象与纯数字下标，100% 杜绝引号转义语法错误)
            function renderCandidates(list, isTmdb) {
                if (!list || list.length === 0) {
                    cardsBox.innerHTML = '<div style="font-size:12px;color:var(--text-muted);padding:8px;display:flex;align-items:center;gap:12px;">' +
                        '<span>未在 ' + (isTmdb ? 'TMDB' : '云端库') + ' 检索到相关影视</span>' +
                        '<button class="btn btn-secondary" style="padding:2px 10px;font-size:11px;border-color:rgba(16,185,129,0.5);color:#6ee7b7;" onclick="openCustomMovieModal(' + idx + ')">➕ 立即作为自建影片入库</button>' +
                        '</div>';
                    return;
                }

                state.unmatchedCandidatesMap = state.unmatchedCandidatesMap || {};
                var candList = [];

                for (var c = 0; c < Math.min(list.length, 6); c++) {
                    var v = list[c];
                    var vTitle = isTmdb ? (v.title || v.name || v.original_title || '') : (v.title || '');
                    var vYear = isTmdb ? (v.release_date ? v.release_date.split('-')[0] : (v.first_air_date ? v.first_air_date.split('-')[0] : '')) : (v.year || '');
                    var vPic = isTmdb ? (v.poster_path ? 'https://image.tmdb.org/t/p/w500' + v.poster_path : '') : (v.pic || '');
                    var vBackdrop = isTmdb ? (v.backdrop_path || '') : (v.backdropPath || '');
                    var vRating = isTmdb ? (v.vote_average ? v.vote_average.toFixed(1) : '') : '';
                    var vOrig = isTmdb ? (v.original_title || v.original_name || '') : (v.ename || '');

                    candList.push({
                        id: isTmdb ? 0 : v.id,
                        title: vTitle,
                        originalTitle: vOrig,
                        pic: vPic,
                        backdropPath: vBackdrop,
                        year: vYear,
                        typeId: isTmdb ? (v.media_type === 'tv' ? 2 : 1) : (v.typeId || 1),
                        director: isTmdb ? '' : (v.director || ''),
                        starring: isTmdb ? '' : (v.starring || ''),
                        content: isTmdb ? (v.overview || '') : (v.content || ''),
                        remark: isTmdb ? (vRating ? '评分 ' + vRating : '') : (v.remark || ''),
                        tmdbId: isTmdb ? v.id : (v.tmdbId || 0),
                        isTmdb: isTmdb
                    });
                }

                state.unmatchedCandidatesMap[idx] = candList;

                var badgeStyle = isTmdb ? 'background:linear-gradient(135deg,#6366f1,#4f46e5);' : 'background:linear-gradient(135deg,#10b981,#059669);';
                var badgeText = isTmdb ? 'TMDB' : '云端';

                var cHtml = '';
                for (var i = 0; i < candList.length; i++) {
                    var card = candList[i];
                    var typeLabel = (card.typeId === 2) ? '<span style="display:inline-block;font-size:10px;padding:1px 4px;border-radius:3px;background:rgba(99,102,241,0.25);color:#a5b4fc;margin-right:4px;">剧集</span>' : '<span style="display:inline-block;font-size:10px;padding:1px 4px;border-radius:3px;background:rgba(148,163,184,0.2);color:#94a3b8;margin-right:4px;">电影</span>';
                    cHtml += '<div style="display:flex;gap:10px;background:rgba(30,41,59,0.85);border:1px solid var(--card-border);border-radius:8px;padding:8px;min-width:230px;max-width:285px;cursor:pointer;align-items:center;position:relative;transition:border-color 0.2s, background-color 0.2s;" onmouseover="this.style.borderColor=\'var(--accent-color)\';this.style.background=\'rgba(45,55,72,0.95)\'" onmouseout="this.style.borderColor=\'var(--card-border)\';this.style.background=\'rgba(30,41,59,0.85)\'" onclick="handleSelectCandidate(' + idx + ', ' + i + ')">';
                    cHtml += '<button type="button" class="btn-card-detail" title="全屏查看影视完整详情 (演职员/剧照/剧情，按ESC退出)" onclick="event.stopPropagation(); handlePreviewCandidate(' + idx + ', ' + i + ')" style="position:absolute;top:6px;right:6px;background:rgba(15,23,42,0.85);border:1px solid rgba(255,255,255,0.2);color:#38bdf8;font-size:10px;padding:2px 6px;border-radius:4px;cursor:pointer;display:inline-flex;align-items:center;gap:2px;z-index:3;line-height:1.2;box-shadow:0 1px 3px rgba(0,0,0,0.5);">🔍 详情</button>';
                    cHtml += '<div style="position:relative;flex-shrink:0;" onclick="event.stopPropagation(); handlePreviewCandidate(' + idx + ', ' + i + ')" title="点击查看高清详情">';
                    if (card.pic) {
                        cHtml += '<img referrerpolicy="no-referrer" src="' + card.pic + '" style="width:46px;height:66px;object-fit:cover;border-radius:4px;box-shadow:0 2px 4px rgba(0,0,0,0.5);display:block;cursor:zoom-in;" onerror="this.onerror=null;this.style.display=\'none\';if(this.nextElementSibling)this.nextElementSibling.style.display=\'flex\';">';
                        cHtml += '<div style="display:none;width:46px;height:66px;background:#1e293b;border-radius:4px;align-items:center;justify-content:center;font-size:18px;">🎬</div>';
                    } else {
                        cHtml += '<div style="width:46px;height:66px;background:#1e293b;border-radius:4px;display:flex;align-items:center;justify-content:center;font-size:18px;">🎬</div>';
                    }
                    cHtml += '<div style="position:absolute;top:2px;left:2px;font-size:9px;color:#fff;' + badgeStyle + 'padding:1px 4px;border-radius:3px;font-weight:600;box-shadow:0 1px 3px rgba(0,0,0,0.6);line-height:1.2;">' + badgeText + '</div>';
                    cHtml += '</div>';
                    cHtml += '<div style="overflow:hidden;flex:1;min-width:0;padding-right:38px;"><div style="font-size:13px;font-weight:700;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="' + card.title.replace(/"/g, '&quot;') + '">' + card.title + '</div>';
                    if (card.originalTitle && card.originalTitle !== card.title) {
                        cHtml += '<div style="font-size:11px;color:#a5b4fc;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:2px;" title="' + card.originalTitle.replace(/"/g, '&quot;') + '">' + card.originalTitle + '</div>';
                    }
                    cHtml += '<div style="font-size:11px;color:var(--text-muted);margin-top:2px;">' + typeLabel + (card.year ? card.year + ' 年' : '') + (card.remark ? ' · ' + card.remark : '') + '</div>';
                    cHtml += '<div style="font-size:11px;color:#38bdf8;margin-top:3px;font-weight:500;">点击选定' + (isTmdb ? '并同步' : '') + ' ✓</div></div>';
                    cHtml += '</div>';
                }
                cardsBox.innerHTML = cHtml;
            }

            // 执行检索分支 (默认优先检索 TMDB 中文，未命中且有原名则自动检索原名，彻底移除无用 cloud 请求)
            if (mode === 'tmdb_id' || (mode === 'auto' && itemTmdbId > 0)) {
                searchTmdb(String(itemTmdbId), year).then(function(list) {
                    if (list && list.length > 0) {
                        renderCandidates(list, true);
                    } else {
                        searchTmdb(title, year).then(function(zhList) { renderCandidates(zhList, true); });
                    }
                });
            } else if (mode === 'imdb') {
                searchTmdb(title, year, imdbId).then(function(list) { renderCandidates(list, true); });
            } else if (mode === 'cloud') {
                searchCloudDb(title).then(function(list) {
                    if (list.length > 0) {
                        renderCandidates(list, false);
                    } else if (altTitle && altTitle !== title && altTitle.length > 2 && !['3D', '4K', '2D', 'HD'].includes(altTitle.toUpperCase())) {
                        searchCloudDb(altTitle).then(function(altList) {
                            renderCandidates(altList, false);
                        });
                    } else {
                        renderCandidates([], false);
                    }
                });
            } else if (mode === 'tmdb_en') {
                searchTmdb(altTitle || title, year).then(function(list) { renderCandidates(list, true); });
            } else {
                // 默认智能检索 TMDB (若有 IMDb ID 优先精准直连)
                var initialSearch = imdbId ? searchTmdb(title, year, imdbId) : searchTmdb(title, year);
                initialSearch.then(function(tmdbList) {
                    if (tmdbList.length > 0) {
                        renderCandidates(tmdbList, true);
                    } else if (imdbId) {
                        // 若 IMDb 未命中，继续尝试中文片名
                        searchTmdb(title, year).then(function(zhList) {
                            if (zhList.length > 0) {
                                renderCandidates(zhList, true);
                            } else if (altTitle && altTitle !== title && altTitle.length > 2 && !['3D', '4K', '2D', 'HD'].includes(altTitle.toUpperCase())) {
                                searchTmdb(altTitle, year).then(function(enList) {
                                    renderCandidates(enList, true);
                                });
                            } else {
                                renderCandidates([], true);
                            }
                        });
                    } else if (altTitle && altTitle !== title && altTitle.length > 2 && !['3D', '4K', '2D', 'HD'].includes(altTitle.toUpperCase())) {
                        searchTmdb(altTitle, year).then(function(tmdbEnList) {
                            renderCandidates(tmdbEnList, true);
                        });
                    } else {
                        renderCandidates([], true);
                    }
                });
            }
        }

        function mapCountryCodeToArea(code, name) {
            code = (code || '').toUpperCase().trim();
            name = (name || '').trim();
            if (/[\u4e00-\u9fa5]/.test(name)) return name;
            var cMap = {
                'US': '美国', 'CN': '中国大陆', 'HK': '中国香港', 'TW': '中国台湾', 'MO': '中国澳门',
                'JP': '日本', 'KR': '韩国', 'KP': '朝鲜', 'GB': '英国', 'UK': '英国',
                'FR': '法国', 'DE': '德国', 'IT': '意大利', 'ES': '西班牙', 'CA': '加拿大',
                'AU': '澳大利亚', 'RU': '俄罗斯', 'IN': '印度', 'TH': '泰国', 'SG': '新加坡',
                'MY': '马来西亚', 'VN': '越南', 'PH': '菲律宾', 'ID': '印度尼西亚', 'BR': '巴西',
                'MX': '墨西哥', 'AR': '阿根廷', 'CL': '智利', 'CO': '哥伦比亚', 'PE': '秘鲁',
                'ZA': '南非', 'EG': '埃及', 'NG': '尼日利亚', 'TR': '土耳其', 'IR': '伊朗',
                'IL': '以色列', 'SA': '沙特阿拉伯', 'AE': '阿联酋', 'NL': '荷兰', 'BE': '比利时',
                'CH': '瑞士', 'SE': '瑞典', 'NO': '挪威', 'DK': '丹麦', 'FI': '芬兰',
                'IS': '冰岛', 'IE': '爱尔兰', 'PL': '波兰', 'CZ': '捷克', 'AT': '奥地利',
                'HU': '匈牙利', 'RO': '罗马尼亚', 'GR': '希腊', 'PT': '葡萄牙', 'UA': '乌克兰',
                'NZ': '新西兰', 'CU': '古巴', 'HR': '克罗地亚', 'RS': '塞尔维亚'
            };
            if (cMap[code]) return cMap[code];
            if (code.length === 2 && cMap[code]) return cMap[code];
            var nMap = {
                'united states of america': '美国', 'united states': '美国', 'usa': '美国',
                'china': '中国大陆', "people's republic of china": '中国大陆',
                'hong kong': '中国香港', 'taiwan': '中国台湾', 'macau': '中国澳门',
                'japan': '日本', 'south korea': '韩国', 'korea': '韩国',
                'united kingdom': '英国', 'uk': '英国', 'great britain': '英国',
                'france': '法国', 'germany': '德国', 'italy': '意大利', 'spain': '西班牙',
                'canada': '加拿大', 'australia': '澳大利亚', 'russia': '俄罗斯', 'india': '印度',
                'thailand': '泰国', 'singapore': '新加坡', 'malaysia': '马来西亚',
                'vietnam': '越南', 'philippines': '菲律宾', 'indonesia': '印度尼西亚',
                'brazil': '巴西', 'mexico': '墨西哥', 'argentina': '阿根廷',
                'netherlands': '荷兰', 'belgium': '比利时', 'switzerland': '瑞士',
                'sweden': '瑞典', 'norway': '挪威', 'denmark': '丹麦', 'finland': '芬兰',
                'poland': '波兰', 'austria': '奥地利', 'hungary': '匈牙利', 'romania': '罗马尼亚',
                'greece': '希腊', 'portugal': '葡萄牙', 'ukraine': '乌克兰', 'new zealand': '新西兰',
                'turkey': '土耳其', 'ireland': '爱尔兰', 'czech republic': '捷克', 'czechia': '捷克'
            };
            var lower = name.toLowerCase();
            if (nMap[lower]) return nMap[lower];
            if (name.length === 2 && cMap[name.toUpperCase()]) return cMap[name.toUpperCase()];
            return name || code || '';
        }

        function mapOriginalLanguage(code, name) {
            var lMap = {
                'zh': '国语', 'cn': '国语', 'en': '英语', 'yue': '粤语', 'cantonese': '粤语',
                'ja': '日语', 'ko': '韩语', 'fr': '法语', 'de': '德语', 'es': '西班牙语',
                'it': '意大利语', 'ru': '俄语', 'th': '泰语', 'hi': '印地语'
            };
            return lMap[code] || name || code || '';
        }

        function extractFullTmdbVodInfo(details) {
            if (!details) return {};
            var crews = (details.credits && details.credits.crew) || [];
            var casts = (details.credits && details.credits.cast) || [];
            
            // 导演 (job === 'Director')
            var directorList = crews.filter(function(c) { return c.job === 'Director'; }).map(function(c) { return c.name; });
            var director = directorList.slice(0, 3).join(',');

            // 编剧 (department === 'Writing' 或 job === 'Screenplay' / 'Writer')
            var writerList = crews.filter(function(c) { return c.department === 'Writing' || c.job === 'Screenplay' || c.job === 'Writer'; }).map(function(c) { return c.name; });
            var bianju = writerList.slice(0, 3).join(',');

            // 演员 (前 8 位)
            var starringList = casts.filter(function(c) { return !c.known_for_department || c.known_for_department === 'Acting'; }).map(function(c) { return c.name; });
            if (starringList.length === 0) starringList = casts.map(function(c) { return c.name; });
            var starring = starringList.slice(0, 8).join(',');

            // 类型 tags
            var genres = details.genres || [];
            var tags = genres.map(function(g) { return (g.name || '').replace('Sci-Fi & Fantasy', '科幻玄幻').replace('War & Politics', '战争与政治').replace('Western', '西部'); }).filter(Boolean);

            // 地区 area
            var countries = details.production_countries || [];
            var area = countries.map(function(c) { return mapCountryCodeToArea(c.iso_3166_1, c.name); }).filter(Boolean).join(',');

            // 语言 language
            var languages = details.spoken_languages || [];
            var langStr = languages.map(function(l) { return mapOriginalLanguage(l.iso_639_1, l.name); }).filter(Boolean).join(',');
            if (!langStr && details.original_language) {
                langStr = mapOriginalLanguage(details.original_language, details.original_language);
            }

            // 上映时间 stime
            var stime = details.release_date || details.first_air_date || '';

            // 片长 times
            var runtime = details.runtime;
            var times = runtime ? String(runtime) + '分钟' : '';

            // 别名 alias
            var aliasList = [];
            var seenMap = {};
            function addAlias(s) {
                if (!s) return;
                var trimmed = String(s).trim();
                var lower = trimmed.toLowerCase();
                if (trimmed && !seenMap[lower]) {
                    seenMap[lower] = true;
                    aliasList.push(trimmed);
                }
            }

            if (details.title) addAlias(details.title);
            if (details.original_title) addAlias(details.original_title);
            if (details.name) addAlias(details.name);
            if (details.original_name) addAlias(details.original_name);

            // 1. alternative_titles (电影为 titles, 电视剧为 results)
            if (details.alternative_titles) {
                var altList = details.alternative_titles.titles || details.alternative_titles.results || [];
                if (Array.isArray(altList)) {
                    altList.forEach(function(item) {
                        if (item && item.title) addAlias(item.title);
                    });
                }
            }

            // 2. translations (翻译多语言名称)
            if (details.translations && Array.isArray(details.translations.translations)) {
                details.translations.translations.forEach(function(item) {
                    if (item && item.data) {
                        if (item.data.title) addAlias(item.data.title);
                        if (item.data.name) addAlias(item.data.name);
                    }
                });
            }

            // 3. 原生传递的 alias 数组 (如云端已收录影视条目)
            if (details.alias && Array.isArray(details.alias)) {
                details.alias.forEach(function(a) { addAlias(a); });
            }

            return {
                director: director,
                bianju: bianju,
                starring: starring,
                tags: tags,
                area: area,
                language: langStr,
                stime: stime,
                times: times,
                alias: aliasList
            };
        }

        function renderTmdbAliasBadges(aliases, containerEl, rowEl) {
            if (!containerEl || !rowEl) return;
            if (!aliases || !Array.isArray(aliases) || aliases.length === 0) {
                rowEl.style.display = 'none';
                containerEl.innerHTML = '';
                return;
            }

            // 过滤与去重
            var uniqueList = [];
            var seen = {};
            for (var i = 0; i < aliases.length; i++) {
                var a = (aliases[i] || '').trim();
                var lower = a.toLowerCase();
                if (a && !seen[lower]) {
                    seen[lower] = true;
                    uniqueList.push(a);
                }
            }

            if (uniqueList.length === 0) {
                rowEl.style.display = 'none';
                containerEl.innerHTML = '';
                return;
            }

            rowEl.style.display = 'block';
            var maxInitial = 8;
            var html = '';
            for (var j = 0; j < uniqueList.length; j++) {
                var hideStyle = (j >= maxInitial) ? 'display:none;' : '';
                var itemClass = (j >= maxInitial) ? 'tmdb-alias-extra' : '';
                html += '<span class="status-badge ' + itemClass + '" style="' + hideStyle + 'background:rgba(255,255,255,0.06);color:#cbd5e1;border:1px solid rgba(255,255,255,0.1);padding:1px 8px;border-radius:4px;font-size:11px;">' + uniqueList[j].replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</span>';
            }

            if (uniqueList.length > maxInitial) {
                var extraCount = uniqueList.length - maxInitial;
                html += '<button type="button" class="btn btn-secondary" id="btnToggleMoreTmdbAlias" style="padding:1px 6px;font-size:10px;background:rgba(99,102,241,0.2);color:#a5b4fc;border:1px solid rgba(99,102,241,0.3);border-radius:4px;cursor:pointer;" onclick="toggleMoreTmdbAlias(this, ' + extraCount + ')">+ 展开更多 (' + extraCount + ') ▾</button>';
            }

            containerEl.innerHTML = html;
        }

        function toggleMoreTmdbAlias(btn, count) {
            var extras = document.querySelectorAll('.tmdb-alias-extra');
            if (!extras || extras.length === 0) return;
            var isHidden = (extras[0].style.display === 'none');
            for (var i = 0; i < extras.length; i++) {
                extras[i].style.display = isHidden ? 'inline-block' : 'none';
            }
            if (btn) {
                btn.innerText = isHidden ? '收起 ▴' : ('+ 展开更多 (' + count + ') ▾');
            }
        }

        function openTmdbPreviewModal(idx, vData, isTmdb, onConfirm) {
            var rawVideo = (typeof vData === 'string') ? JSON.parse(decodeURIComponent(vData)) : vData;
            var tmdbId = rawVideo.tmdbId || 0;
            var cleanedObj = cleanSeasonFromTitle(rawVideo.title || '');
            var isTv = isSeriesTypeId(rawVideo.typeId) || (cleanedObj.season > 0);

            // 1. 设置基础信息
            var badgeEl = document.getElementById('tmdbSourceBadge');
            if (badgeEl) {
                badgeEl.innerText = isTmdb ? (isTv ? 'TMDB 剧集' : 'TMDB 电影') : '云端影视库';
                badgeEl.style.background = isTmdb ? 'linear-gradient(135deg, #6366f1, #4f46e5)' : 'linear-gradient(135deg, #10b981, #059669)';
            }

            document.getElementById('tmdbDetailModalTitle').innerText = (rawVideo.title || '') + (rawVideo.year ? ' (' + rawVideo.year + ')' : '');
            document.getElementById('tmdbMainTitle').innerText = rawVideo.title || '';
            document.getElementById('tmdbYearTag').innerText = rawVideo.year ? (rawVideo.year + ' 年') : '';
            document.getElementById('tmdbOriginalTitle').innerText = rawVideo.originalTitle || '';

            // 重置与初次填充别名展示区
            var aliasRow = document.getElementById('tmdbAliasRow');
            var aliasListEl = document.getElementById('tmdbAliasList');
            if (aliasRow) aliasRow.style.display = 'none';
            if (aliasListEl) aliasListEl.innerHTML = '';

            var initAliases = rawVideo.alias || [];
            if (initAliases && Array.isArray(initAliases) && initAliases.length > 0) {
                var initClean = initAliases.filter(function(a) {
                    var lower = (a || '').toLowerCase();
                    return lower && lower !== (rawVideo.title || '').toLowerCase() && lower !== (rawVideo.originalTitle || '').toLowerCase();
                });
                renderTmdbAliasBadges(initClean, aliasListEl, aliasRow);
            }

            var posterImg = document.getElementById('tmdbPosterImg');
            if (posterImg) posterImg.src = rawVideo.pic || '';

            var backdropEl = document.getElementById('tmdbBackdropBg');
            if (backdropEl) {
                var bgUrl = rawVideo.backdropPath || rawVideo.pic || '';
                if (bgUrl && !bgUrl.startsWith('http')) bgUrl = 'https://image.tmdb.org/t/p/w1280' + bgUrl;
                backdropEl.style.backgroundImage = bgUrl ? 'url("' + bgUrl + '")' : 'none';
            }

            document.getElementById('tmdbRatingText').innerText = rawVideo.remark || '暂无评分';
            document.getElementById('tmdbOverviewText').innerText = rawVideo.content || '正在加载详细剧情与演职员...';
            document.getElementById('tmdbDirectorText').innerText = rawVideo.director || '-';
            document.getElementById('tmdbWriterRow').style.display = 'none';
            document.getElementById('tmdbCastList').innerHTML = '<div style="font-size:12px;color:var(--text-muted);padding:8px;">正在加载演员阵容...</div>';
            document.getElementById('tmdbMetaPills').innerHTML = '';

            var linkBtn = document.getElementById('tmdbExternalLink');
            if (linkBtn) {
                if (isTmdb && tmdbId > 0) {
                    var typePath = isTv ? 'tv' : 'movie';
                    linkBtn.href = 'https://www.themoviedb.org/' + typePath + '/' + tmdbId + '?language=zh-CN';
                    linkBtn.style.display = 'inline-flex';
                } else {
                    linkBtn.style.display = 'none';
                }
            }

            // 绑定弹窗底部的【确认绑定】按钮
            var btnConfirm = document.getElementById('btnConfirmTmdbBind');
            if (btnConfirm) {
                if (typeof onConfirm === 'function') {
                    btnConfirm.style.display = 'inline-block';
                    btnConfirm.innerText = '✓ 选定并绑定此片';
                    btnConfirm.onclick = function() {
                        closeModal('tmdbDetailModal');
                        onConfirm();
                    };
                } else if (idx < 0) {
                    btnConfirm.style.display = 'none';
                } else {
                    btnConfirm.style.display = 'inline-block';
                    btnConfirm.innerText = '✓ 选定并绑定此片';
                    btnConfirm.onclick = function() {
                        closeModal('tmdbDetailModal');
                        inlineSelectUnmatched(idx, rawVideo, isTmdb);
                    };
                }
            }

            // 立即打开弹窗 (ESC 可关闭)
            openModal('tmdbDetailModal');

            // 2. 如果是 TMDB，异步拉取超详细元数据（Backdrop, 演职员表, 剧情, 片长, 别名等）
            if (isTmdb && tmdbId > 0) {
                var detailApiUrl = isTv ? ('/api/tmdb/tv/' + tmdbId) : ('/api/tmdb/movie/' + tmdbId);
                fetch(detailApiUrl)
                    .then(function(res) { return res.json(); })
                    .then(function(dRes) {
                        var d = (dRes && dRes.data) ? dRes.data : null;
                        if (!d) return;

                        var fullInfo = extractFullTmdbVodInfo(d);

                        // 更新主片名与原名
                        var tZh = d.title || d.name || rawVideo.title;
                        var tOrig = d.original_title || d.original_name || rawVideo.originalTitle;
                        document.getElementById('tmdbMainTitle').innerText = tZh;
                        if (tOrig && tOrig !== tZh) {
                            document.getElementById('tmdbOriginalTitle').innerText = tOrig;
                        }

                        // 渲染别名/又名列表 (过滤掉当前主片名与外文原名)
                        var cleanAliases = (fullInfo.alias || []).filter(function(a) {
                            var lower = (a || '').toLowerCase();
                            return lower && lower !== (tZh || '').toLowerCase() && lower !== (tOrig || '').toLowerCase();
                        });
                        renderTmdbAliasBadges(cleanAliases, document.getElementById('tmdbAliasList'), document.getElementById('tmdbAliasRow'));

                        // 更新海报与背景图
                        if (d.poster_path) {
                            posterImg.src = formatProxiedImgUrl('https://image.tmdb.org/t/p/w500' + d.poster_path);
                        }
                        if (d.backdrop_path && backdropEl) {
                            backdropEl.style.backgroundImage = 'url("' + formatProxiedImgUrl('https://image.tmdb.org/t/p/w1280' + d.backdrop_path) + '")';
                        }

                        // 评分
                        if (d.vote_average) {
                            var voteCount = d.vote_count ? ' (' + d.vote_count + ' 人评价)' : '';
                            document.getElementById('tmdbRatingText').innerText = d.vote_average.toFixed(1) + ' 分' + voteCount;
                        }

                        // 元数据胶囊
                        var pillsHtml = '';
                        if (fullInfo.stime) pillsHtml += '<span class="status-badge" style="background:rgba(255,255,255,0.1);color:#fff;">📅 ' + fullInfo.stime + '</span>';
                        if (fullInfo.times) pillsHtml += '<span class="status-badge" style="background:rgba(255,255,255,0.1);color:#fff;">⏱️ ' + fullInfo.times + '</span>';
                        if (fullInfo.area) pillsHtml += '<span class="status-badge" style="background:rgba(255,255,255,0.1);color:#fff;">🌍 ' + fullInfo.area + '</span>';
                        if (fullInfo.language) pillsHtml += '<span class="status-badge" style="background:rgba(255,255,255,0.1);color:#fff;">🗣️ ' + fullInfo.language + '</span>';
                        if (fullInfo.tags && fullInfo.tags.length > 0) {
                            fullInfo.tags.forEach(function(tag) {
                                pillsHtml += '<span class="status-badge" style="background:rgba(99,102,241,0.2);color:#a5b4fc;border:1px solid rgba(99,102,241,0.3);">' + tag + '</span>';
                            });
                        }
                        document.getElementById('tmdbMetaPills').innerHTML = pillsHtml;

                        // 剧情概要
                        var overview = d.overview || rawVideo.content || '暂无详细中文剧情介绍。';
                        document.getElementById('tmdbOverviewText').innerText = overview;

                        // 导演与编剧
                        document.getElementById('tmdbDirectorText').innerText = fullInfo.director || '-';
                        if (fullInfo.bianju) {
                            document.getElementById('tmdbWriterRow').style.display = 'block';
                            document.getElementById('tmdbWriterText').innerText = fullInfo.bianju;
                        }

                        // 演员头像与角色横向滚动列表
                        var castList = (d.credits && d.credits.cast) || [];
                        if (castList.length > 0) {
                            var castHtml = '';
                            for (var i = 0; i < Math.min(castList.length, 12); i++) {
                                var actor = castList[i];
                                var aImg = actor.profile_path ? formatProxiedImgUrl('https://image.tmdb.org/t/p/w185' + actor.profile_path) : '';
                                castHtml += '<div style="flex-shrink:0;width:76px;text-align:center;">';
                                if (aImg) {
                                    castHtml += '<img referrerpolicy="no-referrer" src="' + aImg + '" style="width:64px;height:64px;border-radius:50%;object-fit:cover;margin:0 auto 4px;display:block;box-shadow:0 2px 6px rgba(0,0,0,0.5);border:1px solid rgba(255,255,255,0.15);">';
                                } else {
                                    castHtml += '<div style="width:64px;height:64px;border-radius:50%;background:#1e293b;margin:0 auto 4px;display:flex;align-items:center;justify-content:center;font-size:22px;border:1px solid rgba(255,255,255,0.1);">👤</div>';
                                }
                                castHtml += '<div style="font-size:11px;font-weight:600;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="' + actor.name + '">' + actor.name + '</div>';
                                if (actor.character) {
                                    castHtml += '<div style="font-size:10px;color:var(--text-muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="' + actor.character + '">' + actor.character + '</div>';
                                }
                                castHtml += '</div>';
                            }
                            document.getElementById('tmdbCastList').innerHTML = castHtml;
                        } else {
                            document.getElementById('tmdbCastList').innerHTML = '<div style="font-size:12px;color:var(--text-muted);padding:8px;">暂无演职员照片数据</div>';
                        }
                    })
                    .catch(function(err) {
                        console.warn('[TMDB Preview] 详情加载异常:', err);
                    });
            } else {
                // 云端影视条目展示
                document.getElementById('tmdbMetaPills').innerHTML = '<span class="status-badge" style="background:rgba(16,185,129,0.2);color:#6ee7b7;">云端自建/共享收录条目</span>';
                document.getElementById('tmdbCastList').innerHTML = '<div style="font-size:12px;color:#cbd5e1;padding:8px;">主演：' + (rawVideo.starring || '暂无') + '</div>';
                if (rawVideo.alias && Array.isArray(rawVideo.alias) && rawVideo.alias.length > 0) {
                    var cleanAliases = rawVideo.alias.filter(function(a) {
                        var lower = (a || '').toLowerCase();
                        return lower && lower !== (rawVideo.title || '').toLowerCase() && lower !== (rawVideo.originalTitle || '').toLowerCase();
                    });
                    renderTmdbAliasBadges(cleanAliases, document.getElementById('tmdbAliasList'), document.getElementById('tmdbAliasRow'));
                }
            }
        }

        function inlineSelectUnmatched(idx, vData, isTmdbSource) {
            var rawVideo = (typeof vData === 'string') ? JSON.parse(decodeURIComponent(vData)) : vData;
            var item = state.excelUnmatched[idx];
            if (!item) return;

            var cleanedTarget = cleanSeasonFromTitle(rawVideo.title);
            var cleanTitle = cleanedTarget.title || rawVideo.title;
            // 严格判断目标是否为连续剧集 (TV)
            var isTv = (cleanedTarget.season >= 0) || isSeriesTypeId(rawVideo.typeId) || (rawVideo.media_type === 'tv');
            var targetTypeId = isTv ? 2 : (rawVideo.typeId || 1);
            var isMovie = (targetTypeId === 1) || !isTv;

            var targetSeason = isMovie ? null : ((item.season !== undefined && item.season !== null && item.season >= 0) ? item.season : ((cleanedTarget.season >= 0) ? cleanedTarget.season : 1));
            var targetEpisode = isMovie ? null : (item.episode || 1);

            var targetVideo = {
                id: rawVideo.id || 0,
                title: cleanTitle,
                originalTitle: rawVideo.originalTitle || '',
                pic: rawVideo.pic || '',
                backdropPath: rawVideo.backdropPath || '',
                year: String(rawVideo.year || ''),
                typeId: targetTypeId,
                director: rawVideo.director || '',
                starring: rawVideo.starring || '',
                bianju: '',
                tags: [],
                area: '',
                language: '',
                stime: '',
                times: '',
                alias: [],
                content: rawVideo.content || '',
                remark: rawVideo.remark || '',
                tmdbId: rawVideo.tmdbId || 0
            };

            // 第一轨：本地私有库秒级生效
            state.excelMatched.push({
                key: item.key,
                raw: item.raw,
                extractedTitle: targetVideo.title,
                extractedYear: targetVideo.year,
                extractedRemark: item.extractedRemark,
                season: targetSeason,
                episode: targetEpisode,
                video: targetVideo,
                parentFolderName: item.parentFolderName || (item.raw && item.raw.parentFolderName) || '',
                matchType: 'manual'
            });

            state.excelUnmatched.splice(idx, 1);
            var successMsg = isMovie ? ('已成功绑定电影《' + targetVideo.title + '》并移入已匹配列表！') : ('已成功绑定《' + targetVideo.title + '》并移入已匹配列表！');
            showToast(successMsg);

            // 级联同剧推荐：严格仅当确认为剧集时才执行，电影坚决不执行同剧分集级联推荐！
            if (isTv && !isMovie) {
                var parentFolder = item.parentFolderName || (item.raw && item.raw.parentFolderName) || '';
                var curTitle = (item.extractedTitle || (item.raw && item.raw.rawTitle) || '').toLowerCase().trim();
                var meaningfulParent = resolveMeaningfulSeriesFolder(parentFolder);
                var remainingSameSeriesIndices = [];

                for (var r = 0; r < state.excelUnmatched.length; r++) {
                    var other = state.excelUnmatched[r];
                    var otherFolder = other.parentFolderName || (other.raw && other.raw.parentFolderName) || '';
                    var otherTitle = (other.extractedTitle || (other.raw && other.raw.rawTitle) || '').toLowerCase().trim();
                    var meaningfulOther = resolveMeaningfulSeriesFolder(otherFolder);

                    // 1. 同名剧集（必须有具体片名且非弱标题）
                    var sameTitle = (curTitle && otherTitle && curTitle === otherTitle && !isWeakSeriesTitle(curTitle));
                    // 2. 属于同一个明确的剧集专属目录（过滤掉“电影”、“新建文件夹”等弱目录），且该目录具名
                    var sameSpecificDir = (meaningfulParent && meaningfulOther && meaningfulParent.toLowerCase() === meaningfulOther.toLowerCase() && !isWeakSeriesTitle(meaningfulParent));

                    if (sameTitle || sameSpecificDir) {
                        remainingSameSeriesIndices.push(r);
                    }
                }

                if (remainingSameSeriesIndices.length > 0) {
                    if (confirm('🎉 已成功绑定当前分集！\n\n💡 系统检测到待确认列表中还有 ' + remainingSameSeriesIndices.length + ' 个属于剧集【' + targetVideo.title + '】的同剧分集。\n是否一键将这 ' + remainingSameSeriesIndices.length + ' 个分集全部绑定并转入已匹配列表？')) {
                        var toMove = [];
                        remainingSameSeriesIndices.sort(function(a, b) { return b - a; });
                        for (var m = 0; m < remainingSameSeriesIndices.length; m++) {
                            var mIdx = remainingSameSeriesIndices[m];
                            var subItem = state.excelUnmatched.splice(mIdx, 1)[0];
                            toMove.push(subItem);
                        }
                        for (var k = 0; k < toMove.length; k++) {
                            var itm = toMove[k];
                            var subSeason = (itm.season !== undefined && itm.season !== null && itm.season >= 0) ? itm.season : (targetSeason || 1);
                            state.excelMatched.push({
                                key: itm.key,
                                raw: itm.raw,
                                extractedTitle: targetVideo.title,
                                extractedYear: targetVideo.year,
                                extractedRemark: itm.extractedRemark,
                                season: subSeason,
                                episode: itm.episode || 1,
                                video: targetVideo,
                                parentFolderName: itm.parentFolderName || (itm.raw && itm.raw.parentFolderName) || '',
                                matchType: 'manual'
                            });
                        }
                        showToast('🎉 成功将同剧剩余 ' + toMove.length + ' 个分集全部绑定并转入已匹配列表！');
                    }
                }
            }

            renderExcelMatchedTable();
            renderExcelUnmatched();
            document.getElementById('btnConfirmBatchImport').style.display = 'inline-flex';

            var nextTab = (state.excelUnmatched.length === 0) ? 'matched' : 'unmatched';
            updateExcelTabCounts(nextTab);

            // 第二轨：零开销众包回传与 SHA 指纹自动绑定
            var itemSha = (item.raw && item.raw.sha) ? item.raw.sha : (item.sha || '');
            var itemSize = (item.raw && item.raw.fileSize) ? item.raw.fileSize : 0;
            var itemFileName = (item.raw && item.raw.rawFileName) ? item.raw.rawFileName : '';
            var lType = 'pan';
            var u = (item.raw && item.raw.linkUrl) ? item.raw.linkUrl.trim() : '';
            var lower = u.toLowerCase();
            if (lower.indexOf('magnet:?') === 0) lType = 'magnet';
            else if (lower.indexOf('ed2k://') === 0) lType = 'ed2k';
            else if (lower.indexOf('http://') === 0 || lower.indexOf('https://') === 0) {
                if (!isPanShareLink(lower)) lType = 'http';
            }

            if (isTmdbSource && targetVideo.tmdbId > 0) {
                // 异步获取 TMDB 完整演职员、国家、语言、编剧与上映详情，并一并回传 SHA
                fetch('/api/tmdb/movie/' + targetVideo.tmdbId)
                    .then(function(res) { return res.json(); })
                    .then(function(tData) {
                        var details = (tData && tData.data) ? tData.data : null;
                        var fullInfo = extractFullTmdbVodInfo(details);

                        // 补齐字段
                        targetVideo.director = fullInfo.director || targetVideo.director;
                        targetVideo.starring = fullInfo.starring || targetVideo.starring;
                        targetVideo.bianju = fullInfo.bianju || '';
                        targetVideo.tags = fullInfo.tags || [];
                        targetVideo.area = fullInfo.area || '';
                        targetVideo.language = fullInfo.language || '';
                        targetVideo.stime = fullInfo.stime || '';
                        targetVideo.times = fullInfo.times || '';
                        targetVideo.alias = fullInfo.alias || [];

                        var contributePayload = {
                            tmdb_id: targetVideo.tmdbId,
                            title: targetVideo.title,
                            original_title: targetVideo.originalTitle || '',
                            year: targetVideo.year ? parseInt(targetVideo.year) : null,
                            type_id: targetVideo.typeId,
                            pic: targetVideo.pic,
                            backdrop_path: targetVideo.backdropPath,
                            director: targetVideo.director,
                            starring: targetVideo.starring,
                            bianju: targetVideo.bianju,
                            tags: targetVideo.tags,
                            area: targetVideo.area,
                            language: targetVideo.language,
                            stime: targetVideo.stime,
                            times: targetVideo.times,
                            alias: targetVideo.alias,
                            content: targetVideo.content,
                            remark: targetVideo.remark,
                            sha: itemSha,
                            file_name: itemFileName,
                            file_size: itemSize,
                            links: u ? [{
                                link_type: lType,
                                url: u,
                                remark: item.extractedRemark || '众包导入链接',
                                sha: itemSha,
                                file_name: itemFileName,
                                file_size: itemSize
                            }] : []
                        };

                        return fetch('/api/mv/videos/contribute-from-tmdb', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(contributePayload)
                        });
                    })
                    .then(function(res) { return res.json(); })
                    .then(function(cRes) {
                        if (cRes && cRes.success && cRes.data && cRes.data.vod_id) {
                            targetVideo.id = cRes.data.vod_id;
                            console.log('[TMDB 众包收录] 完整元数据与 SHA 指纹已成功入库, 云端 vod_id:', cRes.data.vod_id, 'SHA:', itemSha);
                        }
                    })
                    .catch(function(err) {
                        console.warn('[TMDB 众包收录] 详情补齐或提交异常 (不影响本地私有库正常使用):', err);
                    });
            } else if (itemSha) {
                // 已有云端影视条目，若携带 SHA，也异步调用 contribute-from-tmdb 顺带补全 SHA 映射
                fetch('/api/mv/videos/contribute-from-tmdb', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        tmdb_id: targetVideo.tmdbId || 0,
                        title: targetVideo.title,
                        original_title: targetVideo.originalTitle || '',
                        year: targetVideo.year ? parseInt(targetVideo.year) : null,
                        type_id: targetVideo.typeId || 1,
                        sha: itemSha,
                        file_name: itemFileName,
                        file_size: itemSize,
                        links: u ? [{
                            link_type: lType,
                            url: u,
                            remark: item.extractedRemark || '众包导入链接',
                            sha: itemSha,
                            file_name: itemFileName,
                            file_size: itemSize
                        }] : []
                    })
                }).then(function(res) { return res.json(); })
                .then(function(cRes) {
                    if (cRes && cRes.success) {
                        console.log('[SHA 众包指纹] 已成功关联已有影视:', targetVideo.title, 'SHA:', itemSha);
                    }
                }).catch(function(err) {
                    console.warn('[SHA 众包指纹] 关联异常 (不影响本地私有库正常使用):', err);
                });
            }
        }

        // 7.5 自建独立影片入库支持 (无需刮削，自由命名)
        var activeCustomIndex = -1;

        function generateGradientCover(title, year) {
            try {
                var canvas = document.createElement('canvas');
                canvas.width = 400;
                canvas.height = 600;
                var ctx = canvas.getContext('2d');

                var grad = ctx.createLinearGradient(0, 0, 400, 600);
                grad.addColorStop(0, '#1e1b4b');
                grad.addColorStop(0.5, '#0f172a');
                grad.addColorStop(1, '#090d16');
                ctx.fillStyle = grad;
                ctx.fillRect(0, 0, 400, 600);

                ctx.strokeStyle = 'rgba(255, 255, 255, 0.12)';
                ctx.lineWidth = 4;
                ctx.strokeRect(16, 16, 368, 568);

                ctx.font = '64px sans-serif';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillText('🎬', 200, 210);

                ctx.fillStyle = '#f8fafc';
                ctx.font = 'bold 24px sans-serif';
                var displayTitle = (title || '自建影片').trim();
                if (displayTitle.length > 13) {
                    var line1 = displayTitle.slice(0, 11);
                    var line2 = displayTitle.slice(11, 23);
                    if (displayTitle.length > 23) line2 += '...';
                    ctx.fillText(line1, 200, 310);
                    ctx.fillText(line2, 200, 350);
                } else {
                    ctx.fillText(displayTitle, 200, 330);
                }

                if (year) {
                    ctx.fillStyle = '#94a3b8';
                    ctx.font = '500 17px sans-serif';
                    ctx.fillText(year + ' 年', 200, 410);
                }

                ctx.fillStyle = '#10b981';
                ctx.font = 'bold 13px sans-serif';
                ctx.fillText('• 自建影视特别收录 •', 200, 480);

                return canvas.toDataURL('image/jpeg', 0.85);
            } catch (e) {
                return '';
            }
        }

        function updateCustomPosterPreview(url) {
            var imgEl = document.getElementById('customPosterPreviewImg');
            var placeholder = document.getElementById('customPosterPlaceholder');
            if (url) {
                imgEl.src = url;
                imgEl.style.display = 'block';
                placeholder.style.display = 'none';
            } else {
                imgEl.src = '';
                imgEl.style.display = 'none';
                placeholder.style.display = 'block';
            }
        }

        function updateCustomPosterPreviewIfEmpty() {
            var currentCover = (document.getElementById('customMovieCover').value || '').trim();
            if (currentCover) return;
            var t = (document.getElementById('customMovieTitle').value || '').trim();
            var y = (document.getElementById('customMovieYear').value || '').trim();
            if (t) {
                var autoCover = generateGradientCover(t, y);
                updateCustomPosterPreview(autoCover);
            } else {
                updateCustomPosterPreview('');
            }
        }

        function handleCustomMovieCoverInput(val) {
            val = (val || '').trim();
            if (val) {
                updateCustomPosterPreview(val);
            } else {
                updateCustomPosterPreviewIfEmpty();
            }
        }

        function triggerCustomPosterUpload() {
            var fileInput = document.getElementById('customPosterFileInput');
            if (fileInput) fileInput.click();
        }

        function handleCustomPosterFileSelect(input) {
            if (!input || !input.files || input.files.length === 0) return;
            var file = input.files[0];
            uploadCustomPosterFile(file);
            input.value = '';
        }

        function uploadCustomPosterFile(file) {
            if (!file) return;
            if (file.type && !file.type.startsWith('image/')) {
                showToast('请选择有效的图片文件 (JPG/PNG/WebP/GIF)');
                return;
            }

            var overlay = document.getElementById('customPosterUploadOverlay');
            if (overlay) overlay.style.display = 'flex';

            var formData = new FormData();
            formData.append('file', file);

            fetch('/api/private/upload_poster', {
                method: 'POST',
                body: formData
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (overlay) overlay.style.display = 'none';
                if (data.success && data.data && data.data.url) {
                    var uploadedUrl = data.data.url;
                    document.getElementById('customMovieCover').value = uploadedUrl;
                    updateCustomPosterPreview(uploadedUrl);
                    showToast('🎉 海报上传成功！已自动关联至本片');
                } else {
                    throw new Error(data.message || data.error || '上传失败');
                }
            })
            .catch(function(err) {
                if (overlay) overlay.style.display = 'none';
                showToast('海报上传异常: ' + err.message);
            });
        }

        function openCustomMovieModal(idx) {
            activeCustomIndex = idx;
            var item = state.excelUnmatched[idx];
            if (!item) return;

            var titleInput = document.getElementById('unmatch_title_' + idx);
            var currentTitle = titleInput ? titleInput.value.trim() : (item.extractedTitle || '');
            var currentYear = (document.getElementById('unmatch_year_' + idx) ? document.getElementById('unmatch_year_' + idx).value.trim() : '') || item.extractedYear || '';

            document.getElementById('customMovieTitle').value = currentTitle || (item.raw && item.raw.rawFileName) || '';
            document.getElementById('customMovieYear').value = currentYear;
            document.getElementById('customMovieType').value = (item.raw && item.raw.rawFileName && (item.raw.rawFileName.indexOf('S0') >= 0 || item.raw.rawFileName.indexOf('EP') >= 0)) ? '2' : '1';
            document.getElementById('customMovieRemark').value = item.extractedRemark || '特典花絮';
            document.getElementById('customMovieCover').value = '';
            document.getElementById('customMovieSummary').value = '光盘特别收录 / 特典资源';

            // 预渲染默认海报预览
            updateCustomPosterPreviewIfEmpty();

            openModal('customMovieModal');
        }

        function submitCustomMovie() {
            if (activeCustomIndex < 0 || !state.excelUnmatched[activeCustomIndex]) {
                closeModal('customMovieModal');
                return;
            }

            var idx = activeCustomIndex;
            var item = state.excelUnmatched[idx];

            var title = (document.getElementById('customMovieTitle').value || '').trim();
            if (!title) {
                showToast('请填写影视片名');
                return;
            }
            var year = (document.getElementById('customMovieYear').value || '').trim();
            var typeId = parseInt(document.getElementById('customMovieType').value) || 1;
            var remark = (document.getElementById('customMovieRemark').value || '').trim() || item.extractedRemark || '特典花絮';
            var coverUrl = (document.getElementById('customMovieCover').value || '').trim();
            var summary = (document.getElementById('customMovieSummary').value || '').trim();

            if (!coverUrl) {
                coverUrl = generateGradientCover(title, year);
            }

            var customVideo = {
                id: 0,
                title: title,
                originalTitle: '',
                pic: coverUrl,
                backdropPath: '',
                year: year,
                typeId: typeId,
                director: '自建特别收录',
                starring: '',
                bianju: '',
                tags: ['特别收录', '花絮'],
                area: '',
                language: '',
                stime: year ? year + '-01-01' : '',
                times: '',
                alias: [],
                content: summary || '用户自建特别收录资源',
                remark: remark,
                tmdbId: 0
            };

            var isCustomTv = isSeriesTypeId(typeId);
            var isCustomMovie = !isCustomTv;

            // 移入已匹配列表
            state.excelMatched.push({
                key: item.key,
                raw: item.raw,
                extractedTitle: customVideo.title,
                extractedYear: customVideo.year,
                extractedRemark: remark,
                season: isCustomMovie ? null : (item.season || 1),
                episode: isCustomMovie ? null : (item.episode || 1),
                video: customVideo,
                parentFolderName: item.parentFolderName || (item.raw && item.raw.parentFolderName) || '',
                matchType: 'manual'
            });

            state.excelUnmatched.splice(idx, 1);
            closeModal('customMovieModal');
            var successMsg = isCustomMovie ? ('🎉 已成功将电影《' + customVideo.title + '》作为自建条目移入待入库清单！') : ('🎉 已成功将《' + customVideo.title + '》作为自建条目移入待入库清单！');
            showToast(successMsg);

            // 级联同剧推荐：严格仅当确认为剧集时才执行，电影坚决不执行同剧推荐！
            if (isCustomTv && !isCustomMovie) {
                var parentFolder = item.parentFolderName || (item.raw && item.raw.parentFolderName) || '';
                var curTitle = (item.extractedTitle || (item.raw && item.raw.rawTitle) || '').toLowerCase().trim();
                var meaningfulParent = resolveMeaningfulSeriesFolder(parentFolder);
                var remainingSameSeriesIndices = [];

                for (var r = 0; r < state.excelUnmatched.length; r++) {
                    var other = state.excelUnmatched[r];
                    var otherFolder = other.parentFolderName || (other.raw && other.raw.parentFolderName) || '';
                    var otherTitle = (other.extractedTitle || (other.raw && other.raw.rawTitle) || '').toLowerCase().trim();
                    var meaningfulOther = resolveMeaningfulSeriesFolder(otherFolder);

                    var sameTitle = (curTitle && otherTitle && curTitle === otherTitle && !isWeakSeriesTitle(curTitle));
                    var sameSpecificDir = (meaningfulParent && meaningfulOther && meaningfulParent.toLowerCase() === meaningfulOther.toLowerCase() && !isWeakSeriesTitle(meaningfulParent));

                    if (sameTitle || sameSpecificDir) {
                        remainingSameSeriesIndices.push(r);
                    }
                }

                if (remainingSameSeriesIndices.length > 0) {
                    if (confirm('🎉 已成功将当前分集作为自建条目移入待入库清单！\n\n💡 系统检测到待确认列表中还有 ' + remainingSameSeriesIndices.length + ' 个属于剧集【' + customVideo.title + '】的同剧分集。\n是否一键将这 ' + remainingSameSeriesIndices.length + ' 个分集全部以此自建条目转入已匹配列表？')) {
                        var toMove = [];
                        remainingSameSeriesIndices.sort(function(a, b) { return b - a; });
                        for (var m = 0; m < remainingSameSeriesIndices.length; m++) {
                            var mIdx = remainingSameSeriesIndices[m];
                            var subItem = state.excelUnmatched.splice(mIdx, 1)[0];
                            toMove.push(subItem);
                        }
                        for (var k = 0; k < toMove.length; k++) {
                            var itm = toMove[k];
                            state.excelMatched.push({
                                key: itm.key,
                                raw: itm.raw,
                                extractedTitle: customVideo.title,
                                extractedYear: customVideo.year,
                                extractedRemark: itm.extractedRemark,
                                season: itm.season || item.season || 1,
                                episode: itm.episode || 1,
                                video: customVideo,
                                parentFolderName: itm.parentFolderName || (itm.raw && itm.raw.parentFolderName) || '',
                                matchType: 'manual'
                            });
                        }
                        showToast('🎉 成功将同剧剩余 ' + toMove.length + ' 个分集全部以此自建条目转入已匹配列表！');
                    }
                }
            }

            renderExcelMatchedTable();
            renderExcelUnmatched();
            document.getElementById('btnConfirmBatchImport').style.display = 'inline-flex';

            var nextTab = (state.excelUnmatched.length === 0) ? 'matched' : 'unmatched';
            updateExcelTabCounts(nextTab);
        }

        // 绑定自建海报拖拽与剪贴板粘贴
        document.addEventListener('DOMContentLoaded', function() {
            var box = document.getElementById('customPosterBox');
            if (box) {
                box.addEventListener('dragover', function(e) {
                    e.preventDefault();
                    box.style.borderColor = '#38bdf8';
                });
                box.addEventListener('dragleave', function() {
                    box.style.borderColor = 'rgba(255,255,255,0.2)';
                });
                box.addEventListener('drop', function(e) {
                    e.preventDefault();
                    box.style.borderColor = 'rgba(255,255,255,0.2)';
                    if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                        uploadCustomPosterFile(e.dataTransfer.files[0]);
                    }
                });
            }

            var modal = document.getElementById('customMovieModal');
            if (modal) {
                modal.addEventListener('paste', function(e) {
                    var items = (e.clipboardData || (window.clipboardData && window.clipboardData.items) || {}).items;
                    if (!items) return;
                    for (var i = 0; i < items.length; i++) {
                        if (items[i].type && items[i].type.indexOf('image') !== -1) {
                            var blob = items[i].getAsFile();
                            if (blob) {
                                uploadCustomPosterFile(blob);
                                showToast('已从剪贴板捕获图片并正在上传...');
                                break;
                            }
                        }
                    }
                });
            }
        });

        // 8. 确认批量导入并自动聚合多版本
        function submitBatchImport() {
            if (state.excelMatched.length === 0 || !state.currentLib) return;

            var matchedCount = state.excelMatched.length;
            var unmatchedCount = state.excelUnmatched.length;

            if (unmatchedCount > 0) {
                var confirmMsg = '当前还有 ' + unmatchedCount + ' 条影片处于【待确认/需修正】状态（未匹配的条目将不会被导入）。\n\n提示：您可先点击【📥 导出待确认列表】保存至本地表格线下修改后重新导入。\n确定只导入已成功匹配的 ' + matchedCount + ' 部影片吗？';
                if (!confirm(confirmMsg)) {
                    return;
                }
            }

            // 同批次同片智能聚合多版本与链接去重
            var movieMap = {};
            var aggregatedMovies = [];
            var totalUniqueLinks = 0;

            for (var i = 0; i < state.excelMatched.length; i++) {
                var item = state.excelMatched[i];
                var v = item.video;
                var cleanedTitleObj = cleanSeasonFromTitle(v.title);
                var cleanMovieTitle = cleanedTitleObj.title || v.title;
                var detectedSeason = (cleanedTitleObj.season >= 0) ? cleanedTitleObj.season : -1;
                var isTv = isSeriesTypeId(v.typeId) || (item.season >= 0 && item.episode > 0) || (item.season > 0) || (item.episode > 0) || (detectedSeason >= 0);

                // 核心修复：聚合 MapKey 生成策略（同一电视剧的所有季必须聚合在同一个影片条目下，绝不能按每季独立的 vod_id 或上映年份拆分）
                var effTmdbId = (v && (v.tmdbId || v.tmdb_id)) || item.tmdbId || 0;
                var mapKey = '';
                if (isTv) {
                    if (effTmdbId && effTmdbId > 0) {
                        mapKey = 'tv_tmdb_' + effTmdbId;
                    } else {
                        mapKey = 'tv_title_' + cleanMovieTitle.trim().toLowerCase();
                    }
                } else {
                    if (effTmdbId && effTmdbId > 0) {
                        mapKey = 'mov_tmdb_' + effTmdbId;
                    } else if (v.id) {
                        mapKey = 'mov_id_' + v.id;
                    } else {
                        mapKey = 'mov_title_' + cleanMovieTitle.trim().toLowerCase() + '_' + (v.year || '').trim();
                    }
                }

                if (!movieMap[mapKey]) {
                    movieMap[mapKey] = {
                        video: v,
                        cleanTitle: cleanMovieTitle,
                        isTv: isTv,
                        tmdbId: effTmdbId,
                        links: [],
                        urlSet: {}
                    };
                    aggregatedMovies.push(movieMap[mapKey]);
                } else {
                    // 同一部剧的多季元数据合并：保留最早的首播年，补全海报与简介
                    var existV = movieMap[mapKey].video;
                    if (v.year && (!existV.year || String(v.year) < String(existV.year))) {
                        existV.year = v.year;
                    }
                    if (!existV.pic && v.pic) existV.pic = v.pic;
                    if (!existV.content && v.content) existV.content = v.content;
                }

                if (item.raw.linkUrl) {
                    var u = item.raw.linkUrl.trim();
                    if (u && !movieMap[mapKey].urlSet[u]) {
                        movieMap[mapKey].urlSet[u] = true;

                        var lType = 'pan';
                        var lower = u.toLowerCase();
                        if (lower.indexOf('magnet:?') === 0) lType = 'magnet';
                        else if (lower.indexOf('ed2k://') === 0) lType = 'ed2k';
                        else if (lower.indexOf('user_pan://') === 0) lType = 'user_pan';
                        else if (lower.indexOf('http://') === 0 || lower.indexOf('https://') === 0) {
                            if (!isPanShareLink(lower)) lType = 'http';
                        }

                        var sNum = 0;
                        var eNum = 0;
                        if (isTv) {
                            if (item.season !== undefined && item.season !== null && item.season >= 0) {
                                sNum = item.season;
                            } else if (detectedSeason >= 0) {
                                sNum = detectedSeason;
                            } else {
                                sNum = 1;
                            }
                            eNum = item.episode || 1;
                        }

                        var fSize = (item.raw && (item.raw.fileSize || item.raw.file_size || item.raw.size)) || item.fileSize || 0;
                        var fId = (item.raw && (item.raw.fileId || item.raw.file_id || item.raw.id)) || '';
                        if (fId && fId.indexOf('eyJ') !== -1) {
                            try {
                                var dec = JSON.parse(atob(fId));
                                if (dec && (dec.fid || dec.file_id || dec.target_id || dec.fs_id)) {
                                    fId = String(dec.fid || dec.file_id || dec.target_id || dec.fs_id);
                                }
                            } catch (e) {}
                        }
                        var fName = (item.raw && (item.raw.rawFileName || item.raw.raw_file_name || item.raw.fileName || item.raw.name)) || '';
                        var fSha = (item.raw && item.raw.sha) || item.sha || '';
                        var pName = (item.raw && (item.raw.provider || item.raw.panName)) || '';
                        if (!pName && lType === 'user_pan') {
                            var pMatch = u.match(/^user_pan:\/\/([^\/]+)/i);
                            if (pMatch) pName = pMatch[1];
                        }
                        if (!fId && lType === 'user_pan') {
                            var fMatch = u.match(/^user_pan:\/\/[^\/]+\/(.+)$/i);
                            if (fMatch) fId = fMatch[1];
                        }

                        if (fSize > 0 && isPanShareLink(u) && u.indexOf('&size=') === -1 && u.indexOf('?size=') === -1) {
                            u += (u.indexOf('#') !== -1 ? '&size=' : '#size=') + fSize;
                        }

                        var pFolder = (item.raw && (item.raw.parentFolderPath || item.raw.parent_folder_path || item.raw.parentFolderName || item.raw.parent_folder_name)) || '';
                        movieMap[mapKey].links.push({
                            link_type: lType,
                            provider: pName,
                            url: u,
                            password: (item.raw && item.raw.password) || '',
                            remark: item.extractedRemark || '批量导入链接',
                            parent_folder_path: pFolder,
                            parent_folder_name: pFolder,
                            file_id: fId,
                            file_name: fName,
                            file_size: fSize,
                            sha1: fSha,
                            season_number: sNum,
                            episode_number: eNum,
                            episode_title: item.episodeTitle || ''
                        });
                        totalUniqueLinks++;
                    }
                }
            }

            // 组装批量入库 payload (单次极速事务提交)
            var batchPayload = [];
            for (var j = 0; j < aggregatedMovies.length; j++) {
                var entry = aggregatedMovies[j];
                var v = entry.video;
                var hasEpisodes = false;
                for (var lkI = 0; lkI < entry.links.length; lkI++) {
                    if (entry.links[lkI].season_number > 0 || entry.links[lkI].episode_number > 0 || (entry.links[lkI].season_number === 0 && entry.links[lkI].episode_number > 0)) {
                        hasEpisodes = true;
                    }
                }
                var finalTypeId = (v.typeId === 2 || hasEpisodes) ? 2 : (v.typeId || 1);

                var areaVal = v.area || '';
                if (!areaVal && v.country) areaVal = v.country;
                if (!areaVal && v.origin_country) {
                    areaVal = Array.isArray(v.origin_country) ? v.origin_country.join('/') : String(v.origin_country);
                }
                if (areaVal) {
                    areaVal = mapCountryCodeToArea('', areaVal);
                }

                batchPayload.push({
                    vod_id: String(v.id || ''),
                    tmdb_id: (v.tmdbId || v.tmdb_id || entry.tmdbId || 0),
                    type_id: finalTypeId,
                    title: entry.cleanTitle || v.title,
                    year: String(v.year || ''),
                    cover_url: v.pic || '',
                    backdrop_url: formatBackdropUrl(v.backdropPath || v.backdrop_path || ''),
                    summary: v.content || '',
                    genres: Array.isArray(v.tags) ? v.tags.join(',') : '',
                    directors: v.director || '',
                    actors: v.starring || '',
                    area: areaVal,
                    links: entry.links
                });
            }

            var isUpdateMode = false;
            var chkUpdate = document.getElementById('chkExcelUpdateMode');
            if (chkUpdate && chkUpdate.checked) {
                isUpdateMode = true;
            }

            var isSkipSha = false;
            var chkSkipSha = document.getElementById('chkExcelSkipShaDedup');
            if (chkSkipSha && chkSkipSha.checked) {
                isSkipSha = true;
            } else if (state.skipShaDedup) {
                isSkipSha = true;
            }

            var tipMsg = isUpdateMode 
                ? ('正在单事务更新入库 (覆盖模式) ' + batchPayload.length + ' 部影视...')
                : ('正在单事务极速入库 ' + batchPayload.length + ' 部影视...');
            showToast(tipMsg);
            var btnConfirm = document.getElementById('btnConfirmBatchImport');
            if (btnConfirm) {
                btnConfirm.disabled = true;
                btnConfirm.innerText = isUpdateMode ? '正在覆盖更新中...' : '正在入库中...';
            }

            var reqBody = { 
                movies: batchPayload,
                update_mode: isUpdateMode,
                skip_sha_dedup: isSkipSha
            };
            var hadPanSync = false;
            if (state.pendingPanSyncInfo) {
                reqBody.pan_sync_info = state.pendingPanSyncInfo;
                hadPanSync = true;
            }

            fetch('/api/private/libraries/' + state.currentLib.id + '/movies/batch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(reqBody)
            })
            .then(function(res) { return res.json(); })
            .then(function(resJson) {
                if (btnConfirm) {
                    btnConfirm.disabled = false;
                    btnConfirm.innerText = '确认导入已匹配影片';
                }
                if (resJson.success) {
                    var syncTip = hadPanSync ? '，并已开启115生活事件实时同步更新！' : '！';
                    var successText = isUpdateMode 
                        ? ('🎉 覆盖更新完成！已更新 ' + aggregatedMovies.length + ' 部影视，覆盖/更新 ' + totalUniqueLinks + ' 条链接' + syncTip)
                        : ('🎉 批量导入完成！已成功入库 ' + aggregatedMovies.length + ' 部影视，聚合 ' + totalUniqueLinks + ' 条多版本链接' + syncTip);
                    showToast(successText);
                    closeModal('excelModal');
                    resetImportSourceView();
                    loadMovies();
                } else {
                    throw new Error(resJson.error || resJson.message || '批量入库失败');
                }
            })
            .catch(function(err) {
                if (btnConfirm) {
                    btnConfirm.disabled = false;
                    btnConfirm.innerText = '确认导入已匹配影片';
                }
                showToast('批量导入失败: ' + err.message);
            });
        }



        // ------------------ 分享与同步 ------------------

        function openShareModal(libId) {
            var lib = null;
            if (libId) {
                for (var i = 0; i < state.libraries.length; i++) {
                    if (state.libraries[i].id === libId) { lib = state.libraries[i]; break; }
                }
            }
            if (!lib && state.currentLib) {
                lib = state.currentLib;
                libId = lib.id;
            }
            if (!lib) return;

            if (lib.share_type === 2) {
                showToast('🔒 持续更新型订阅媒体库不可二次发布或管理分享');
                return;
            }

            state.activeEditingLibId = libId;

            var movieCount = (lib.item_count !== undefined) ? lib.item_count : (state.movies ? state.movies.length : 0);
            if (!lib.share_code && movieCount <= 0) {
                showToast('媒体库内暂无影片，请先添加影视后再发布分享');
                return;
            }

            // 检查是否全部为个人网盘私有文件
            if (state.currentLib && state.currentLib.id === libId && state.movies && state.movies.length > 0) {
                var totalM = state.movies.length;
                var onlyUserPanCount = 0;
                for (var si = 0; si < totalM; si++) {
                    var sm = state.movies[si];
                    var uCount = 0;
                    var oCount = 0;
                    if (sm.links) {
                        for (var sl = 0; sl < sm.links.length; sl++) {
                            if (sm.links[sl].link_type === 'user_pan' || (sm.links[sl].url && sm.links[sl].url.indexOf('user_pan://') === 0)) {
                                uCount++;
                            } else {
                                oCount++;
                            }
                        }
                    }
                    if (uCount > 0 && oCount === 0) onlyUserPanCount++;
                }
                if (onlyUserPanCount === totalM) {
                    showToast('⚠️ 当前媒体库内全部为个人网盘私有文件，无有效公开分享链接，无法对外发布分享');
                    return;
                }
            }

            var btn = document.getElementById('btnPublishShare');
            var unpubBtn = document.getElementById('btnUnpublishShare');
            btn.style.display = 'inline-flex';

            if (lib.share_code) {
                document.getElementById('shareCodeDisplay').innerText = lib.share_code;
                document.getElementById('shareResultBox').style.display = 'block';
                btn.innerText = '🚀 推送更新至云端 (升级版本)';
                unpubBtn.style.display = 'inline-flex';
            } else {
                document.getElementById('shareResultBox').style.display = 'none';
                btn.innerText = '立即发布分享';
                unpubBtn.style.display = 'none';
            }
            if (authState.user && !document.getElementById('sharerNameInput').value) {
                document.getElementById('sharerNameInput').value = authState.user.nickname || authState.user.username;
            }
            openModal('shareModal');
        }

        function updateShareProgress(percent, batchText, subText, title) {
            var bar = document.getElementById('shareProgressBar');
            var pEl = document.getElementById('shareProgressPercent');
            var bEl = document.getElementById('shareProgressBatchText');
            var sEl = document.getElementById('shareProgressSubtitle');
            var tEl = document.getElementById('shareProgressTitle');

            if (bar) bar.style.width = percent + '%';
            if (pEl) pEl.innerText = percent + '%';
            if (bEl && batchText) bEl.innerText = batchText;
            if (sEl && subText) sEl.innerText = subText;
            if (tEl && title) tEl.innerText = title;
        }

        function pruneMovieForCloud(m) {
            if (!m) return m;
            var copy = Object.assign({}, m);
            if (copy.links && Array.isArray(copy.links)) {
                copy.links = copy.links.filter(function(l) {
                    return l.link_type !== 'user_pan' && (!l.url || l.url.indexOf('user_pan://') !== 0);
                });
            }
            if (copy.extra_meta_json) {
                try {
                    var isSeries = checkIsSeries(m, m.links);
                    if (!isSeries || parseInt(m.type_id, 10) === 1) {
                        copy.extra_meta_json = '';
                    } else {
                        var meta = typeof copy.extra_meta_json === 'string' ? JSON.parse(copy.extra_meta_json) : copy.extra_meta_json;
                        if (meta && meta.seasons && Array.isArray(meta.seasons)) {
                            var slimSeasons = meta.seasons.map(function(s) {
                                return {
                                    season_number: s.season_number,
                                    name: s.name || ('第 ' + s.season_number + ' 季'),
                                    episode_count: s.episode_count || (s.episodes ? s.episodes.length : 0),
                                    poster_path: s.poster_path || ''
                                };
                            });
                            copy.extra_meta_json = JSON.stringify({ seasons: slimSeasons });
                        } else {
                            copy.extra_meta_json = '';
                        }
                    }
                } catch (e) {
                    copy.extra_meta_json = '';
                }
            } else {
                copy.extra_meta_json = '';
            }
            return copy;
        }

        async function submitPublishShare() {
            var libId = state.activeEditingLibId;
            var lib = null;
            for (var i = 0; i < state.libraries.length; i++) {
                if (state.libraries[i].id === libId) { lib = state.libraries[i]; break; }
            }
            if (!lib && state.currentLib && state.currentLib.id === libId) {
                lib = state.currentLib;
            }
            if (lib && lib.share_type === 2) {
                showToast('🔒 持续更新型订阅媒体库不可二次发布或管理分享');
                return;
            }

            var movieCount = (lib && lib.item_count !== undefined) ? lib.item_count : (state.movies ? state.movies.length : 0);
            if (!lib || (!lib.share_code && movieCount <= 0)) {
                showToast('媒体库内暂无影片，请先添加影视后再发布分享');
                return;
            }

            if (!authState.token) {
                showToast('发布分享需先登录账号');
                openAuthModal(function() {
                    submitPublishShare();
                });
                return;
            }

            var shareType = parseInt(document.getElementById('shareTypeSelect').value, 10);
            var isPublic = document.getElementById('sharePublicSelect').value === 'true';
            var creatorName = document.getElementById('sharerNameInput').value.trim();
            if (!creatorName && authState.user) {
                creatorName = authState.user.nickname || authState.user.username;
            }

            var isUpdate = Boolean(lib && lib.share_code);

            // 1. 打开实时进度弹窗
            openModal('shareProgressModal');
            updateShareProgress(0, '正在准备...', '正在读取本地媒体库影视数据...', isUpdate ? '正在推送更新至云端' : '正在同步发布共享媒体库');

            try {
                // 2. 读取当前媒体库的所有影视与链接
                var mRes = await fetch('/api/private/libraries/' + libId + '/movies');
                var mJson = await mRes.json();
                var allMovies = (mJson && mJson.data) ? mJson.data : [];

                if (!allMovies || allMovies.length === 0) {
                    closeModal('shareProgressModal');
                    showToast('媒体库内暂无影片');
                    return;
                }

                // 过滤个人网盘链接 (user_pan)
                var shareableMovies = [];
                var hasUserPanFiltered = false;
                for (var mi = 0; mi < allMovies.length; mi++) {
                    var mv = allMovies[mi];
                    var validLinks = [];
                    if (mv.links && mv.links.length > 0) {
                        for (var li = 0; li < mv.links.length; li++) {
                            var lk = mv.links[li];
                            if (lk.link_type === 'user_pan' || (lk.url && lk.url.indexOf('user_pan://') === 0)) {
                                hasUserPanFiltered = true;
                                continue;
                            }
                            validLinks.push(lk);
                        }
                    }
                    if (validLinks.length > 0) {
                        var mvCopy = Object.assign({}, mv);
                        mvCopy.links = validLinks;
                        mvCopy.has_user_pan = false;
                        shareableMovies.push(mvCopy);
                    } else {
                        hasUserPanFiltered = true;
                    }
                }

                if (shareableMovies.length === 0) {
                    closeModal('shareProgressModal');
                    if (hasUserPanFiltered) {
                        showToast('当前媒体库内全部为个人网盘私有文件，无有效公开分享链接，无法对外发布分享');
                    } else {
                        showToast('媒体库内暂无包含有效公开播放链接的影片，无法对外发布分享');
                    }
                    return;
                }
                allMovies = shareableMovies;

                var totalMovies = allMovies.length;

                if (!isUpdate) {
                    // --- 初次发布：三段式分批流式上传 ---
                    updateShareProgress(5, '初始化分享空间...', '正在创建专属 6 位分享码...', '正在同步发布共享媒体库');

                    // 阶段 1: 初始化会话
                    var initRes = await authFetch('/api/mv/shared-libraries/publish/init', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            name: lib.name,
                            coverUrl: lib.cover_url || '',
                            intro: '',
                            shareType: shareType,
                            isPublic: isPublic,
                            creatorName: creatorName,
                            totalMovies: totalMovies
                        })
                    });
                    if (!initRes.ok) {
                        var iErrTxt = await initRes.text();
                        try {
                            var iErrJson = JSON.parse(iErrTxt);
                            throw new Error(iErrJson.message || ('初始化失败 (' + initRes.status + ')'));
                        } catch(pe) {
                            throw new Error('初始化失败 (' + initRes.status + ')');
                        }
                    }
                    var initData = await initRes.json();
                    if (!initData.success || !initData.data || !initData.data.shareCode) {
                        throw new Error(initData.message || '初始化分享会话失败');
                    }

                    var shareCode = initData.data.shareCode;

                    // 阶段 2: 分批上传影片与链接 (每批 100 部，经过 pruneMovieForCloud 深度瘦身)
                    var BATCH_SIZE = 100;
                    var totalBatches = Math.ceil(totalMovies / BATCH_SIZE);

                    for (var bIdx = 0; bIdx < totalBatches; bIdx++) {
                        var start = bIdx * BATCH_SIZE;
                        var end = Math.min(start + BATCH_SIZE, totalMovies);
                        var batchChunk = allMovies.slice(start, end).map(pruneMovieForCloud);
                        var curProgress = Math.round(5 + ((bIdx + 1) / totalBatches) * 85);

                        updateShareProgress(
                            curProgress,
                            '第 ' + (bIdx + 1) + '/' + totalBatches + ' 批',
                            '正在上传第 ' + (bIdx + 1) + '/' + totalBatches + ' 批影视 (' + end + '/' + totalMovies + ' 部)...',
                            '正在同步发布共享媒体库'
                        );

                        // 单批上传 (带 3 次重试保护)
                        var retryCount = 0;
                        var successBatch = false;
                        while (retryCount < 3 && !successBatch) {
                            try {
                                var bRes = await authFetch('/api/mv/shared-libraries/' + shareCode + '/batch-movies', {
                                    method: 'POST',
                                    headers: { 'Content-Type': 'application/json' },
                                    body: JSON.stringify({
                                        movies: batchChunk,
                                        startIndex: start,
                                        version: 1
                                    })
                                });
                                if (!bRes.ok) {
                                    if (bRes.status === 413) {
                                        throw new Error('上传数据量超出网关限制 (413 Request Entity Too Large)');
                                    }
                                    var errTxt = await bRes.text();
                                    try {
                                        var errJson = JSON.parse(errTxt);
                                        throw new Error(errJson.message || ('批次上传失败 (HTTP ' + bRes.status + ')'));
                                    } catch(pe) {
                                        throw new Error('批次上传失败 (HTTP ' + bRes.status + ')');
                                    }
                                }
                                var bData = await bRes.json();
                                if (bData.success) {
                                    successBatch = true;
                                } else {
                                    throw new Error(bData.message || '批次上传失败');
                                }
                            } catch (bErr) {
                                retryCount++;
                                if (retryCount >= 3) throw bErr;
                                await new Promise(function(resolve) { setTimeout(resolve, 1000); });
                            }
                        }
                    }

                    // 阶段 3: 封包确认
                    updateShareProgress(95, '正在核算数据...', '正在完成数据封包校验...', '正在同步发布共享媒体库');
                    var commitRes = await authFetch('/api/mv/shared-libraries/' + shareCode + '/commit', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ totalMovies: totalMovies })
                    });
                    if (!commitRes.ok) {
                        var cErrTxt = await commitRes.text();
                        try {
                            var cErrJson = JSON.parse(cErrTxt);
                            throw new Error(cErrJson.message || '封包校验失败');
                        } catch(ce) {
                            throw new Error('封包校验请求失败 (HTTP ' + commitRes.status + ')');
                        }
                    }
                    var commitData = await commitRes.json();
                    if (!commitData.success) {
                        throw new Error(commitData.message || '封包校验失败');
                    }

                    // 阶段 4: 同步更新本地媒体库的 share_code
                    await fetch('/api/private/libraries/' + libId, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ share_code: shareCode, remote_version: 1 })
                    });
                    await fetch('/api/private/libraries/' + libId + '/commit_push', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ pushed_version: 1 })
                    });

                    updateShareProgress(100, '🎉 发布完成！', '媒体库已成功发布并生成分享码！', '发布成功');

                    setTimeout(function() {
                        closeModal('shareProgressModal');
                        document.getElementById('shareCodeDisplay').innerText = shareCode;
                        document.getElementById('shareResultBox').style.display = 'block';
                        document.getElementById('btnUnpublishShare').style.display = 'inline-flex';
                        document.getElementById('btnPublishShare').innerText = '🚀 推送更新至云端 (升级版本)';
                        showToast('发布共享成功！专属码: ' + shareCode);
                        loadLibraries();
                        if (state.currentLevel === 2) {
                            loadMovies();
                        }
                    }, 500);

                } else {
                    // --- 持续更新：推送增量变更 (Local Delta Push) ---
                    var shareCode = lib.share_code;
                    updateShareProgress(20, '检查本地变更...', '正在分析自上次推送以来的增量改动...', '正在推送更新至云端');

                    var deltaRes = await fetch('/api/private/libraries/' + libId + '/delta');
                    var deltaJson = await deltaRes.json();
                    var deltaData = (deltaJson && deltaJson.data) ? deltaJson.data : null;

                    if (!deltaData || !deltaData.has_changes) {
                        closeModal('shareProgressModal');
                        showToast('当前媒体库内容无任何新改动，无需重复推送');
                        return;
                    }

                    var changedMovies = (deltaData.changed_movies || []).map(pruneMovieForCloud);
                    var deletedMovieIds = deltaData.deleted_movie_ids || [];
                    var deletedLinkIds = deltaData.deleted_link_ids || [];

                    updateShareProgress(50, '正在推送增量...', '已捕获 ' + changedMovies.length + ' 部变更影片，' + deletedMovieIds.length + ' 部删除影片，正在同步至云端...', '正在推送更新至云端');

                    var curBaseVersion = lib.remote_version || 1;
                    var updRes = await authFetch('/api/mv/shared-libraries/update', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            shareCode: shareCode,
                            name: lib.name,
                            coverUrl: lib.cover_url || '',
                            intro: '',
                            isPublic: isPublic,
                            baseVersion: curBaseVersion,
                            changedMovies: changedMovies,
                            deletedMovieIds: deletedMovieIds,
                            deletedLinkIds: deletedLinkIds
                        })
                    });
                    if (!updRes.ok) {
                        if (updRes.status === 413) {
                            throw new Error('更新数据量超出网关限制 (413 Request Entity Too Large)');
                        }
                        var uErrTxt = await updRes.text();
                        try {
                            var uErrJson = JSON.parse(uErrTxt);
                            throw new Error(uErrJson.message || ('推送更新失败 (HTTP ' + updRes.status + ')'));
                        } catch(ue) {
                            throw new Error('推送更新失败 (HTTP ' + updRes.status + ')');
                        }
                    }
                    var updData = await updRes.json();

                    if (updData.code === 'VERSION_OUTDATED') {
                        // 检测到多设备并发协同冲突：云端在其他设备上已被升级
                        var remoteVer = updData.currentVersion || (curBaseVersion + 1);
                        updateShareProgress(65, '🔄 正在自动合流...', '检测到云端在其他设备上有新提交 (v' + remoteVer + ')，正在自动拉取并合并...', '正在自动合流');

                        // 步骤 1: 拉取云端增量并合并到本地
                        var syncRes = await fetch('/api/private/libraries/' + libId + '/sync', { method: 'POST' });
                        var syncJson = await syncRes.json();
                        if (!syncJson.success) {
                            throw new Error('自动合流拉取云端更新失败: ' + (syncJson.message || '未知错误'));
                        }

                        // 步骤 2: 重新获取合并后的本地 Delta
                        updateShareProgress(85, '正在提交本地变更...', '已完成云端新片单合流，正在提交本地新内容至云端...', '正在提交最终更新');
                        var reDeltaRes = await fetch('/api/private/libraries/' + libId + '/delta');
                        var reDeltaJson = await reDeltaRes.json();
                        var reDeltaData = (reDeltaJson && reDeltaJson.data) ? reDeltaJson.data : null;

                        var finalChangedMovies = (reDeltaData && reDeltaData.changed_movies) ? reDeltaData.changed_movies.map(pruneMovieForCloud) : [];
                        var finalDeletedMovieIds = (reDeltaData && reDeltaData.deleted_movie_ids) ? reDeltaData.deleted_movie_ids : [];
                        var finalDeletedLinkIds = (reDeltaData && reDeltaData.deleted_link_ids) ? reDeltaData.deleted_link_ids : [];

                        // 步骤 3: 使用更新后的基准版本再次推送
                        var reUpdRes = await authFetch('/api/mv/shared-libraries/update', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                shareCode: shareCode,
                                name: lib.name,
                                coverUrl: lib.cover_url || '',
                                intro: '',
                                isPublic: isPublic,
                                baseVersion: remoteVer,
                                changedMovies: finalChangedMovies,
                                deletedMovieIds: finalDeletedMovieIds,
                                deletedLinkIds: finalDeletedLinkIds
                            })
                        });
                        if (!reUpdRes.ok) {
                            if (reUpdRes.status === 413) {
                                throw new Error('更新数据量超出网关限制 (413 Request Entity Too Large)');
                            }
                            var ruErrTxt = await reUpdRes.text();
                            try {
                                var ruErrJson = JSON.parse(ruErrTxt);
                                throw new Error(ruErrJson.message || ('合流后重试推送失败 (HTTP ' + reUpdRes.status + ')'));
                            } catch(rue) {
                                throw new Error('合流后重试推送失败 (HTTP ' + reUpdRes.status + ')');
                            }
                        }
                        updData = await reUpdRes.json();
                        if (!updData.success) {
                            throw new Error(updData.message || '合流后重试推送失败');
                        }
                    } else if (!updData.success) {
                        throw new Error(updData.message || '推送更新失败');
                    }

                    var newVersion = (updData.data && updData.data.version) ? updData.data.version : ((lib.remote_version || 1) + 1);

                    // 确认提交本地推送状态
                    await fetch('/api/private/libraries/' + libId + '/commit_push', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ pushed_version: newVersion })
                    });

                    updateShareProgress(100, '🎉 增量推送完成！', '已成功升级云端版本至 v' + newVersion + ' (更新 ' + changedMovies.length + ' 部, 删除 ' + deletedMovieIds.length + ' 部)', '更新成功');

                    setTimeout(function() {
                        closeModal('shareProgressModal');
                        showToast('已成功推送增量更新至云端 (v' + newVersion + ')！');
                        loadLibraries();
                        if (state.currentLevel === 2) {
                            loadMovies();
                        }
                    }, 500);
                }

            } catch (err) {
                closeModal('shareProgressModal');
                showToast('发布失败: ' + (err.message || err));
            }
        }

        function submitUnpublishShare() {
            if (!authState.token) {
                showToast('取消分享需先登录账号');
                openAuthModal();
                return;
            }

            var libId = state.activeEditingLibId;
            var lib = null;
            for (var i = 0; i < state.libraries.length; i++) {
                if (state.libraries[i].id === libId) { lib = state.libraries[i]; break; }
            }
            if (!lib || !lib.share_code) return;
            if (lib.share_type === 2) {
                showToast('🔒 持续更新型订阅媒体库无权下架云端原作者分享');
                return;
            }

            if (!confirm('确定要取消分享并下架此媒体库吗？\n\n下架后该 6 位分享码 (' + lib.share_code + ') 将立即失效，且会从公共广场移除。')) {
                return;
            }

            var unpubBtn = document.getElementById('btnUnpublishShare');
            var origText = unpubBtn ? unpubBtn.innerText : '🚫 取消分享 (下架)';
            if (unpubBtn) {
                unpubBtn.disabled = true;
                unpubBtn.innerText = '⏳ 正在下架中...';
            }

            authFetch('/api/private/libraries/' + libId + '/unpublish', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (unpubBtn) {
                    unpubBtn.disabled = false;
                    unpubBtn.innerText = origText;
                }
                if (data.success) {
                    lib.share_code = '';
                    closeModal('shareModal');
                    showToast('已成功取消分享并下架！');
                    renderLibraries();
                    loadLibraries();
                } else {
                    showToast('下架失败: ' + (data.message || '未知错误'));
                }
            })
            .catch(function(err) {
                if (unpubBtn) {
                    unpubBtn.disabled = false;
                    unpubBtn.innerText = origText;
                }
                showToast('下架请求异常: ' + err.message);
            });
        }

        function copyShareCode() {
            var el = document.getElementById('shareCodeDisplay');
            var code = el ? (el.innerText || el.textContent || '').trim() : '';
            if (!code || code === '------') {
                showToast('暂无有效分享码可复制');
                return;
            }
            copyToClipboard(code, '分享码已复制到剪贴板！');
        }

        function openImportShareModal() {
            var input = document.getElementById('importCodeInput');
            if (input) input.value = '';
            var previewBox = document.getElementById('importPreviewBox');
            if (previewBox) {
                previewBox.style.display = 'none';
                previewBox.innerHTML = '';
            }
            var btnConfirm = document.getElementById('btnConfirmImport');
            if (btnConfirm) btnConfirm.style.display = 'none';
            state.previewImportData = null;
            state.previewShareCode = '';
            var sInput = document.getElementById('publicLibSearchInput');
            if (sInput) sInput.value = '';
            state.publicLibsQuery = '';
            openModal('importShareModal');
            loadPublicLibraries(1);
        }

        function previewShareCode() {
            var input = document.getElementById('importCodeInput');
            var code = input ? input.value.trim().toUpperCase() : '';
            if (!code) {
                showToast('请输入 6 位媒体库分享码');
                if (input) input.focus();
                return;
            }

            var btn = document.getElementById('btnPreviewShareCode');
            var origText = btn ? btn.innerHTML : '🔍 查询预览';
            if (btn) {
                btn.disabled = true;
                btn.innerHTML = '<span class="loading-spinner"></span> 查询中...';
            }

            var previewBox = document.getElementById('importPreviewBox');
            var btnConfirm = document.getElementById('btnConfirmImport');
            if (previewBox) previewBox.style.display = 'none';
            if (btnConfirm) btnConfirm.style.display = 'none';

            // 优先调用极速预览接口 (<15ms 极速响应)
            fetch('/api/mv/shared-libraries/preview/' + code)
                .then(function(res) { return res.json(); })
                .then(function(data) {
                    if (btn) {
                        btn.disabled = false;
                        btn.innerHTML = origText;
                    }
                    if (data.success && data.data) {
                        var lib = data.data;
                        state.previewShareCode = code;
                        state.previewImportData = null; // 延迟到点击确认导入时按需拉取全量

                        var firstMovieCover = (lib.previewMovies && lib.previewMovies.length > 0 && lib.previewMovies[0].coverUrl) || (lib.previewCovers && lib.previewCovers.length > 0 && lib.previewCovers[0]) || '';
                        if (!firstMovieCover && state.publicLibsList) {
                            for (var k = 0; k < state.publicLibsList.length; k++) {
                                var pubIt = state.publicLibsList[k];
                                if ((pubIt.shareCode || pubIt.share_code || '').toUpperCase() === code) {
                                    if (pubIt.previewCovers && pubIt.previewCovers.length > 0) {
                                        firstMovieCover = pubIt.previewCovers[0];
                                    } else if (pubIt.coverUrl && pubIt.coverUrl.indexOf('/posters/') !== 0) {
                                        firstMovieCover = pubIt.coverUrl;
                                    }
                                    break;
                                }
                            }
                        }
                        var fallbackCover = firstMovieCover || PRESET_COVERS[0];
                        var coverImg = lib.coverUrl;
                        if (!coverImg || (!lib.isOwner && coverImg.indexOf('/posters/') === 0)) {
                            coverImg = fallbackCover;
                        }
                        var shareTypeTag = lib.shareType === 2 ? '持续更新订阅' : '一次性快照';
                        var badgeColor = lib.shareType === 2 ? '#3b82f6' : '#10b981';

                        var previewHtml = '<div style="display: flex; gap: 12px; align-items: flex-start; justify-content: space-between;">';
                        previewHtml += '<div style="display: flex; gap: 12px; align-items: flex-start; flex: 1; min-width: 0;">';
                        previewHtml += '<img referrerpolicy="no-referrer" src="' + coverImg + '" onerror="this.onerror=function(){this.src=\'' + PRESET_COVERS[0] + '\';};this.src=\'' + fallbackCover + '\';" style="width: 52px; height: 72px; object-fit: cover; border-radius: 8px; flex-shrink: 0; background: #1e293b; border: 1px solid rgba(255,255,255,0.1);">';
                        previewHtml += '<div style="flex: 1; min-width: 0;">';
                        previewHtml += '<div style="font-weight: 700; font-size: 15px; color: #fff; line-height: 1.3;">' + lib.name + '</div>';
                        previewHtml += '<div style="display: flex; gap: 6px; flex-wrap: wrap; margin-top: 5px;">';
                        previewHtml += '<span style="background: rgba(99, 102, 241, 0.2); color: #a5b4fc; font-size: 11px; padding: 2px 8px; border-radius: 9999px; font-weight: 600;">🎬 ' + (lib.itemCount || 0) + ' 部影片</span>';
                        previewHtml += '<span style="background: rgba(56, 189, 248, 0.2); color: #38bdf8; font-size: 11px; padding: 2px 8px; border-radius: 9999px; font-weight: 600;">🔗 ' + (lib.linkCount || 0) + ' 条链接</span>';
                        if (lib.isOwner) {
                            previewHtml += '<span style="background: rgba(16, 185, 129, 0.2); color: #34d399; font-size: 11px; padding: 2px 8px; border-radius: 9999px; font-weight: 600;">👑 您的发布 (导入后开启作者维护模式)</span>';
                        } else {
                            previewHtml += '<span style="background: ' + badgeColor + '22; color: ' + badgeColor + '; font-size: 11px; padding: 2px 8px; border-radius: 9999px; font-weight: 600;">🏷️ ' + shareTypeTag + '</span>';
                        }
                        previewHtml += '</div>';
                        previewHtml += '<div style="font-size: 12px; color: var(--text-muted); margin-top: 5px;">分享作者: <span style="color: #e2e8f0; font-weight: 600;">' + (lib.creatorName || '匿名') + '</span> · 版本: v' + (lib.version || 1) + '</div>';
                        previewHtml += '</div></div>';
                        previewHtml += '<div style="flex-shrink: 0; margin-left: 8px;">';
                        previewHtml += '<button class="btn" id="btnConfirmImport" style="font-size: 12.5px; padding: 6px 14px; white-space: nowrap;" onclick="submitImportShare()">📥 确认导入</button>';
                        previewHtml += '</div>';
                        previewHtml += '</div>';

                        if (lib.previewMovies && lib.previewMovies.length > 0) {
                            previewHtml += '<div style="margin-top: 10px; border-top: 1px solid rgba(255,255,255,0.08); padding-top: 8px;">';
                            previewHtml += '<div style="font-size: 11.5px; color: var(--text-muted); margin-bottom: 6px;">部分影片预览:</div>';
                            previewHtml += '<div style="display: flex; gap: 8px; overflow-x: auto; padding-bottom: 4px;">';
                            for (var p = 0; p < lib.previewMovies.length; p++) {
                                var pm = lib.previewMovies[p];
                                var pmCover = pm.coverUrl || '';
                                previewHtml += '<div style="width: 46px; flex-shrink: 0; text-align: center;">';
                                if (pmCover) {
                                    previewHtml += '<img referrerpolicy="no-referrer" src="' + pmCover + '" onerror="this.onerror=null;this.src=\'' + PRESET_COVERS[0] + '\';" style="width: 46px; height: 64px; object-fit: cover; border-radius: 5px; background: #1e293b;">';
                                } else {
                                    previewHtml += '<div style="width: 46px; height: 64px; border-radius: 5px; background: #1e293b; display: flex; align-items: center; justify-content: center; font-size: 10px; color: var(--text-muted);">暂无图</div>';
                                }
                                previewHtml += '<div style="font-size: 10px; color: #cbd5e1; margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="' + pm.title + '">' + pm.title + '</div>';
                                previewHtml += '</div>';
                            }
                            previewHtml += '</div></div>';
                        }

                        if (previewBox) {
                            previewBox.innerHTML = previewHtml;
                            previewBox.style.display = 'block';
                        }
                    } else {
                        showToast(data.message || '未找到该分享码对应的媒体库');
                    }
                })
                .catch(function(err) {
                    if (btn) {
                        btn.disabled = false;
                        btn.innerHTML = origText;
                    }
                    showToast('查询失败: ' + err.message);
                });
        }

        async function submitImportShare() {
            var code = state.previewShareCode;
            if (!code) return;

            if (state.libraries) {
                var upperCode = code.toUpperCase();
                for (var i = 0; i < state.libraries.length; i++) {
                    if ((state.libraries[i].share_code || '').toUpperCase() === upperCode) {
                        showToast('⚠️ 您已导入过该媒体库【' + state.libraries[i].name + '】，无需重复导入');
                        locateLocalLibraryByShareCode(code);
                        return;
                    }
                }
            }

            var btn = document.getElementById('btnConfirmImport');
            var origText = btn ? btn.innerHTML : '确认导入到我的私有库';
            if (btn) {
                btn.disabled = true;
                btn.innerHTML = '<span class="loading-spinner"></span> 正在导入入库...';
            }

            try {
                // 1. 获取全量快照数据
                var detailRes = await fetch('/api/mv/shared-libraries/detail/' + code);
                var detailData = await detailRes.json();
                if (!detailData.success || !detailData.data) {
                    throw new Error(detailData.message || '拉取媒体库全量数据失败');
                }

                var isOwnerLib = Boolean(detailData.data.library && detailData.data.library.isOwner);

                // 若导入的共享媒体库没有封面图，自动生成 Canvas 渐变科技封面并转存为本地实体文件
                if (detailData.data.library && !detailData.data.library.coverUrl) {
                    var libName = detailData.data.library.name || '共享媒体库';
                    var autoCover = generateLibGradientCover(libName, (state.libraries ? state.libraries.length : 0) % LIB_COVER_THEMES.length);
                    if (autoCover) {
                        try {
                            var savedCover = await uploadBase64LibPoster(autoCover);
                            detailData.data.library.coverUrl = savedCover;
                        } catch (eCov) {
                            detailData.data.library.coverUrl = autoCover;
                        }
                    }
                }

                // 2. 提交至本地 SQLite 极速事务入库
                var importRes = await fetch('/api/private/import_snapshot', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(detailData.data)
                });
                var importData = await importRes.json();

                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = origText;
                }

                if (importData.success) {
                    if (isOwnerLib) {
                        showToast('🎉 检测到您是该分享的作者，已自动开启「作者编辑维护模式」，修改后可直接推送更新至该分享码！');
                    } else {
                        showToast('🎉 已成功导入到我的私有库！');
                    }
                    closeModal('importShareModal');
                    loadLibraries();
                } else {
                    showToast('导入失败: ' + (importData.message || '未知错误'));
                }
            } catch (err) {
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = origText;
                }
                showToast('导入异常: ' + (err.message || err));
            }
        }

        function searchPublicLibraries() {
            var input = document.getElementById('publicLibSearchInput');
            state.publicLibsQuery = input ? input.value.trim() : '';
            loadPublicLibraries(1);
        }

        function changePublicLibsPage(delta) {
            var target = state.publicLibsPage + delta;
            if (target >= 1 && target <= state.publicLibsTotalPages) {
                loadPublicLibraries(target);
            }
        }

        function previewPublicSharedLibrary(code) {
            var input = document.getElementById('importCodeInput');
            if (input) input.value = code;
            previewShareCode();
            var modalBody = document.querySelector('#importShareModal .modal-body');
            if (modalBody) {
                modalBody.scrollTo({ top: 0, behavior: 'smooth' });
            }
        }

        function onPublicLibCardClick(code, name, itemCount, event) {
            if (state.libraries) {
                var upperCode = code.toUpperCase();
                for (var i = 0; i < state.libraries.length; i++) {
                    if ((state.libraries[i].share_code || '').toUpperCase() === upperCode) {
                        showToast('⚠️ 您已导入过该媒体库【' + state.libraries[i].name + '】');
                        locateLocalLibraryByShareCode(code);
                        return;
                    }
                }
            }
            importPublicSharedLibrary(code, name, itemCount, event);
        }

        async function importPublicSharedLibrary(code, name, itemCount, event) {
            if (!code) return;

            // 0. 本地查重拦截
            if (state.libraries) {
                var upperCode = code.toUpperCase();
                for (var i = 0; i < state.libraries.length; i++) {
                    if ((state.libraries[i].share_code || '').toUpperCase() === upperCode) {
                        showToast('⚠️ 您已导入过该媒体库【' + state.libraries[i].name + '】，无需重复导入');
                        locateLocalLibraryByShareCode(code);
                        return;
                    }
                }
            }

            var countMsg = (itemCount !== undefined && itemCount !== null) ? ' (共 ' + itemCount + ' 部影片)' : '';
            if (!confirm('确定要将共享媒体库【' + name + '】' + countMsg + ' 导入到您的本地私有库吗？')) {
                return;
            }

            var targetBtn = event && event.target ? event.target.closest('button') : null;
            var origBtnHtml = targetBtn ? targetBtn.innerHTML : '';
            if (targetBtn) {
                targetBtn.disabled = true;
                targetBtn.innerHTML = '<span class="loading-spinner"></span> 导入中...';
            }

            showToast('正在从云端拉取媒体库【' + name + '】快照数据...');

            try {
                // 1. 获取全量快照数据
                var detailRes = await fetch('/api/mv/shared-libraries/detail/' + code);
                var detailData = await detailRes.json();
                if (!detailData.success || !detailData.data) {
                    throw new Error(detailData.message || '拉取媒体库全量数据失败');
                }

                var isOwnerLib = Boolean(detailData.data.library && detailData.data.library.isOwner);

                // 2. 封面兜底
                if (detailData.data.library && !detailData.data.library.coverUrl) {
                    var libName = detailData.data.library.name || name || '共享媒体库';
                    var autoCover = generateLibGradientCover(libName, (state.libraries ? state.libraries.length : 0) % LIB_COVER_THEMES.length);
                    if (autoCover) {
                        try {
                            var savedCover = await uploadBase64LibPoster(autoCover);
                            detailData.data.library.coverUrl = savedCover;
                        } catch (eCov) {
                            detailData.data.library.coverUrl = autoCover;
                        }
                    }
                }

                // 3. 提交至本地 SQLite 极速事务入库
                var importRes = await fetch('/api/private/import_snapshot', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(detailData.data)
                });
                var importData = await importRes.json();

                if (targetBtn) {
                    targetBtn.disabled = false;
                    targetBtn.innerHTML = origBtnHtml;
                }

                if (importData.success) {
                    if (isOwnerLib) {
                        showToast('🎉 检测到您是该分享的作者，已自动开启「作者编辑维护模式」，修改后可直接推送更新至该分享码！');
                    } else {
                        showToast('🎉 已成功将【' + name + '】导入到我的私有库！');
                    }
                    closeModal('importShareModal');
                    loadLibraries();
                } else {
                    showToast('导入失败: ' + (importData.message || '未知错误'));
                }
            } catch (err) {
                if (targetBtn) {
                    targetBtn.disabled = false;
                    targetBtn.innerHTML = origBtnHtml;
                }
                showToast('导入异常: ' + (err.message || err));
            }
        }

        async function loadPublicLibraries(page) {
            state.publicLibsPage = page || 1;
            var container = document.getElementById('publicLibsContainer');
            var paginationEl = document.getElementById('publicLibsPagination');
            var summaryEl = document.getElementById('publicLibsSummary');
            if (!container) return;

            container.innerHTML = '<div style="text-align: center; color: var(--text-muted); padding: 32px;"><span class="loading-spinner"></span> 正在加载共享媒体库列表...</div>';
            if (paginationEl) paginationEl.style.display = 'none';

            try {
                var url = '/api/mv/shared-libraries/public?page=' + state.publicLibsPage + '&pageSize=' + state.publicLibsPageSize;
                if (state.publicLibsQuery) {
                    url += '&q=' + encodeURIComponent(state.publicLibsQuery);
                }
                var res = await fetch(url);
                var data = await res.json();

                if (!data.success || !data.data) {
                    container.innerHTML = '<div style="text-align: center; color: var(--text-muted); padding: 30px;">' + (data.message || '加载共享媒体库失败') + '</div>';
                    return;
                }

                var items = data.data.items || [];
                var pag = data.data.pagination || {};
                state.publicLibsList = items;
                state.publicLibsTotal = pag.total !== undefined ? pag.total : (data.data.total || items.length);
                state.publicLibsTotalPages = pag.totalPages || Math.ceil(state.publicLibsTotal / state.publicLibsPageSize) || 1;

                if (summaryEl) {
                    summaryEl.innerText = '(共 ' + state.publicLibsTotal + ' 个共享库)';
                }

                if (items.length === 0) {
                    container.innerHTML = '<div style="text-align: center; color: var(--text-muted); padding: 32px;">暂无' + (state.publicLibsQuery ? '符合条件的' : '公开的') + '共享媒体库</div>';
                    if (paginationEl) paginationEl.style.display = 'none';
                    return;
                }

                var localCodeMap = {};
                if (state.libraries) {
                    for (var k = 0; k < state.libraries.length; k++) {
                        var sc = (state.libraries[k].share_code || '').trim().toUpperCase();
                        if (sc) {
                            localCodeMap[sc] = state.libraries[k];
                        }
                    }
                }

                var html = '';
                for (var i = 0; i < items.length; i++) {
                    var it = items[i];
                    var sCode = (it.shareCode || it.share_code || '').trim().toUpperCase();
                    var itName = it.name || '共享媒体库';
                    var itCreator = it.creatorName || it.creator_name || '匿名';
                    var mCount = it.itemCount !== undefined ? it.itemCount : (it.item_count !== undefined ? it.item_count : (it.movieCount || 0));
                    var lCount = it.linkCount !== undefined ? it.linkCount : (it.link_count || 0);
                    var sType = it.shareType || it.share_type || 1;
                    var isImported = Boolean(localCodeMap[sCode]);
                    var fallbackCover = (it.previewCovers && it.previewCovers[0]) || PRESET_COVERS[0];
                    var coverImg = it.coverUrl;
                    if (!coverImg || (!isImported && coverImg.indexOf('/posters/') === 0)) {
                        coverImg = fallbackCover;
                    }

                    var sTypeLabel = (sType === 2) ? '持续更新' : '快照';
                    var sTypeBadge = (sType === 2) 
                        ? '<span style="background: rgba(59, 130, 246, 0.18); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.35); font-size: 11px; padding: 1px 7px; border-radius: 9999px; font-weight: 600;">🔄 ' + sTypeLabel + '</span>'
                        : '<span style="background: rgba(16, 185, 129, 0.18); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.35); font-size: 11px; padding: 1px 7px; border-radius: 9999px; font-weight: 600;">📦 ' + sTypeLabel + '</span>';

                    var escapedCode = escapeHtml(sCode);
                    var escapedName = escapeHtml(itName);
                    var escapedCreator = escapeHtml(itCreator);
                    var safeJsName = escapedName.replace(/'/g, "\\'");
                    var safeJsCode = escapedCode.replace(/'/g, "\\'");

                    html += '<div class="public-lib-card" onclick="onPublicLibCardClick(\'' + safeJsCode + '\', \'' + safeJsName + '\', ' + mCount + ', event)" style="background: rgba(15, 23, 42, 0.6); border: 1px solid ' + (isImported ? 'rgba(99, 102, 241, 0.35)' : 'var(--card-border)') + '; border-radius: 8px; padding: 7px 12px; display: flex; gap: 10px; align-items: center; justify-content: space-between; transition: all 0.2s ease; cursor: pointer;">';
                    html += '<div style="display: flex; gap: 10px; align-items: center; min-width: 0; flex: 1;">';
                    html += '<img referrerpolicy="no-referrer" src="' + coverImg + '" onerror="this.onerror=function(){this.src=\'' + PRESET_COVERS[0] + '\';};this.src=\'' + fallbackCover + '\';" style="width: 36px; height: 50px; object-fit: cover; border-radius: 5px; background: #1e293b; border: 1px solid rgba(255,255,255,0.08); flex-shrink: 0;">';
                    html += '<div style="min-width: 0; flex: 1;">';
                    html += '<div style="display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">';
                    html += '<span style="font-weight: 700; font-size: 13.5px; color: #fff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 340px;" title="' + escapedName + '">' + escapedName + '</span>';
                    html += '<span style="font-size: 11px; color: #a5b4fc; font-weight: 700; background: rgba(99, 102, 241, 0.15); padding: 1px 5px; border-radius: 4px; font-family: monospace;">' + escapedCode + '</span>';
                    html += sTypeBadge;
                    html += '</div>';
                    html += '<div style="display: flex; gap: 8px; align-items: center; margin-top: 3px; font-size: 11.5px; color: var(--text-muted); flex-wrap: wrap;">';
                    html += '<span>🎬 <strong style="color: #cbd5e1;">' + mCount + '</strong> 部影片</span>';
                    html += '<span>🔗 <strong style="color: #cbd5e1;">' + lCount + '</strong> 链接</span>';
                    html += '<span>👤 ' + escapedCreator + '</span>';
                    html += '</div>';
                    html += '</div>';
                    html += '</div>';

                    // 右侧操作按钮组
                    html += '<div style="display: flex; gap: 6px; align-items: center; flex-shrink: 0;">';
                    html += '<button class="btn btn-secondary" style="font-size: 11.5px; padding: 4px 9px;" title="在上方预览详细影片与信息" onclick="event.stopPropagation(); previewPublicSharedLibrary(\'' + safeJsCode + '\')">🔍 预览</button>';
                    if (isImported) {
                        html += '<button class="btn btn-secondary" style="font-size: 11.5px; padding: 4px 10px; color: #a5b4fc; border-color: rgba(99,102,241,0.4);" onclick="event.stopPropagation(); locateLocalLibraryByShareCode(\'' + safeJsCode + '\')">📍 本地已存在</button>';
                    } else {
                        html += '<button class="btn" style="font-size: 11.5px; padding: 4px 11px;" onclick="event.stopPropagation(); importPublicSharedLibrary(\'' + safeJsCode + '\', \'' + safeJsName + '\', ' + mCount + ', event)">📥 导入</button>';
                    }
                    html += '</div>';

                    html += '</div>';
                }

                container.innerHTML = html;
                container.scrollTop = 0;

                // 渲染分页控件
                if (paginationEl) {
                    paginationEl.style.display = 'flex';
                    var pageSummaryEl = document.getElementById('publicLibsPageSummary');
                    var pageInfoEl = document.getElementById('publicLibsPageInfo');
                    var prevBtn = document.getElementById('publicLibsPrevBtn');
                    var nextBtn = document.getElementById('publicLibsNextBtn');
                    if (pageSummaryEl) pageSummaryEl.innerText = '共 ' + state.publicLibsTotal + ' 个共享媒体库';
                    if (pageInfoEl) pageInfoEl.innerText = '第 ' + state.publicLibsPage + ' / ' + state.publicLibsTotalPages + ' 页';
                    if (prevBtn) prevBtn.disabled = (state.publicLibsPage <= 1);
                    if (nextBtn) nextBtn.disabled = (state.publicLibsPage >= state.publicLibsTotalPages);
                }
            } catch (err) {
                container.innerHTML = '<div style="text-align: center; color: var(--text-muted); padding: 30px;">加载共享媒体库列表异常: ' + (err.message || err) + '</div>';
                if (paginationEl) paginationEl.style.display = 'none';
            }
        }

        function syncLibrary(libId) {
            showToast('正在检查更新...');
            fetch('/api/private/libraries/' + libId + '/sync', { method: 'POST' })
                .then(function(res) { return res.json(); })
                .then(function(data) {
                    if (data.data && data.data.hasUpdates) {
                        showToast('同步成功，已更新至最新版本！');
                        loadLibraries();
                        if (state.currentLevel === 2) loadMovies();
                    } else {
                        showToast('当前已是最新版本');
                    }
                })
                .catch(function(err) {
                    showToast('同步失败: ' + err.message);
                });
        }

        function exportCurrentLibToStrm() {
            var libId = state.currentLib ? state.currentLib.id : null;
            if (!libId) {
                showToast('请先选择一个媒体库');
                return;
            }
            showToast('正在导出 STRM 与 NFO 元数据...');
            fetch('/api/private/libraries/' + libId + '/export_strm', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({})
            })
            .then(function(res) { return res.json(); })
            .then(function(res) {
                if (res.success) {
                    var msg = '🎬 成功导出 ' + res.exported_movies + ' 部影片 (' + res.exported_strms + ' 个版本)！\n\n📁 目标路径: ' + res.target_dir;
                    if (res.is_coreelec) {
                        msg += '\n\n(已自动适配 CoreELEC 系统路径 /storage/videos/juku-strm/movies，在 Kodi 媒体库中添加该视频源并选择「巨库」刮削器即可！)';
                    }
                    alert(msg);
                } else {
                    alert('导出失败: ' + (res.message || res.error || '未知错误'));
                }
            })
            .catch(function(err) {
                alert('请求异常: ' + err.message);
            });
        }

        // ------------------ 网盘监控与自动同步目录管理 ------------------

        function openPanSyncDirsModal(libId) {
            var targetLibId = libId || (state.currentLib ? state.currentLib.id : '');
            var container = document.getElementById('panSyncDirsContainer');
            if (container) {
                container.innerHTML = '<div style="text-align: center; padding: 30px; color: var(--text-muted); font-size: 13px;"><div class="loading-spinner" style="width: 24px; height: 24px; margin: 0 auto 10px auto;"></div>正在读取监控目录列表...</div>';
            }
            openModal('panSyncDirsModal');

            var url = '/api/private/pan/sync_dirs';
            if (targetLibId) {
                url += '?library_id=' + encodeURIComponent(targetLibId);
            }

            fetch(url)
                .then(function(res) { return res.json(); })
                .then(function(res) {
                    if (!res.success) {
                        throw new Error(res.error || res.message || '获取监控目录失败');
                    }
                    var schedulerStatusEl = document.getElementById('panSyncSchedulerStatus');
                    if (schedulerStatusEl) {
                        if (res.is_running) {
                            schedulerStatusEl.innerHTML = '● 115生活事件轮询器: 运行中 (每10秒)';
                            schedulerStatusEl.style.background = 'rgba(16,185,129,0.15)';
                            schedulerStatusEl.style.color = '#34d399';
                            schedulerStatusEl.style.borderColor = 'rgba(16,185,129,0.3)';
                        } else {
                            schedulerStatusEl.innerHTML = '○ 115生活事件轮询器: 未启动或空转';
                            schedulerStatusEl.style.background = 'rgba(148,163,184,0.15)';
                            schedulerStatusEl.style.color = '#94a3b8';
                            schedulerStatusEl.style.borderColor = 'rgba(148,163,184,0.3)';
                        }
                    }
                    renderPanSyncDirsList(res.items || [], targetLibId);
                })
                .catch(function(err) {
                    if (container) {
                        container.innerHTML = '<div style="text-align: center; padding: 30px; color: #f87171; font-size: 13px;">加载失败: ' + escapeHtml(err.message) + '</div>';
                    }
                });
        }

        function renderPanSyncDirsList(items, currentLibId) {
            var container = document.getElementById('panSyncDirsContainer');
            if (!container) return;

            if (!items || items.length === 0) {
                container.innerHTML = '<div style="text-align: center; padding: 40px 20px; color: var(--text-muted);">' +
                    '<div style="font-size: 32px; margin-bottom: 12px;">📂</div>' +
                    '<div style="font-size: 14px; font-weight: 600; color: #cbd5e1; margin-bottom: 6px;">当前媒体库暂无绑定的网盘监控目录</div>' +
                    '<div style="font-size: 12px; max-width: 420px; margin: 0 auto; line-height: 1.6;">点击媒体库顶部的【从个人盘导入】，选择您的 115 网盘目录并保持勾选【同步更新】，系统将自动在此创建监控任务并实时追踪更新。</div>' +
                    '</div>';
                return;
            }

            var html = '<div style="display: flex; flex-direction: column; gap: 12px;">';
            for (var i = 0; i < items.length; i++) {
                var it = items[i];
                var isEnabled = (it.sync_enabled === 1);
                var lastSyncStr = '从未同步';
                if (it.last_sync_at > 0) {
                    var d = new Date(it.last_sync_at * 1000);
                    lastSyncStr = d.getFullYear() + '-' +
                        String(d.getMonth() + 1).padStart(2, '0') + '-' +
                        String(d.getDate()).padStart(2, '0') + ' ' +
                        String(d.getHours()).padStart(2, '0') + ':' +
                        String(d.getMinutes()).padStart(2, '0') + ':' +
                        String(d.getSeconds()).padStart(2, '0');
                }

                html += '<div style="background: rgba(15,23,42,0.6); border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; padding: 14px 18px; display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap;">';
                
                // 左侧信息区
                html += '<div style="flex: 1; min-width: 240px;">';
                html += '<div style="display: flex; align-items: center; gap: 8px; margin-bottom: 6px;">';
                html += '<span style="font-size: 12px; font-weight: 700; padding: 2px 7px; border-radius: 4px; background: rgba(99,102,241,0.2); color: #a5b4fc; border: 1px solid rgba(99,102,241,0.3);">' + escapeHtml(it.provider || 'CLOUD115') + '</span>';
                html += '<span style="font-size: 15px; font-weight: 700; color: #f1f5f9;">' + escapeHtml(it.dir_name || '个人网盘目录') + '</span>';
                if (isEnabled) {
                    html += '<span style="font-size: 11px; padding: 1px 6px; border-radius: 4px; background: rgba(16,185,129,0.15); color: #34d399;">监控中</span>';
                } else {
                    html += '<span style="font-size: 11px; padding: 1px 6px; border-radius: 4px; background: rgba(239,68,68,0.15); color: #f87171;">已暂停</span>';
                }
                html += '</div>';

                html += '<div style="font-size: 12px; color: var(--text-muted); display: flex; flex-direction: column; gap: 4px;">';
                html += '<div>目录 ID: <code style="background: rgba(0,0,0,0.3); padding: 1px 5px; border-radius: 4px; font-size: 11px; color: #cbd5e1;">' + escapeHtml(it.dir_file_id || '-') + '</code>' + (it.dir_path ? (' | 路径: ' + escapeHtml(it.dir_path)) : '') + '</div>';
                html += '<div>上次同步: <span style="color: #94a3b8;">' + lastSyncStr + '</span></div>';
                html += '</div>';
                html += '</div>';

                // 右侧操作按钮区
                html += '<div style="display: flex; align-items: center; gap: 8px; flex-shrink: 0;">';
                
                // 立即全量同步按钮
                html += '<button class="btn btn-secondary" style="padding: 6px 12px; font-size: 12px; display: inline-flex; align-items: center; gap: 4px;" id="btnFullSync_' + it.id + '" onclick="triggerPanSyncDirFullSync(\'' + it.id + '\', \'' + (currentLibId || '') + '\')" title="全量扫描目录并补全遗漏影视">' +
                    '🔄 立即全量同步' +
                    '</button>';

                // 启停切换按钮
                if (isEnabled) {
                    html += '<button class="btn btn-secondary" style="padding: 6px 12px; font-size: 12px; color: #f59e0b; border-color: rgba(245,158,11,0.3);" onclick="togglePanSyncDirStatus(\'' + it.id + '\', 0, \'' + (currentLibId || '') + '\')">⏸️ 暂停</button>';
                } else {
                    html += '<button class="btn btn-secondary" style="padding: 6px 12px; font-size: 12px; color: #34d399; border-color: rgba(16,185,129,0.3);" onclick="togglePanSyncDirStatus(\'' + it.id + '\', 1, \'' + (currentLibId || '') + '\')">▶️ 启用</button>';
                }

                // 删除解绑按钮
                html += '<button class="btn btn-secondary" style="padding: 6px 10px; font-size: 12px; color: #f87171; border-color: rgba(239,68,68,0.3);" onclick="deletePanSyncDir(\'' + it.id + '\', \'' + escapeHtml(it.dir_name || '') + '\', \'' + (currentLibId || '') + '\')" title="解除监控并删除绑定记录">🗑️ 解绑</button>';

                html += '</div>';

                html += '</div>';
            }
            html += '</div>';
            container.innerHTML = html;
        }

        function togglePanSyncDirStatus(id, newStatus, currentLibId) {
            fetch('/api/private/pan/sync_dir/toggle', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id: id, status: newStatus })
            })
            .then(function(res) { return res.json(); })
            .then(function(res) {
                if (res.success) {
                    showToast(newStatus === 1 ? '✅ 已恢复该目录的生活事件同步监控' : '⏸️ 已暂停该目录的生活事件同步监控');
                    openPanSyncDirsModal(currentLibId);
                } else {
                    throw new Error(res.error || res.message || '更新状态失败');
                }
            })
            .catch(function(err) {
                showToast('操作失败: ' + err.message);
            });
        }

        function deletePanSyncDir(id, dirName, currentLibId) {
            if (!confirm('确定要解除对目录【' + (dirName || '所选目录') + '】的同步监控吗？\n\n解除后，网盘目录变动将不再自动同步至此媒体库（库内已导入的影片仍会保留）。')) {
                return;
            }
            fetch('/api/private/pan/sync_dir/delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id: id })
            })
            .then(function(res) { return res.json(); })
            .then(function(res) {
                if (res.success) {
                    showToast('🗑️ 已成功解除监控目录绑定');
                    openPanSyncDirsModal(currentLibId);
                } else {
                    throw new Error(res.error || res.message || '解除绑定失败');
                }
            })
            .catch(function(err) {
                showToast('解除绑定失败: ' + err.message);
            });
        }

        function triggerPanSyncDirFullSync(id, currentLibId) {
            var btn = document.getElementById('btnFullSync_' + id);
            if (btn) {
                btn.disabled = true;
                btn.innerHTML = '⏳ 正在全量扫描比对...';
            }
            fetch('/api/private/pan/sync_dir/full_sync', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id: id })
            })
            .then(function(res) { return res.json(); })
            .then(function(res) {
                if (res.success) {
                    showToast('🚀 已触发全量扫描同步！后台正在递归检查并补全可能遗漏的影视资源...');
                    setTimeout(function() {
                        if (btn) {
                            btn.disabled = false;
                            btn.innerHTML = '🔄 立即全量同步';
                        }
                        openPanSyncDirsModal(currentLibId);
                    }, 2500);
                } else {
                    throw new Error(res.error || res.message || '触发全量同步失败');
                }
            })
            .catch(function(err) {
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = '🔄 立即全量同步';
                }
                showToast('全量同步请求失败: ' + err.message);
            });
        }

        // ------------------ 待确认暂存箱 (全局 / 单库双模) ------------------

        function refreshUnmatchedCounts(activeLibId) {
            fetch('/api/private/unmatched')
                .then(function(res) { return res.json(); })
                .then(function(data) {
                    if (!data || !data.data) return;
                    var counts = data.data.counts || {};
                    var globalTotal = data.data.global_total || 0;
                    state.unmatchedCounts = counts;
                    state.unmatchedGlobalTotal = globalTotal;

                    // 1. 私有库列表页全局徽章
                    var badgeAll = document.getElementById('badgeAllUnmatched');
                    if (badgeAll) {
                        if (globalTotal > 0) {
                            badgeAll.innerText = globalTotal;
                            badgeAll.style.display = 'inline-block';
                        } else {
                            badgeAll.style.display = 'none';
                        }
                    }
                    var badgeAllCombined = document.getElementById('badgeAllToolsCombined');
                    if (badgeAllCombined) {
                        if (globalTotal > 0) {
                            badgeAllCombined.innerText = globalTotal > 99 ? '99+' : globalTotal;
                            badgeAllCombined.style.display = 'inline-flex';
                        } else {
                            badgeAllCombined.style.display = 'none';
                        }
                    }

                    // 2. 媒体库内页单库徽章
                    var targetLibId = activeLibId || (state.currentLib ? state.currentLib.id : '');
                    var badgeL2 = document.getElementById('badgeL2Unmatched');
                    if (badgeL2) {
                        var libCount = (targetLibId && counts[targetLibId]) ? counts[targetLibId] : 0;
                        if (libCount > 0) {
                            badgeL2.innerText = libCount;
                            badgeL2.style.display = 'inline-block';
                        } else {
                            badgeL2.style.display = 'none';
                        }
                    }
                    if (typeof updateCombinedToolsBadge === 'function') {
                        updateCombinedToolsBadge();
                    }
                })
                .catch(function(e) {
                    console.error('[refreshUnmatchedCounts] error:', e);
                });
        }



        function openUnmatchedModal(scope) {
            var targetScope = scope || 'all';
            if (targetScope !== 'all') {
                var lib = (state.libraries || []).find(function(l) { return l.id === targetScope; });
                if (lib && lib.share_type === 2) {
                    showToast('🔒 持续更新型订阅媒体库为只读模式，无待确认暂存箱');
                    return;
                }
            }
            state.unmatchedCurrentScope = targetScope;
            state.unmatchedQueueSelectedIds = [];
            var chkAll = document.getElementById('unmatchedSelectAll');
            if (chkAll) chkAll.checked = false;
            updateUnmatchedBatchDelBtn();

            var titleEl = document.getElementById('unmatchedModalTitle');
            var selectEl = document.getElementById('unmatchedLibSelect');
            var libTh = document.getElementById('thUnmatchedLibCol');

            if (targetScope === 'all') {
                if (titleEl) titleEl.innerText = '📥 待确认暂存箱 (全部媒体库)';
                if (selectEl) {
                    selectEl.style.display = 'inline-block';
                    var optHtml = '<option value="all">全部媒体库</option>';
                    var writableLibs = getWritableLibraries();
                    for (var i = 0; i < writableLibs.length; i++) {
                        var l = writableLibs[i];
                        optHtml += '<option value="' + l.id + '">' + l.name.replace(/"/g, '&quot;') + '</option>';
                    }
                    selectEl.innerHTML = optHtml;
                    selectEl.value = 'all';
                }
                if (libTh) libTh.style.display = '';
            } else {
                var libName = (state.currentLib && state.currentLib.name) ? state.currentLib.name : '当前媒体库';
                if (titleEl) titleEl.innerText = '📥 待确认暂存箱 - ' + libName;
                if (selectEl) selectEl.style.display = 'none';
                if (libTh) libTh.style.display = 'none';
            }

            updateApiCheatSheetContent(scope);
            loadUnmatchedQueueItems(scope);
            openModal('unmatchedModal');
        }

        function handleUnmatchedLibChange(val) {
            state.unmatchedCurrentScope = val;
            state.unmatchedQueueSelectedIds = [];
            var chkAll = document.getElementById('unmatchedSelectAll');
            if (chkAll) chkAll.checked = false;
            updateUnmatchedBatchDelBtn();
            updateApiCheatSheetContent(val);
            loadUnmatchedQueueItems(val);
        }

        function loadUnmatchedQueueItems(scope) {
            var url = '/api/private/unmatched';
            if (scope && scope !== 'all') {
                url += '?library_id=' + encodeURIComponent(scope);
            }
            var tbody = document.getElementById('unmatchedQueueTbody');
            var emptyNotice = document.getElementById('unmatchedEmptyNotice');
            var badgeEl = document.getElementById('unmatchedModalCountBadge');

            if (tbody) tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:24px;color:#a5b4fc;">正在加载待确认记录...</td></tr>';

            fetch(url)
                .then(function(res) { return res.json(); })
                .then(function(data) {
                    var items = (data && data.data && data.data.items) || [];
                    state.unmatchedQueueList = items;
                    if (badgeEl) badgeEl.innerText = '共 ' + items.length + ' 条待处理';
                    renderUnmatchedQueueTable();
                    refreshUnmatchedCounts(state.currentLib ? state.currentLib.id : '');
                })
                .catch(function(err) {
                    if (tbody) tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:24px;color:#f87171;">加载失败: ' + err.message + '</td></tr>';
                });
        }

        function switchUnmatchedView(mode) {
            state.unmatchedViewMode = mode;
            var btnSeries = document.getElementById('btnUnmViewSeries');
            var btnFlat = document.getElementById('btnUnmViewFlat');
            if (mode === 'series') {
                if (btnSeries) { btnSeries.style.background = '#6366f1'; btnSeries.style.color = '#fff'; }
                if (btnFlat) { btnFlat.style.background = 'transparent'; btnFlat.style.color = '#94a3b8'; }
            } else {
                if (btnSeries) { btnSeries.style.background = 'transparent'; btnSeries.style.color = '#94a3b8'; }
                if (btnFlat) { btnFlat.style.background = '#6366f1'; btnFlat.style.color = '#fff'; }
            }
            renderUnmatchedQueueTable();
        }

        function renderUnmatchedQueueTable() {
            var tableEl = document.getElementById('unmatchedQueueTable');
            var seriesView = document.getElementById('unmatchedSeriesView');
            var emptyNotice = document.getElementById('unmatchedEmptyNotice');
            var items = state.unmatchedQueueList || [];

            if (items.length === 0) {
                if (tableEl) tableEl.style.display = 'none';
                if (seriesView) { seriesView.style.display = 'none'; seriesView.innerHTML = ''; }
                if (emptyNotice) emptyNotice.style.display = 'block';
                return;
            }
            if (emptyNotice) emptyNotice.style.display = 'none';

            if (state.unmatchedViewMode === 'series') {
                if (tableEl) tableEl.style.display = 'none';
                if (seriesView) {
                    seriesView.style.display = 'flex';
                    renderUnmatchedSeriesCards();
                }
            } else {
                if (seriesView) seriesView.style.display = 'none';
                if (tableEl) {
                    tableEl.style.display = 'table';
                    renderUnmatchedFlatTable();
                }
            }
        }

        function renderUnmatchedSeriesCards() {
            var container = document.getElementById('unmatchedSeriesView');
            if (!container) return;
            var items = state.unmatchedQueueList || [];
            if (items.length === 0) {
                container.innerHTML = '';
                return;
            }

            var isAllScope = (state.unmatchedCurrentScope === 'all');

            // 1. 聚类分组 (优先同剧名，其次有意义剧名目录，再次单文件)
            var groups = {};
            var groupOrder = [];
            for (var i = 0; i < items.length; i++) {
                var it = items[i];
                var pFolder = it.parent_folder_name || '';
                var rawT = (it.raw_title || '').trim();
                var rawY = (it.raw_year || '').trim();
                var meaningfulFolder = resolveMeaningfulSeriesFolder(pFolder);
                var effectiveTitle = !isWeakSeriesTitle(rawT) ? rawT : (meaningfulFolder || '');

                var key = '';
                if (!isWeakSeriesTitle(effectiveTitle)) {
                    key = 'title:' + effectiveTitle.toLowerCase() + (rawY ? ('_' + rawY) : '');
                } else {
                    key = 'single:' + it.id;
                }

                if (!groups[key]) {
                    groups[key] = {
                        key: key,
                        dir: pFolder,
                        title: effectiveTitle,
                        year: rawY,
                        libraryName: it.library_name || '',
                        libraryId: it.library_id || '',
                        provider: it.provider || '',
                        items: []
                    };
                    groupOrder.push(key);
                }
                groups[key].items.push(it);
                if (!groups[key].title && effectiveTitle) groups[key].title = effectiveTitle;
                if (!groups[key].year && rawY) groups[key].year = rawY;
                if (!groups[key].provider && it.provider) groups[key].provider = it.provider;
            }
            for (var k in groups) {
                groups[k].items.sort(function(a, b) {
                    var sa = a.season_number || 1;
                    var sb = b.season_number || 1;
                    if (sa !== sb) return sa - sb;
                    return (a.episode_number || 1) - (b.episode_number || 1);
                });
            }
            state.unmatchedSeriesGroups = groups;

            var html = '';
            for (var g = 0; g < groupOrder.length; g++) {
                var grpKey = groupOrder[g];
                var grp = groups[grpKey];
                var totalEpisodes = grp.items.length;
                var displayTitle = grp.title || resolveMeaningfulSeriesFolder(grp.dir) || '未命名影视';
                var displayYear = grp.year ? (' (' + grp.year + ')') : '';
                var provBadge = grp.provider ? ('<span class="badge" style="background:rgba(99,102,241,0.2);color:#a5b4fc;border:1px solid rgba(99,102,241,0.35);font-size:11px;padding:2px 6px;border-radius:4px;margin-right:6px;">' + grp.provider + '</span>') : '';
                var libBadge = isAllScope ? ('<span class="badge" style="background:rgba(148,163,184,0.15);color:#cbd5e1;font-size:11px;padding:2px 6px;border-radius:4px;margin-right:6px;">' + (grp.libraryName || grp.libraryId) + '</span>') : '';

                html += '<div class="unm-series-card" id="unm_grp_card_' + g + '" style="background:rgba(15,23,42,0.65);border:1px solid rgba(255,255,255,0.08);border-radius:8px;padding:12px 16px;display:flex;flex-direction:column;gap:8px;transition:all 0.2s ease;">';
                html += '  <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;">';
                html += '    <div style="display:flex;align-items:center;gap:8px;flex:1;min-width:240px;flex-wrap:wrap;">';
                html += '      <span style="font-size:18px;">📁</span>';
                html += '      <div style="font-size:14px;font-weight:700;color:#fff;">' + displayTitle + '<span style="font-size:12px;color:var(--text-muted);font-weight:normal;margin-left:4px;">' + displayYear + '</span></div>';
                html += '      <span style="background:rgba(56,189,248,0.15);color:#38bdf8;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:700;border:1px solid rgba(56,189,248,0.3);">共 ' + totalEpisodes + ' 集待确认</span>';
                html +=        libBadge + provBadge;
                html += '    </div>';
                html += '    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">';
                html += '      <button class="btn btn-primary" style="padding:4px 12px;font-size:12px;font-weight:700;background:linear-gradient(135deg,#6366f1,#4f46e5);border:none;box-shadow:0 2px 8px rgba(99,102,241,0.35);" onclick="openSeriesBindInline(' + g + ')" title="搜索 TMDB 一键将整部剧 ' + totalEpisodes + ' 个分集批量入库">🔍 一键绑定整部剧 (' + totalEpisodes + '集)</button>';
                html += '      <button class="btn btn-secondary" id="btnToggleGrp_' + g + '" style="padding:4px 10px;font-size:12px;" onclick="toggleSeriesDetail(' + g + ')">展开明细 ▾</button>';
                html += '      <button class="btn btn-outline" style="padding:4px 8px;font-size:12px;color:#f87171;border-color:rgba(239,68,68,0.3);" onclick="deleteSeriesGroup(' + g + ')" title="从暂存箱移除整部剧的所有分集">🗑️ 移除整剧</button>';
                html += '    </div>';
                html += '  </div>';

                // 搜索展开区
                html += '  <div id="unm_grp_search_' + g + '" style="display:none;background:rgba(30,41,59,0.85);border-radius:6px;padding:12px 14px;border:1px solid rgba(99,102,241,0.25);margin-top:4px;">';
                html += '    <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;flex-wrap:wrap;">';
                html += '      <span style="font-size:12px;color:#a5b4fc;font-weight:600;">检索影视:</span>';
                html += '      <input type="text" class="form-input" id="unm_grp_title_input_' + g + '" value="' + displayTitle.replace(/"/g, '&quot;') + '" placeholder="片名" style="width:160px;height:28px;font-size:12px;padding:2px 8px;" onkeydown="if(event.key===\'Enter\')searchSeriesTmdb(' + g + ')">';
                html += '      <input type="text" class="form-input" id="unm_grp_year_input_' + g + '" value="' + (grp.year || '').replace(/"/g, '&quot;') + '" placeholder="年份" style="width:60px;height:28px;font-size:12px;padding:2px 8px;text-align:center;" onkeydown="if(event.key===\'Enter\')searchSeriesTmdb(' + g + ')">';
                html += '      <button class="btn btn-secondary" style="padding:3px 10px;font-size:12px;" onclick="searchSeriesTmdb(' + g + ')">检索 🔍</button>';
                html += '      <button class="btn btn-outline" style="padding:3px 8px;font-size:11px;margin-left:auto;" onclick="document.getElementById(\'unm_grp_search_' + g + '\').style.display=\'none\'">收起 ✕</button>';
                html += '    </div>';
                html += '    <div id="unm_grp_candidates_' + g + '"></div>';
                html += '  </div>';

                // 明细展开区 (表格)
                html += '  <div id="unm_grp_detail_' + g + '" style="display:none;background:rgba(15,23,42,0.4);border-radius:6px;padding:8px;border:1px solid rgba(255,255,255,0.04);margin-top:4px;overflow-x:auto;">';
                html += '    <table style="width:100%;border-collapse:collapse;font-size:12px;">';
                html += '      <thead><tr style="color:var(--text-muted);border-bottom:1px solid rgba(255,255,255,0.08);"><th style="padding:6px 8px;text-align:left;">分集</th><th style="padding:6px 8px;text-align:left;">原文件名</th><th style="padding:6px 8px;text-align:left;">播放链接</th><th style="padding:6px 8px;text-align:center;width:60px;">操作</th></tr></thead>';
                html += '      <tbody>';
                for (var gi = 0; gi < grp.items.length; gi++) {
                    var itm = grp.items[gi];
                    var seBadge = '<span style="background:rgba(56,189,248,0.15);color:#38bdf8;padding:1px 5px;border-radius:4px;font-size:11px;font-weight:700;">S' + (itm.season_number || 1) + 'E' + (itm.episode_number || 1) + '</span>';
                    html += '<tr style="border-bottom:1px solid rgba(255,255,255,0.04);">';
                    html += '  <td style="padding:6px 8px;white-space:nowrap;">' + seBadge + '</td>';
                    html += '  <td style="padding:6px 8px;color:#fff;max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="' + (itm.raw_filename || '').replace(/"/g, '&quot;') + '">' + (itm.raw_filename || '-') + '</td>';
                    html += '  <td style="padding:6px 8px;color:#64748b;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="' + (itm.url || '').replace(/"/g, '&quot;') + '">' + (itm.url || '-') + '</td>';
                    html += '  <td style="padding:6px 8px;text-align:center;"><button class="icon-btn" style="color:#f87171;font-size:12px;padding:2px 4px;" onclick="deleteSingleUnmatchedRecord(\'' + itm.id + '\')" title="从暂存箱移除单集">🗑️</button></td>';
                    html += '</tr>';
                }
                html += '      </tbody>';
                html += '    </table>';
                html += '  </div>';

                html += '</div>';
            }
            container.innerHTML = html;
        }

        function openSeriesBindInline(grpIdx) {
            var box = document.getElementById('unm_grp_search_' + grpIdx);
            if (!box) return;
            box.style.display = 'block';
            searchSeriesTmdb(grpIdx);
        }

        function toggleSeriesDetail(grpIdx) {
            var box = document.getElementById('unm_grp_detail_' + grpIdx);
            var btn = document.getElementById('btnToggleGrp_' + grpIdx);
            if (!box) return;
            if (box.style.display === 'none') {
                box.style.display = 'block';
                if (btn) btn.innerText = '收起明细 ▴';
            } else {
                box.style.display = 'none';
                if (btn) btn.innerText = '展开明细 ▾';
            }
        }

        function searchSeriesTmdb(grpIdx) {
            var titleInput = document.getElementById('unm_grp_title_input_' + grpIdx);
            var yearInput = document.getElementById('unm_grp_year_input_' + grpIdx);
            var candBox = document.getElementById('unm_grp_candidates_' + grpIdx);
            if (!titleInput || !candBox) return;

            var title = titleInput.value.trim();
            var year = yearInput ? yearInput.value.trim() : '';
            if (!title) {
                candBox.innerHTML = '<div style="font-size:12px;color:#f87171;">请输入片名后再搜索</div>';
                return;
            }

            candBox.innerHTML = '<div style="display:flex;align-items:center;gap:10px;font-size:12px;color:#a5b4fc;"><div class="loading-spinner" style="width:16px;height:16px;border-width:2px;"></div> 正在 TMDB 中检索【' + title + (year ? ' (' + year + ')' : '') + '】...</div>';

            fetchTmdbSearch(title, year)
                .then(function(results) {
                    if (!results || results.length === 0) {
                        candBox.innerHTML = '<div style="font-size:12px;color:#94a3b8;padding:8px 0;">未在 TMDB 检索到相关影视条目，建议修改片名重新检索</div>';
                        return;
                    }
                    var candList = [];
                    var cHtml = '<div style="display:grid;grid-template-columns:repeat(auto-fill, minmax(260px, 1fr));gap:8px;margin-top:8px;">';
                    for (var c = 0; c < Math.min(results.length, 6); c++) {
                        var v = results[c];
                        var vTitle = v.title || v.name || v.original_title || '';
                        var vOrig = v.original_title || v.original_name || '';
                        var vYear = v.release_date ? v.release_date.split('-')[0] : (v.first_air_date ? v.first_air_date.split('-')[0] : '');
                        var vPic = v.poster_path ? ('https://image.tmdb.org/t/p/w500' + v.poster_path) : '';
                        var vBackdrop = v.backdrop_path ? ('https://image.tmdb.org/t/p/original' + v.backdrop_path) : '';
                        var vRating = v.vote_average ? v.vote_average.toFixed(1) : '';
                        var isTV = (v.media_type === 'tv');

                        candList.push({
                            id: v.id,
                            tmdbId: v.id,
                            title: vTitle,
                            originalTitle: vOrig,
                            pic: vPic,
                            backdropPath: vBackdrop,
                            year: vYear,
                            media_type: v.media_type,
                            typeId: isTV ? 2 : 1,
                            overview: v.overview || '',
                            remark: vRating ? '评分 ' + vRating : ''
                        });

                        var typeLabel = isTV ? '<span class="badge" style="background:#0284c7;color:#fff;font-size:10px;padding:1px 5px;border-radius:3px;margin-right:4px;">剧集</span>' : '<span class="badge" style="background:#7c3aed;color:#fff;font-size:10px;padding:1px 5px;border-radius:3px;margin-right:4px;">电影</span>';

                        cHtml += '<div class="unm-cand-card" style="display:flex;gap:10px;padding:8px;background:rgba(15,23,42,0.8);border:1px solid rgba(255,255,255,0.08);border-radius:6px;cursor:pointer;align-items:center;" onclick="resolveSeriesWithCandidate(' + grpIdx + ', ' + c + ')">';
                        if (vPic) {
                            cHtml += '<img src="' + vPic + '" style="width:38px;height:54px;object-fit:cover;border-radius:4px;flex-shrink:0;">';
                        } else {
                            cHtml += '<div style="width:38px;height:54px;background:#1e293b;border-radius:4px;flex-shrink:0;display:flex;align-items:center;justify-content:center;">🎬</div>';
                        }
                        cHtml += '<div style="overflow:hidden;flex:1;min-width:0;">';
                        cHtml += '  <div style="font-size:13px;font-weight:700;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + vTitle + '</div>';
                        cHtml += '  <div style="font-size:11px;color:var(--text-muted);margin-top:2px;">' + typeLabel + (vYear ? vYear + ' 年' : '') + (vRating ? ' · ★ ' + vRating : '') + '</div>';
                        cHtml += '  <div style="font-size:11px;color:#38bdf8;margin-top:3px;font-weight:500;">点击选定一键入库整部剧 ✓</div>';
                        cHtml += '</div></div>';
                    }
                    cHtml += '</div>';
                    state.unmatchedSeriesCandidatesMap = state.unmatchedSeriesCandidatesMap || {};
                    state.unmatchedSeriesCandidatesMap[grpIdx] = candList;
                    candBox.innerHTML = cHtml;
                })
                .catch(function(e) {
                    candBox.innerHTML = '<div style="font-size:12px;color:#f87171;">检索异常: ' + e.message + '</div>';
                });
        }

        function resolveSeriesWithCandidate(grpIdx, candIdx) {
            var candList = state.unmatchedSeriesCandidatesMap && state.unmatchedSeriesCandidatesMap[grpIdx];
            if (!candList || !candList[candIdx]) return;

            var grpKeys = Object.keys(state.unmatchedSeriesGroups || {});
            var grpKey = grpKeys[grpIdx];
            var grp = state.unmatchedSeriesGroups[grpKey];
            if (!grp || !grp.items || grp.items.length === 0) return;

            var v = candList[candIdx];
            var ids = grp.items.map(function(it) { return it.id; });

            var payload = {
                unmatched_ids: ids,
                movie: {
                    title: v.title,
                    year: v.year,
                    tmdb_id: v.tmdbId,
                    type_id: v.typeId || 2,
                    cover_url: v.pic,
                    backdrop_url: v.backdropPath,
                    summary: v.overview
                }
            };

            showToast('正在将《' + v.title + '》共 ' + ids.length + ' 个分集批量入库...');
            fetch('/api/private/unmatched/resolve-batch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (!data.success) {
                    showToast('批量转正失败: ' + (data.message || '未知错误'));
                    return;
                }
                showToast('🎉 已成功将《' + v.title + '》共 ' + ids.length + ' 个分集一次性转正入库！');
                loadUnmatchedQueueItems(state.unmatchedCurrentScope);
                if (state.currentLevel === 2) {
                    loadMovies();
                }
            })
            .catch(function(e) {
                showToast('请求异常: ' + e.message);
            });
        }

        function deleteSeriesGroup(grpIdx) {
            var grpKeys = Object.keys(state.unmatchedSeriesGroups || {});
            var grpKey = grpKeys[grpIdx];
            var grp = state.unmatchedSeriesGroups[grpKey];
            if (!grp || !grp.items || grp.items.length === 0) return;
            var ids = grp.items.map(function(it) { return it.id; });
            if (!confirm('确定要从暂存箱移除【' + (grp.title || '此剧集') + '】的全部 ' + ids.length + ' 个分集吗？')) return;

            fetch('/api/private/unmatched/batch-delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ids: ids })
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                showToast('已移除该剧集的 ' + ids.length + ' 个分集');
                loadUnmatchedQueueItems(state.unmatchedCurrentScope);
            });
        }

        function deleteSingleUnmatchedRecord(id) {
            fetch('/api/private/unmatched?id=' + encodeURIComponent(id), { method: 'DELETE' })
                .then(function(res) { return res.json(); })
                .then(function(data) {
                    showToast('已移除该记录');
                    loadUnmatchedQueueItems(state.unmatchedCurrentScope);
                });
        }

        function renderUnmatchedFlatTable() {
            var tbody = document.getElementById('unmatchedQueueTbody');
            var emptyNotice = document.getElementById('unmatchedEmptyNotice');
            var isAllScope = (state.unmatchedCurrentScope === 'all');
            var items = state.unmatchedQueueList || [];

            if (items.length === 0) {
                if (tbody) tbody.innerHTML = '';
                if (emptyNotice) emptyNotice.style.display = 'block';
                return;
            }
            if (emptyNotice) emptyNotice.style.display = 'none';

            var html = '';
            for (var i = 0; i < items.length; i++) {
                var it = items[i];
                var rawLink = it.url || '-';
                var rawName = it.raw_filename || '-';
                var folderName = it.parent_folder_name || '';
                var folderBadge = folderName ? ('<div style="font-size:11px;color:#94a3b8;margin-top:2px;display:flex;align-items:center;gap:4px;" title="所在目录: ' + folderName.replace(/"/g, '&quot;') + '"><span style="opacity:0.7;">📁</span> ' + folderName + '</div>') : '';
                var libCol = isAllScope ? ('<td style="font-size:12px;color:#cbd5e1;"><span class="badge" style="background:rgba(99,102,241,0.15);color:#a5b4fc;border:1px solid rgba(99,102,241,0.3);padding:2px 6px;border-radius:4px;">' + (it.library_name || it.library_id).replace(/"/g, '&quot;') + '</span></td>') : '';

                var titleVal = (it.raw_title || '').replace(/"/g, '&quot;');
                var yearVal = (it.raw_year || '').replace(/"/g, '&quot;');
                if (!titleVal) {
                    if (folderName) {
                        var pFolder = resolveMeaningfulSeriesFolder(folderName);
                        if (pFolder && !isWeakSeriesTitle(pFolder)) {
                            titleVal = pFolder.replace(/"/g, '&quot;');
                        }
                    }
                    if (!titleVal && it.raw_filename) {
                        var cExt = extractTmdbIdAndClean(it.raw_filename);
                        if (cExt && cExt.title && !isWeakSeriesTitle(cExt.title)) {
                            titleVal = cExt.title.replace(/"/g, '&quot;');
                        }
                    }
                }
                if (!yearVal && it.raw_filename) {
                    var cExtY = extractTmdbIdAndClean(it.raw_filename);
                    if (cExtY && cExtY.year) {
                        yearVal = cExtY.year.replace(/"/g, '&quot;');
                    }
                }
                var seBadge = '';
                if (it.season_number > 0 || it.episode_number > 0) {
                    seBadge = '<span style="display:inline-block;background:rgba(56,189,248,0.15);color:#38bdf8;padding:1px 5px;border-radius:4px;font-size:11px;margin-left:4px;">S' + (it.season_number || 1) + 'E' + (it.episode_number || 1) + '</span>';
                }

                var dateStr = '';
                if (it.created_at) {
                    var d = new Date(it.created_at * 1000);
                    var pad = function(n) { return n < 10 ? '0' + n : n; };
                    dateStr = (d.getMonth() + 1) + '-' + pad(d.getDate()) + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
                }

                var reasonHtml = '<span style="font-size:12px;color:#fca5a5;background:rgba(239,68,68,0.12);padding:2px 6px;border-radius:4px;border:1px solid rgba(239,68,68,0.25);" title="' + (it.failure_reason || '').replace(/"/g, '&quot;') + '">' + (it.failure_reason || '未能对齐候选') + '</span>';

                html += '<tr id="unm_q_row_' + i + '">';
                html += '<td style="text-align:center;"><input type="checkbox" class="unm-chk" value="' + it.id + '" onchange="handleUnmatchedRowCheck(this)"></td>';
                html += libCol;
                html += '<td class="raw-filename-cell" style="max-width:240px;word-break:break-all;cursor:pointer;" title="点击查看完整原文件名&#10;' + rawName.replace(/"/g, '&quot;') + '&#10;链接: ' + rawLink.replace(/"/g, '&quot;') + '" onclick="showFullFileNameUnmatchedQueue(' + i + ')">' +
                        '<div style="font-weight:500;color:#fff;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + rawName + '</div>' +
                        folderBadge +
                        '<div style="font-size:11px;color:#64748b;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-top:2px;">' + (it.provider ? '[' + it.provider + '] ' : '') + rawLink + '</div>' +
                        '</td>';

                html += '<td>';
                html += '<div style="display:flex;gap:4px;align-items:center;">';
                html += '<input type="text" class="form-input" id="unm_q_title_' + i + '" value="' + titleVal + '" placeholder="片名" style="padding:2px 6px;height:26px;font-size:12px;width:155px;" onkeydown="if(event.key===\'Enter\')inlineSearchUnmatchedQueue(' + i + ')">';
                html += '<input type="text" class="form-input" id="unm_q_year_' + i + '" value="' + yearVal + '" placeholder="年份" style="padding:2px 4px;height:26px;font-size:12px;width:48px;text-align:center;">';
                html += '</div>';
                html += '<div style="margin-top:2px;">' + (it.remark ? '<span style="font-size:11px;color:#a5b4fc;">' + it.remark + '</span>' : '') + seBadge + '</div>';
                html += '</td>';

                html += '<td style="text-align:center;">';
                html += '<div style="display:flex;gap:4px;justify-content:center;align-items:center;">';
                html += '<button class="btn btn-secondary" style="padding:3px 7px;font-size:11px;white-space:nowrap;" onclick="inlineSearchUnmatchedQueue(' + i + ')" title="微调片名并在 TMDB 中搜索绑定">🔍 绑定</button>';
                html += '<button class="btn btn-outline" style="padding:3px 7px;font-size:11px;white-space:nowrap;border-color:rgba(16,185,129,0.4);color:#6ee7b7;" onclick="customCreateFromUnmatchedQueue(' + i + ')" title="直接以此名称自建入库">➕ 自建</button>';
                html += '<button class="btn btn-outline" style="padding:3px 6px;font-size:11px;color:#f87171;border-color:rgba(239,68,68,0.3);" onclick="deleteSingleUnmatchedQueue(' + i + ')" title="从暂存箱移除此条记录">🗑️</button>';
                html += '</div>';
                html += '</td>';

                html += '<td>' + reasonHtml + '</td>';
                html += '<td style="text-align:center;font-size:11px;color:#94a3b8;">' + dateStr + '</td>';
                html += '</tr>';

                html += '<tr id="unm_q_expand_' + i + '" style="display:none;"><td colspan="7" style="background:rgba(15,23,42,0.85);padding:10px 16px;border-bottom:1px solid rgba(99,102,241,0.2);"><div id="unm_q_candidates_' + i + '" style="display:flex;flex-direction:column;gap:8px;"></div></td></tr>';
            }
            if (tbody) tbody.innerHTML = html;
        }

        function showFullFileNameUnmatchedQueue(idx) {
            var item = state.unmatchedQueueList && state.unmatchedQueueList[idx];
            if (!item) return;
            var name = item.raw_filename || item.raw_title || '-';
            var lines = [];
            if (item.raw_filename) {
                lines.push('📄 原始文件：' + item.raw_filename);
            } else if (item.raw_title) {
                lines.push('📄 识别片名：' + item.raw_title);
            }
            if (item.parent_folder_name) {
                lines.push('📁 所在目录：' + item.parent_folder_name);
            }
            if (item.url) {
                lines.push('🔗 资源链接：' + (item.provider ? '[' + item.provider + '] ' : '') + item.url);
            }
            var displayContent = lines.length > 0 ? lines.join('\n\n') : name;
            var titleEl = document.getElementById('fullFileNameTitle');
            var textEl = document.getElementById('fullFileNameText');
            if (titleEl) titleEl.innerText = '📄 完整原文件名与来源 (暂存箱 #' + (idx + 1) + ')';
            if (textEl) {
                textEl.innerText = displayContent;
                textEl.setAttribute('data-content', item.raw_filename || name);
            }
            openModal('fullFileNameModal');
        }

        function handlePreviewUnmatchedQueue(idx, c) {
            var candList = state.unmatchedQueueCandidatesMap && state.unmatchedQueueCandidatesMap[idx];
            if (!candList || !candList[c]) return;
            var cand = candList[c];
            openTmdbPreviewModal(idx, cand, true, function() {
                resolveUnmatchedWithCandidate(idx, c);
            });
        }

        function inlineSearchUnmatchedQueue(idx) {
            var item = state.unmatchedQueueList[idx];
            if (!item) return;
            var titleInput = document.getElementById('unm_q_title_' + idx);
            var yearInput = document.getElementById('unm_q_year_' + idx);
            var title = (titleInput ? titleInput.value : item.raw_title || '').trim();
            var year = (yearInput ? yearInput.value : item.raw_year || '').trim();

            var expandRow = document.getElementById('unm_q_expand_' + idx);
            var candBox = document.getElementById('unm_q_candidates_' + idx);
            if (!expandRow || !candBox) return;

            expandRow.style.display = '';
            candBox.innerHTML = '<div style="display:flex;align-items:center;gap:10px;font-size:12px;color:#a5b4fc;"><div class="loading-spinner" style="width:16px;height:16px;border-width:2px;"></div> 正在 TMDB 中检索【' + title + (year ? ' (' + year + ')' : '') + '】...</div>';

            fetchTmdbSearch(title, year)
                .then(function(results) {
                    if (!results || results.length === 0) {
                        candBox.innerHTML = '<div style="display:flex;align-items:center;justify-content:space-between;font-size:12px;color:#94a3b8;">' +
                            '<span>未在 TMDB 检索到相关影视条目，建议修改片名重新点击【🔍 绑定】或直接自建入库</span>' +
                            '<button class="btn btn-secondary" style="padding:2px 8px;font-size:11px;" onclick="document.getElementById(\'unm_q_expand_' + idx + '\').style.display=\'none\'">收起 ✕</button>' +
                            '</div>';
                        return;
                    }

                    var candList = [];
                    for (var c = 0; c < Math.min(results.length, 6); c++) {
                        var v = results[c];
                        var vTitle = v.title || v.name || v.original_title || '';
                        var vOrig = v.original_title || v.original_name || '';
                        var vYear = v.release_date ? v.release_date.split('-')[0] : (v.first_air_date ? v.first_air_date.split('-')[0] : '');
                        var vPic = v.poster_path ? ('https://image.tmdb.org/t/p/w500' + v.poster_path) : '';
                        var vBackdrop = v.backdrop_path ? ('https://image.tmdb.org/t/p/original' + v.backdrop_path) : '';
                        var vRating = v.vote_average ? v.vote_average.toFixed(1) : '';
                        var isTV = (v.media_type === 'tv');

                        candList.push({
                            id: v.id,
                            tmdbId: v.id,
                            title: vTitle,
                            originalTitle: vOrig,
                            pic: vPic,
                            poster_path: v.poster_path,
                            backdropPath: vBackdrop,
                            backdrop_path: v.backdrop_path,
                            year: vYear,
                            release_date: v.release_date,
                            first_air_date: v.first_air_date,
                            media_type: v.media_type,
                            typeId: isTV ? 2 : 1,
                            director: '',
                            starring: '',
                            content: v.overview || '',
                            overview: v.overview || '',
                            remark: vRating ? '评分 ' + vRating : '',
                            vote_average: v.vote_average,
                            isTmdb: true
                        });
                    }

                    state.unmatchedQueueCandidatesMap = state.unmatchedQueueCandidatesMap || {};
                    state.unmatchedQueueCandidatesMap[idx] = candList;

                    var cHtml = '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid rgba(255,255,255,0.1);">' +
                        '<div style="font-size:12px;color:#a5b4fc;font-weight:600;display:flex;align-items:center;gap:6px;">' +
                        '<span>🔍 TMDB 候选匹配结果</span>' +
                        '<span style="font-size:11px;color:#94a3b8;font-weight:normal;">(可点击【🔍 详情】核对演职员与剧情，或点击卡片直接转正入库)</span>' +
                        '</div>' +
                        '<button class="icon-btn" style="padding:2px 8px;font-size:11px;" onclick="document.getElementById(\'unm_q_expand_' + idx + '\').style.display=\'none\'">收起 ✕</button>' +
                        '</div>';
                    cHtml += '<div style="display:flex;gap:10px;overflow-x:auto;padding-bottom:6px;">';

                    for (var i = 0; i < candList.length; i++) {
                        var card = candList[i];
                        var typeLabel = (card.typeId === 2) ? '<span style="display:inline-block;font-size:10px;padding:1px 4px;border-radius:3px;background:rgba(99,102,241,0.25);color:#a5b4fc;margin-right:4px;">剧集</span>' : '<span style="display:inline-block;font-size:10px;padding:1px 4px;border-radius:3px;background:rgba(148,163,184,0.2);color:#94a3b8;margin-right:4px;">电影</span>';
                        cHtml += '<div style="display:flex;gap:10px;background:rgba(30,41,59,0.85);border:1px solid var(--card-border);border-radius:8px;padding:8px;min-width:240px;max-width:295px;cursor:pointer;align-items:center;position:relative;transition:border-color 0.2s, background-color 0.2s;" onmouseover="this.style.borderColor=\'var(--accent-color)\';this.style.background=\'rgba(45,55,72,0.95)\'" onmouseout="this.style.borderColor=\'var(--card-border)\';this.style.background=\'rgba(30,41,59,0.85)\'" onclick="resolveUnmatchedWithCandidate(' + idx + ', ' + i + ')">';
                        cHtml += '<button type="button" class="btn-card-detail" title="全屏查看影视完整详情 (演职员/剧照/剧情，按ESC退出)" onclick="event.stopPropagation(); handlePreviewUnmatchedQueue(' + idx + ', ' + i + ')" style="position:absolute;top:6px;right:6px;background:rgba(15,23,42,0.85);border:1px solid rgba(255,255,255,0.2);color:#38bdf8;font-size:10px;padding:2px 6px;border-radius:4px;cursor:pointer;display:inline-flex;align-items:center;gap:2px;z-index:3;line-height:1.2;box-shadow:0 1px 3px rgba(0,0,0,0.5);" onmouseover="this.style.borderColor=\'#38bdf8\';this.style.color=\'#fff\'" onmouseout="this.style.borderColor=\'rgba(255,255,255,0.2)\';this.style.color=\'#38bdf8\'">🔍 详情</button>';
                        cHtml += '<div style="position:relative;flex-shrink:0;" onclick="event.stopPropagation(); handlePreviewUnmatchedQueue(' + idx + ', ' + i + ')" title="点击查看 TMDB 完整详情">';
                        if (card.pic) {
                            cHtml += '<img referrerpolicy="no-referrer" src="' + card.pic + '" style="width:46px;height:66px;object-fit:cover;border-radius:4px;box-shadow:0 2px 4px rgba(0,0,0,0.5);display:block;cursor:zoom-in;" onerror="this.onerror=null;this.style.display=\'none\';if(this.nextElementSibling)this.nextElementSibling.style.display=\'flex\';">';
                            cHtml += '<div style="display:none;width:46px;height:66px;background:#1e293b;border-radius:4px;align-items:center;justify-content:center;font-size:18px;">🎬</div>';
                        } else {
                            cHtml += '<div style="width:46px;height:66px;background:#1e293b;border-radius:4px;display:flex;align-items:center;justify-content:center;font-size:18px;">🎬</div>';
                        }
                        cHtml += '<div style="position:absolute;top:2px;left:2px;font-size:9px;color:#fff;background:linear-gradient(135deg,#6366f1,#4f46e5);padding:1px 4px;border-radius:3px;font-weight:600;box-shadow:0 1px 3px rgba(0,0,0,0.6);line-height:1.2;">TMDB</div>';
                        cHtml += '</div>';
                        cHtml += '<div style="overflow:hidden;flex:1;min-width:0;padding-right:38px;"><div style="font-size:13px;font-weight:700;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="' + card.title.replace(/"/g, '&quot;') + '">' + card.title + '</div>';
                        if (card.originalTitle && card.originalTitle !== card.title) {
                            cHtml += '<div style="font-size:11px;color:#a5b4fc;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:2px;" title="' + card.originalTitle.replace(/"/g, '&quot;') + '">' + card.originalTitle + '</div>';
                        }
                        cHtml += '<div style="font-size:11px;color:var(--text-muted);margin-top:2px;">' + typeLabel + (card.year ? card.year + ' 年' : '') + (card.remark ? ' · ' + card.remark : '') + '</div>';
                        cHtml += '<div style="font-size:11px;color:#38bdf8;margin-top:3px;font-weight:500;">点击选定绑定 ✓</div></div>';
                        cHtml += '</div>';
                    }
                    cHtml += '</div>';
                    candBox.innerHTML = cHtml;
                })
                .catch(function(e) {
                    candBox.innerHTML = '<div style="font-size:12px;color:#f87171;">搜索失败: ' + e.message + '</div>';
                });
        }

        function resolveUnmatchedWithCandidate(idx, candIdx) {
            var item = state.unmatchedQueueList[idx];
            var candList = state.unmatchedQueueCandidatesMap && state.unmatchedQueueCandidatesMap[idx];
            if (!item || !candList || !candList[candIdx]) return;

            var v = candList[candIdx];
            var vTitle = v.title || v.name || v.original_title || '';
            var vYear = v.release_date ? v.release_date.split('-')[0] : (v.first_air_date ? v.first_air_date.split('-')[0] : (v.year || ''));
            var isTV = (v.media_type === 'tv' || v.typeId === 2);

            var payload = {
                unmatched_id: item.id,
                movie: {
                    title: vTitle,
                    year: vYear,
                    tmdb_id: v.tmdbId || v.id,
                    type_id: isTV ? 2 : 1,
                    cover_url: v.pic || (v.poster_path ? ('https://image.tmdb.org/t/p/w500' + v.poster_path) : ''),
                    backdrop_url: v.backdropPath || (v.backdrop_path ? ('https://image.tmdb.org/t/p/original' + v.backdrop_path) : ''),
                    summary: v.content || v.overview || ''
                }
            };

            showToast('正在绑定并加入媒体库...');
            fetch('/api/private/unmatched/resolve', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (!data.success) {
                    showToast('绑定入库失败: ' + (data.message || '未知错误'));
                    return;
                }
                showToast('已成功将【' + vTitle + '】转正入库！');

                // 级联同剧推荐：严格仅当确认为剧集 (isTV) 时才执行，电影坚决不执行同剧推荐！
                if (isTV) {
                    var itemMeanDir = resolveMeaningfulSeriesFolder(item.parent_folder_name);
                    var remainingSameSeriesIds = [];
                    for (var r = 0; r < state.unmatchedQueueList.length; r++) {
                        var other = state.unmatchedQueueList[r];
                        if (other.id === item.id) continue;
                        var otherMeanDir = resolveMeaningfulSeriesFolder(other.parent_folder_name);
                        var sameDir = (itemMeanDir && otherMeanDir && itemMeanDir.toLowerCase() === otherMeanDir.toLowerCase() && !isWeakSeriesTitle(itemMeanDir));
                        var sameTitle = (!isWeakSeriesTitle(item.raw_title) && !isWeakSeriesTitle(other.raw_title) && item.raw_title.toLowerCase() === other.raw_title.toLowerCase());
                        if (sameTitle || sameDir) {
                            remainingSameSeriesIds.push(other.id);
                        }
                    }

                    if (remainingSameSeriesIds.length > 0) {
                        if (confirm('🎉 已成功转正当前分集！\n\n💡 系统检测到暂存箱中还有 ' + remainingSameSeriesIds.length + ' 个属于剧集【' + vTitle + '】的同剧分集文件。\n是否一键将这 ' + remainingSameSeriesIds.length + ' 个分集全部转正入库？')) {
                            showToast('正在批量转正剩余 ' + remainingSameSeriesIds.length + ' 个分集...');
                            fetch('/api/private/unmatched/resolve-batch', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({
                                    unmatched_ids: remainingSameSeriesIds,
                                    movie_id: data.movie_id,
                                    movie: payload.movie
                                })
                            })
                            .then(function(r2) { return r2.json(); })
                            .then(function(d2) {
                                showToast('🎉 成功将同剧剩余 ' + remainingSameSeriesIds.length + ' 个分集全部转正入库！');
                                loadUnmatchedQueueItems(state.unmatchedCurrentScope);
                                if (state.currentLevel === 2) loadMovies();
                            })
                            .catch(function(err2) {
                                showToast('批量转正失败: ' + err2.message);
                                loadUnmatchedQueueItems(state.unmatchedCurrentScope);
                            });
                            return;
                        }
                    }
                }

                loadUnmatchedQueueItems(state.unmatchedCurrentScope);
                if (state.currentLevel === 2) {
                    loadMovies();
                }
            })
            .catch(function(e) {
                showToast('请求异常: ' + e.message);
            });
        }

        function customCreateFromUnmatchedQueue(idx) {
            var item = state.unmatchedQueueList[idx];
            if (!item) return;
            var titleInput = document.getElementById('unm_q_title_' + idx);
            var yearInput = document.getElementById('unm_q_year_' + idx);
            var currentTitle = (titleInput ? titleInput.value : item.raw_title || '').trim();
            var currentYear = (yearInput ? yearInput.value : item.raw_year || '').trim();

            var newTitle = prompt('请输入要自建的影片片名：', currentTitle);
            if (newTitle === null) return;
            newTitle = newTitle.trim();
            if (!newTitle) {
                showToast('片名不能为空');
                return;
            }

            var payload = {
                unmatched_id: item.id,
                movie: {
                    title: newTitle,
                    year: currentYear,
                    type_id: (item.season_number > 1 || item.episode_number > 1) ? 2 : 1
                }
            };

            showToast('正在自建入库...');
            fetch('/api/private/unmatched/resolve', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (!data.success) {
                    showToast('自建入库失败: ' + (data.message || '未知错误'));
                    return;
                }
                showToast('已成功自建入库【' + newTitle + '】！');
                loadUnmatchedQueueItems(state.unmatchedCurrentScope);
                if (state.currentLevel === 2) {
                    loadMovies();
                }
            })
            .catch(function(e) {
                showToast('自建请求异常: ' + e.message);
            });
        }

        function deleteSingleUnmatchedQueue(idx) {
            var item = state.unmatchedQueueList[idx];
            if (!item) return;
            if (!confirm('确定要从暂存箱移除该条记录吗？')) return;

            fetch('/api/private/unmatched?id=' + encodeURIComponent(item.id), {
                method: 'DELETE'
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (data.success) {
                    showToast('已移除该记录');
                    loadUnmatchedQueueItems(state.unmatchedCurrentScope);
                } else {
                    showToast('移除失败: ' + data.message);
                }
            })
            .catch(function(e) {
                showToast('删除请求失败: ' + e.message);
            });
        }

        function handleUnmatchedRowCheck(chk) {
            var id = chk.value;
            if (chk.checked) {
                if (state.unmatchedQueueSelectedIds.indexOf(id) === -1) {
                    state.unmatchedQueueSelectedIds.push(id);
                }
            } else {
                var idx = state.unmatchedQueueSelectedIds.indexOf(id);
                if (idx !== -1) {
                    state.unmatchedQueueSelectedIds.splice(idx, 1);
                }
            }
            updateUnmatchedBatchDelBtn();
        }

        function toggleSelectAllUnmatched(checked) {
            var chks = document.querySelectorAll('.unm-chk');
            state.unmatchedQueueSelectedIds = [];
            for (var i = 0; i < chks.length; i++) {
                chks[i].checked = checked;
                if (checked) {
                    state.unmatchedQueueSelectedIds.push(chks[i].value);
                }
            }
            updateUnmatchedBatchDelBtn();
        }

        function updateUnmatchedBatchDelBtn() {
            var btnDel = document.getElementById('btnUnmatchedBatchDel');
            var btnBind = document.getElementById('btnUnmatchedBatchBind');
            var cntDel = document.getElementById('unmatchedSelectedCount');
            var cntBind = document.getElementById('unmatchedBatchBindCount');
            var cntRetry = document.getElementById('unmatchedRetryCount');
            var num = state.unmatchedQueueSelectedIds.length;
            if (cntDel) cntDel.innerText = num;
            if (cntBind) cntBind.innerText = num;
            if (cntRetry) cntRetry.innerText = num > 0 ? (num + ' 条选定项') : '全部';
            if (num > 0) {
                if (btnDel) btnDel.style.display = 'inline-flex';
                if (btnBind) btnBind.style.display = 'inline-flex';
            } else {
                if (btnDel) btnDel.style.display = 'none';
                if (btnBind) btnBind.style.display = 'none';
            }
        }

        function applyUnmatchedQueueBatchBindConfirm(cand, ids) {
            if (!cand || !ids || ids.length === 0) return;

            var cleanedTarget = cleanSeasonFromTitle(cand.title || cand.name || '');
            var cleanTitle = cleanedTarget.title || cand.title || cand.name || '';
            var vYear = cand.release_date ? cand.release_date.split('-')[0] : (cand.first_air_date ? cand.first_air_date.split('-')[0] : (cand.year || ''));
            var isTV = (cand.media_type === 'tv') || (cand.typeId === 2) || (cleanedTarget.season >= 0);

            var movieData = {
                title: cleanTitle,
                year: String(vYear || ''),
                tmdb_id: cand.tmdbId || cand.id || 0,
                type_id: isTV ? 2 : 1,
                cover_url: cand.poster_path ? (cand.poster_path.startsWith('http') ? cand.poster_path : ('https://image.tmdb.org/t/p/w500' + cand.poster_path)) : (cand.pic || ''),
                backdrop_url: cand.backdrop_path ? (cand.backdrop_path.startsWith('http') ? cand.backdrop_path : ('https://image.tmdb.org/t/p/original' + cand.backdrop_path)) : (cand.backdropPath || ''),
                summary: cand.overview || cand.content || ''
            };

            closeModal('batchBindModal');
            showToast('正在批量转正入库...');
            fetch('/api/private/unmatched/resolve-batch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    unmatched_ids: ids,
                    movie: movieData
                })
            })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.success) {
                    showToast('🎉 成功将选中的 ' + ids.length + ' 个分集批量绑定入库！');
                    state.unmatchedQueueSelectedIds = [];
                    var chkAll = document.getElementById('unmatchedSelectAll');
                    if (chkAll) chkAll.checked = false;
                    updateUnmatchedBatchDelBtn();
                    loadUnmatchedQueueItems(state.unmatchedCurrentScope);
                    if (state.currentLevel === 2) loadMovies();
                } else {
                    showToast('批量转正失败: ' + data.message);
                }
            })
            .catch(function(err) {
                showToast('批量转正异常: ' + err.message);
            });
        }

        function handleUnmatchedBatchBind() {
            var ids = state.unmatchedQueueSelectedIds || [];
            if (ids.length === 0) {
                showToast('请先勾选要批量绑定的条目');
                return;
            }

            // 查找第一条勾选条目的片名和年份作为默认搜索条件
            var defaultTitle = '';
            var defaultYear = '';
            for (var i = 0; i < state.unmatchedQueueList.length; i++) {
                var item = state.unmatchedQueueList[i];
                if (ids.indexOf(item.id) !== -1) {
                    if (!defaultTitle && item.raw_title) {
                        var cleanT = cleanSeasonFromTitle(item.raw_title);
                        defaultTitle = cleanT.title || item.raw_title;
                    }
                    if (!defaultYear && item.raw_year) defaultYear = item.raw_year;
                    if (defaultTitle && defaultYear) break;
                }
            }

            if (defaultTitle) {
                var cObj = extractTmdbIdAndClean(defaultTitle);
                if (cObj.title) defaultTitle = cObj.title;
                if (!defaultYear && cObj.year) defaultYear = cObj.year;
            }

            openUniversalBatchBindModal({
                mode: 'unmatched_queue',
                ids: ids,
                count: ids.length,
                defaultTitle: defaultTitle,
                defaultYear: defaultYear,
                onConfirm: function(selectedCand) {
                    applyUnmatchedQueueBatchBindConfirm(selectedCand, ids);
                }
            });
        }

        function handleUnmatchedBatchDelete() {
            if (!state.unmatchedQueueSelectedIds || state.unmatchedQueueSelectedIds.length === 0) return;
            if (!confirm('确定要批量移除选中的 ' + state.unmatchedQueueSelectedIds.length + ' 条待确认记录吗？')) return;

            fetch('/api/private/unmatched/batch-delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ids: state.unmatchedQueueSelectedIds })
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (data.success) {
                    showToast('已成功批量移除 ' + state.unmatchedQueueSelectedIds.length + ' 条记录');
                    state.unmatchedQueueSelectedIds = [];
                    var chkAll = document.getElementById('unmatchedSelectAll');
                    if (chkAll) chkAll.checked = false;
                    updateUnmatchedBatchDelBtn();
                    loadUnmatchedQueueItems(state.unmatchedCurrentScope);
                } else {
                    showToast('批量删除失败: ' + data.message);
                }
            })
            .catch(function(e) {
                showToast('批量删除异常: ' + e.message);
            });
        }

        function handleUnmatchedRetry() {
            var selectedIds = state.unmatchedQueueSelectedIds || [];
            var isAll = (state.unmatchedCurrentScope === 'all');
            var libId = isAll ? '' : state.unmatchedCurrentScope;
            var tip = selectedIds.length > 0
                ? '确定要对选中的 ' + selectedIds.length + ' 条待确认记录重新执行智能别名库与 TMDB 自动对齐吗？'
                : '确定要对当前列表中的全部待确认记录重新执行智能别名库与 TMDB 自动对齐吗？';
            if (!confirm(tip)) return;

            showToast('正在重新对齐中，请稍候...');
            var btn = document.getElementById('btnUnmatchedRetry');
            if (btn) btn.disabled = true;

            fetch('/api/private/unmatched/retry', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    library_id: libId,
                    unmatched_ids: selectedIds
                })
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (btn) btn.disabled = false;
                if (data.success) {
                    showToast(data.message || '重新对齐完成');
                    state.unmatchedQueueSelectedIds = [];
                    var chkAll = document.getElementById('unmatchedSelectAll');
                    if (chkAll) chkAll.checked = false;
                    updateUnmatchedBatchDelBtn();
                    loadUnmatchedQueueItems(state.unmatchedCurrentScope);
                    if (state.currentLibraryId) {
                        loadMovies(state.currentLibraryId);
                    }
                } else {
                    showToast('重新对齐失败: ' + data.message);
                }
            })
            .catch(function(e) {
                if (btn) btn.disabled = false;
                showToast('重新对齐异常: ' + e.message);
            });
        }

        function clearCurrentUnmatchedQueue() {
            var isAll = (state.unmatchedCurrentScope === 'all');
            var confirmMsg = isAll ? '确定要清空全部媒体库的待确认暂存箱吗？' : '确定要清空当前媒体库的待确认暂存箱吗？';
            if (!confirm(confirmMsg)) return;

            fetch('/api/private/unmatched/clear', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ library_id: isAll ? '' : state.unmatchedCurrentScope })
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (data.success) {
                    showToast('已清空暂存箱');
                    loadUnmatchedQueueItems(state.unmatchedCurrentScope);
                } else {
                    showToast('清空失败: ' + data.message);
                }
            })
            .catch(function(e) {
                showToast('清空异常: ' + e.message);
            });
        }

        function exportUnmatchedQueueToExcel() {
            var items = state.unmatchedQueueList || [];
            if (items.length === 0) {
                showToast('当前暂存箱没有任何记录可导出');
                return;
            }

            function doExport() {
                var rawList = [];
                for (var i = 0; i < items.length; i++) {
                    var it = items[i];
                    var titleInput = document.getElementById('unm_q_title_' + i);
                    var yearInput = document.getElementById('unm_q_year_' + i);
                    var curTitle = (titleInput ? titleInput.value.trim() : '') || it.raw_title || '';
                    var curYear = (yearInput ? yearInput.value.trim() : '') || it.raw_year || '';

                    var sVal = (it.season_number !== undefined && it.season_number !== null && it.season_number > 0) ? it.season_number : '';
                    var eVal = (it.episode_number !== undefined && it.episode_number !== null && it.episode_number > 0) ? it.episode_number : '';
                    if (!sVal && !eVal && it.raw_filename) {
                        var seM = it.raw_filename.match(/[sS](\d+)[eE](\d+)/i) || it.raw_filename.match(/第?\s*(\d+)\s*季\s*第?\s*(\d+)\s*集/i);
                        if (seM) {
                            sVal = parseInt(seM[1], 10) || 1;
                            eVal = parseInt(seM[2], 10) || 1;
                        } else {
                            var epM = it.raw_filename.match(/(?:[eE]|第|\b)(\d{1,3})(?:集|\b|\.mp4|\.mkv)/i);
                            if (epM) {
                                eVal = parseInt(epM[1], 10) || 1;
                                sVal = 1;
                            }
                        }
                    }

                    var parentFolder = it.parent_folder_name || '';
                    var meaningfulFolder = resolveMeaningfulSeriesFolder(parentFolder);
                    var effectiveTitle = !isWeakSeriesTitle(curTitle) ? curTitle : (meaningfulFolder || '');

                    var groupKey = '';
                    if (!isWeakSeriesTitle(effectiveTitle)) {
                        groupKey = 'title:' + effectiveTitle.toLowerCase() + (curYear ? ('_' + curYear) : '');
                    } else {
                        groupKey = 'single:' + (it.id || ('queue_' + i));
                    }

                    rawList.push({
                        title: effectiveTitle || curTitle,
                        year: curYear,
                        season: sVal,
                        episode: eVal,
                        url: it.url || '',
                        password: it.password || '',
                        remark: it.remark || '',
                        raw_filename: it.raw_filename || '',
                        parent_folder_name: parentFolder,
                        failure_reason: it.failure_reason || '未能对齐候选',
                        groupKey: groupKey
                    });
                }

                // 剧集聚合分组：同剧分集归类排列，首行输出片名/年份，后续分集留空自动继承
                var groups = {};
                var groupOrder = [];
                for (var g = 0; g < rawList.length; g++) {
                    var itm = rawList[g];
                    if (!groups[itm.groupKey]) {
                        groups[itm.groupKey] = [];
                        groupOrder.push(itm.groupKey);
                    }
                    groups[itm.groupKey].push(itm);
                }

                var rows = [];
                for (var go = 0; go < groupOrder.length; go++) {
                    var gItems = groups[groupOrder[go]];
                    gItems.sort(function(a, b) {
                        var aSea = parseInt(a.season, 10) || 1;
                        var bSea = parseInt(b.season, 10) || 1;
                        if (aSea !== bSea) return aSea - bSea;
                        var aEp = parseInt(a.episode, 10) || 0;
                        var bEp = parseInt(b.episode, 10) || 0;
                        return aEp - bEp;
                    });

                    for (var gi = 0; gi < gItems.length; gi++) {
                        var item = gItems[gi];
                        var isFirstInGroup = (gi === 0);
                        rows.push({
                            '片名': isFirstInGroup ? (item.title || item.raw_filename) : '',
                            '年份': isFirstInGroup ? item.year : '',
                            '季数': item.season,
                            '集数': item.episode,
                            '播放链接': item.url,
                            '提取码': item.password,
                            '备注': item.remark,
                            '原文件名': item.raw_filename,
                            '所在目录': item.parent_folder_name,
                            '待确认原因': item.failure_reason
                        });
                    }
                }

                try {
                    var ws = XLSX.utils.json_to_sheet(rows, {
                        header: ['片名', '年份', '季数', '集数', '播放链接', '提取码', '备注', '原文件名', '所在目录', '待确认原因']
                    });
                    ws['!cols'] = [
                        { wch: 22 }, { wch: 8 }, { wch: 8 }, { wch: 8 },
                        { wch: 50 }, { wch: 10 }, { wch: 18 }, { wch: 35 },
                        { wch: 22 }, { wch: 22 }
                    ];
                    var wb = XLSX.utils.book_new();
                    XLSX.utils.book_append_sheet(wb, ws, '待确认暂存箱');

                    var scopeName = '全部媒体库';
                    if (state.unmatchedCurrentScope !== 'all') {
                        for (var k = 0; k < state.libraries.length; k++) {
                            if (state.libraries[k].id === state.unmatchedCurrentScope) {
                                scopeName = state.libraries[k].name;
                                break;
                            }
                        }
                    }
                    var cleanScope = scopeName.replace(/[/\\?%*:|"<>]/g, '_');
                    var now = new Date();
                    var pad = function(n) { return n < 10 ? '0' + n : n; };
                    var ts = now.getFullYear() + '' + pad(now.getMonth() + 1) + '' + pad(now.getDate()) + '_' + pad(now.getHours()) + '' + pad(now.getMinutes());
                    var fileName = '待确认暂存箱_' + cleanScope + '_' + ts + '.xlsx';

                    XLSX.writeFile(wb, fileName);
                    showToast('已成功导出 ' + rows.length + ' 条待确认记录至表格（已按剧集聚合：同剧分集只需在首行修改片名/年份，重新导入时自动继承）！');
                } catch (e) {
                    console.error('[exportUnmatchedQueueToExcel] error:', e);
                    showToast('导出 Excel 失败: ' + e.message);
                }
            }

            if (typeof XLSX === 'undefined') {
                showToast('正在加载表格导出组件...');
                var s = document.createElement('script');
                s.src = 'https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js';
                s.onload = doExport;
                s.onerror = function() { showToast('加载表格组件失败，请检查网络'); };
                document.head.appendChild(s);
            } else {
                doExport();
            }
        }

        function toggleApiCheatSheet() {
            var box = document.getElementById('apiCheatSheetBox');
            if (!box) return;
            box.style.display = (box.style.display === 'none') ? 'block' : 'none';
        }

        function getWritableLibraries() {
            return (state.libraries || []).filter(function(l) {
                return l.share_type !== 2;
            });
        }



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
