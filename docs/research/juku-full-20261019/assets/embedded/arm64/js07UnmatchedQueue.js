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

