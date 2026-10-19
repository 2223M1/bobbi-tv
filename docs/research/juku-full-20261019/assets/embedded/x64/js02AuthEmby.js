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


