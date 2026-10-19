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


