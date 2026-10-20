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

