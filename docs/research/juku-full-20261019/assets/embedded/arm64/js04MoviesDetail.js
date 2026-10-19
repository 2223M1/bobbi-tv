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
