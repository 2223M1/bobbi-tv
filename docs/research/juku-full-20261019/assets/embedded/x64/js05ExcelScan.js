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

