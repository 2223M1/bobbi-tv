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

