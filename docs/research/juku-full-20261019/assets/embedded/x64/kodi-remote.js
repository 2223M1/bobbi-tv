
(function() {
    /* ==================== DOM 模板注入 ==================== */
    const remoteDOMTemplate = `
    <!-- 全局后台异步任务进度条常驻卡片 (浮动在右下角遥控器上方) -->
    <div id="globalAsyncTaskBar" class="global-async-task-bar" style="display: none;">
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
            <span style="font-size: 13px; font-weight: 600; color: #a5b4fc; display: flex; align-items: center; gap: 6px;" id="globalAsyncTitle">
                <span class="async-task-spinner"></span>
                <span>⚡ 后台全自动导入进行中</span>
            </span>
            <span style="font-size: 12px; color: #38bdf8; font-weight: 700;" id="globalAsyncPercent">10%</span>
        </div>
        <div style="font-size: 12px; color: #94a3b8; line-height: 1.4; margin-bottom: 10px; max-height: 48px; overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;" id="globalAsyncStage">正在扫描网盘目录...</div>
        <div style="width: 100%; height: 4px; background: rgba(255,255,255,0.1); border-radius: 9999px; overflow: hidden;">
            <div id="globalAsyncBar" style="width: 10%; height: 100%; background: linear-gradient(90deg, #6366f1, #38bdf8); transition: width 0.3s ease;"></div>
        </div>
        <div style="display: flex; justify-content: flex-end; gap: 8px; margin-top: 10px;">
            <button type="button" style="padding: 4px 10px; font-size: 11px; background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.15); color: #cbd5e1; border-radius: 6px; cursor: pointer;" id="btnCancelGlobalAsyncTask" onclick="cancelCurrentGlobalImportTask()">⏹️ 取消任务</button>
            <button type="button" style="padding: 4px 10px; font-size: 11px; background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.15); color: #cbd5e1; border-radius: 6px; cursor: pointer;" onclick="collapseGlobalAsyncTaskBar()">收起小窗 ↘</button>
        </div>
    </div>

    <!-- 收起后常驻悬浮微型胶囊指示器 -->
    <div id="globalAsyncTaskBadge" class="global-async-task-badge" onclick="expandGlobalAsyncTaskBar()" style="display: none;" title="点击展开导入进度详情">
        <span class="async-task-spinner" id="globalAsyncBadgeSpinner"></span>
        <span style="font-size: 12px; font-weight: 700; color: #a5b4fc;" id="globalAsyncBadgeText">⚡ 导入中 10%</span>
    </div>

    <!-- 右下角悬浮遥控器入口按钮 -->
    <div id="remote-fab" class="remote-fab" onclick="checkKodiStatusAndOpenRemote()" title="遥控器">
        <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="6" y="2" width="12" height="20" rx="4" ry="4"></rect>
            <circle cx="12" cy="7" r="1.5"></circle>
            <polygon points="12,10 14,12 12,14 10,12"></polygon>
            <circle cx="9" cy="17" r="1"></circle>
            <circle cx="15" cy="17" r="1"></circle>
        </svg>
        <span class="fab-pulse-dot" id="fab-playing-dot" style="display:none;"></span>
    </div>

    <!-- 全局 Mini 播放控制条 -->
    <div id="mini-player-bar" class="mini-player-bar" style="display: none;">
        <div class="mini-progress-bg">
            <div id="mini-progress-fill" class="mini-progress-fill" style="width: 0%;"></div>
        </div>
        <div class="mini-content" onclick="openRemoteModal()">
            <img id="mini-poster" class="mini-poster" referrerpolicy="no-referrer" src="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg'/>" alt="cover">
            <div class="mini-info">
                <div id="mini-title" class="mini-title">正在播放...</div>
                <div id="mini-time-str" class="mini-time-str">00:00 / 00:00</div>
            </div>
            <div class="mini-controls" onclick="event.stopPropagation()">
                <button class="mini-btn" onclick="toggleKodiPlayPause()">
                    <svg id="mini-icon-pp" viewBox="0 0 24 24" width="20" height="20" fill="currentColor"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
                </button>
                <button class="mini-btn" onclick="stopKodiPlayback()" title="停止">
                    <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor"><path d="M6 6h12v12H6z"/></svg>
                </button>
                <button class="mini-btn" onclick="playNextKodiItem()" title="下一集">
                    <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor"><path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z"/></svg>
                </button>
            </div>
        </div>
    </div>

    <!-- 遥控器全屏 Modal 弹窗 -->
    <div id="remote-modal" class="remote-modal-overlay" style="display: none;" onclick="if(event.target === this) closeRemoteModal()">
        <div class="remote-header">
            <button class="remote-hdr-btn" onclick="closeRemoteModal()">
                <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
            </button>
            <div class="remote-device-info">
                <span class="remote-dev-name" id="remote-dev-name">Kodi 遥控器</span>
                <span class="remote-status-badge" id="remote-status-badge">未连接</span>
            </div>
            <div class="remote-hdr-actions">
                <button class="remote-hdr-btn" id="btn-remote-voice" onclick="openVoiceCommandModal()" title="语音控制 / 搜片" style="color: #38bdf8;">
                    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
                        <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
                        <line x1="12" y1="19" x2="12" y2="23"/>
                        <line x1="8" y1="23" x2="16" y2="23"/>
                    </svg>
                </button>
                <button class="remote-hdr-btn" onclick="openKodiPowerModal()" title="电源选项">
                    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18.36 6.64a9 9 0 1 1-12.73 0"/><line x1="12" y1="2" x2="12" y2="12"/></svg>
                </button>
            </div>
        </div>

        <!-- 播放队列卡片 (有播放时显示，默认展开) -->
        <div id="remote-playlist-card" class="remote-playlist-card" style="display: none;">
            <div class="playlist-header" onclick="togglePlaylistExpand()">
                <span>播放列表 (<span id="playlist-count">0</span>)</span>
                <svg id="playlist-arrow" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" style="transform: rotate(180deg); transition: transform 0.2s;"><path d="M6 9l6 6 6-6"/></svg>
            </div>
            <div id="playlist-list" class="playlist-list" style="display: block;"></div>
        </div>

        <!-- 中部内嵌式 Kore 3x3 遥控器 Grid 卡片 -->
        <div class="remote-dpad-container">
            <div class="dpad-kore-grid">
                <button class="dpad-corner-btn" onclick="sendKodiInput('PlayerProcessInfo')" title="播放与解码详细信息">
                    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 6h16M4 12h16M4 18h16"/></svg>
                </button>
                <button class="dpad-dir-btn" onclick="sendKodiInput('Up')" title="上">
                    <svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor"><path d="M12 8l-6 6h12z"/></svg>
                </button>
                <button class="dpad-corner-btn" onclick="sendKodiInput('ShowOSD')" title="显示播放控制条 (OSD)">
                    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="4" width="20" height="16" rx="3"/><polygon points="10 9 15 12 10 15 10 9" fill="currentColor"/><line x1="6" y1="17" x2="18" y2="17"/></svg>
                </button>

                <button class="dpad-dir-btn" onclick="sendKodiInput('Left')" title="左">
                    <svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor"><path d="M14 18l-6-6 6-6v12z"/></svg>
                </button>
                <button class="dpad-ok-btn" onclick="sendKodiInput('Select')">
                    <span>OK</span>
                </button>
                <button class="dpad-dir-btn" onclick="sendKodiInput('Right')" title="右">
                    <svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor"><path d="M10 6l6 6-6 6V6z"/></svg>
                </button>

                <button class="dpad-corner-btn" onclick="sendKodiInput('Back')" title="返回">
                    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
                </button>
                <button class="dpad-dir-btn" onclick="sendKodiInput('Down')" title="下">
                    <svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor"><path d="M12 16l6-6H6z"/></svg>
                </button>
                <button class="dpad-corner-btn" id="btn-remote-volume" onclick="openKodiVolumeModal()" title="音量调节">
                    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>
                </button>
            </div>
        </div>

        <!-- 底部单行极简视频控制组件 (Yatse 极简设计) -->
        <div id="remote-player-card" class="remote-player-card" style="display: none;">
            <div class="player-progress-area">
                <div id="seek-tooltip" class="seek-tooltip" style="display: none;">00:00</div>
                <input type="range" id="remote-seekbar" class="remote-seekbar" min="0" max="100" step="0.1" value="0" 
                       onpointerdown="handleSeekStart()"
                       ontouchstart="handleSeekStart()"
                       oninput="handleSeekInput(this.value)" 
                       onchange="seekKodiPlayer(this.value)"
                       onpointerup="seekKodiPlayer(this.value)"
                       ontouchend="seekKodiPlayer(this.value)">
            </div>

            <div class="player-single-row">
                <img id="remote-poster" class="remote-poster-sm" referrerpolicy="no-referrer" src="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg'/>" alt="poster">
                <div class="media-single-info">
                    <div id="remote-media-title" class="single-title">影片标题</div>
                    <div class="single-time-row">
                        <span id="remote-time-cur">00:00</span> / <span id="remote-time-tot">00:00</span>
                    </div>
                </div>
                <div class="player-icons-group">
                    <button class="icon-btn-mini" onclick="openAudioTrackModal()" title="音轨选择">
                        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 18v-6a9 9 0 0 1 18 0v6"/><path d="M21 19a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3zM3 19a2 2 0 0 0 2 2h1a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2H3z"/></svg>
                    </button>
                    <button class="icon-btn-mini" onclick="openSubtitleTrackModal()" title="字幕">
                        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="M6 15h4M14 15h4M6 11h12"/></svg>
                    </button>
                    <button class="icon-btn-mini" onclick="playPreviousKodiItem()" title="上一集">
                        <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M6 6h2v12H6zm3.5 6l8.5 6V6z"/></svg>
                    </button>
                    <button class="icon-btn-mini main-play-btn-mini" onclick="toggleKodiPlayPause()" title="播放/暂停">
                        <svg id="remote-play-icon" viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
                    </button>
                    <button class="icon-btn-mini" onclick="stopKodiPlayback()" title="停止">
                        <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M6 6h12v12H6z"/></svg>
                    </button>
                    <button class="icon-btn-mini" onclick="playNextKodiItem()" title="下一集">
                        <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z"/></svg>
                    </button>
                </div>
            </div>
        </div>
    </div>

    <!-- HTTP 配置引导与保存 Modal -->
    <div id="remote-config-modal" class="remote-modal-overlay sub-modal" style="display: none;" onclick="if(event.target === this) closeRemoteConfigModal()">
        <div class="config-modal-box">
            <div class="config-modal-header">
                <h3>Kodi HTTP 远程控制设置</h3>
            </div>
            <div class="config-guide">
                <p>💡 <b>开启引导说明：</b></p>
                <p>1. 请在 Kodi 中打开【设置】➔【服务设置】➔【控制】。</p>
                <p>2. 勾选<b>“允许通过 HTTP 远程控制”</b>。</p>
                <p>3. 检查端口（默认 8080）。若设置了用户名与密码，请在下方填写。</p>
            </div>
            <form onsubmit="handleKodiConfigSubmit(event)">
                <div class="input-group">
                    <label>HTTP 端口</label>
                    <input type="number" id="kodi-port-input" value="8080" placeholder="8080" required>
                </div>
                <div class="input-group">
                    <label>用户名 (选填)</label>
                    <input type="text" id="kodi-user-input" placeholder="kodi">
                </div>
                <div class="input-group">
                    <label>密码 (选填)</label>
                    <input type="password" id="kodi-pass-input" placeholder="密码">
                </div>
                <div id="kodi-config-msg" class="config-msg" style="display:none;font-size:12px;margin:8px 0;"></div>
                <div class="config-btn-row">
                    <button type="button" class="btn-cancel" onclick="closeRemoteConfigModal()">取消</button>
                    <button type="submit" id="kodi-save-btn" class="btn-save">保存并测试连接</button>
                </div>
            </form>
        </div>
    </div>

    <!-- 音轨与字幕选择 Modal -->
    <div id="remote-track-modal" class="remote-modal-overlay sub-modal" style="display: none;" onclick="if(event.target === this) closeTrackModal()">
        <div class="track-modal-box">
            <div class="config-modal-header">
                <h3 id="track-modal-title">选择音轨</h3>
            </div>
            <div id="track-modal-list" class="track-modal-list"></div>
        </div>
    </div>

    <!-- Kodi 电源与设备控制 Modal -->
    <div id="remote-power-modal" class="remote-modal-overlay sub-modal" style="display: none;" onclick="if(event.target === this) closeKodiPowerModal()">
        <div class="config-modal-box">
            <div class="config-modal-header">
                <h3>电源选项</h3>
            </div>
            <div class="power-options-grid">
                <button class="power-opt-btn danger" onclick="execKodiPowerAction('System.Shutdown')">
                    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2"><path d="M18.36 6.64a9 9 0 1 1-12.73 0"/><line x1="12" y1="2" x2="12" y2="12"/></svg>
                    <span>关机</span>
                </button>
                <button class="power-opt-btn" onclick="execKodiPowerAction('System.Reboot')">
                    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg>
                    <span>重启</span>
                </button>
                <button class="power-opt-btn" onclick="execKodiPowerAction('System.Suspend')">
                    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
                    <span>休眠</span>
                </button>
                <button class="power-opt-btn" onclick="execKodiPowerAction('Application.Quit')">
                    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
                    <span>退出 Kodi</span>
                </button>
            </div>
        </div>
    </div>

    <!-- Kodi 音量调节控制 Modal -->
    <div id="remote-volume-modal" class="remote-modal-overlay sub-modal" style="display: none;" onclick="if(event.target === this) closeKodiVolumeModal()">
        <div class="config-modal-box">
            <div class="config-modal-header">
                <h3>音量调节</h3>
                <span id="volume-val-badge" class="volume-val-badge">100%</span>
            </div>
            <div class="volume-control-box">
                <button class="vol-btn-quick" onclick="toggleKodiMuteInModal()" title="静音切换">
                    <svg id="vol-mute-icon" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><line x1="23" y1="9" x2="17" y2="15"/><line x1="17" y1="9" x2="23" y2="15"/></svg>
                </button>
                <div class="vol-slider-wrap">
                    <input type="range" id="kodi-volume-slider" class="remote-seekbar vol-seekbar" min="0" max="100" value="100" oninput="handleKodiVolumeChange(this.value)">
                </div>
                <button class="vol-btn-quick" onclick="setKodiMaxVolume()" title="最大音量">
                    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>
                </button>
            </div>
        </div>
    </div>

    <!-- 语音控制与搜片 Modal (支持原生 Web Speech API 与输入法兜底) -->
    <div id="remote-voice-modal" class="remote-modal-overlay sub-modal" style="display: none;" onclick="if(event.target === this) closeVoiceCommandModal()">
        <div class="voice-modal-box">
            <div class="voice-modal-header">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="font-size: 18px;">🎙️</span>
                    <span style="font-size: 15px; font-weight: 700; color: #fff;">语音控制 / 搜片</span>
                </div>
                <button class="modal-close" onclick="closeVoiceCommandModal()">×</button>
            </div>
            <div class="voice-modal-body">
                <div class="voice-mic-container">
                    <div id="voice-mic-pulse" class="voice-mic-btn" onclick="toggleVoiceRecording()" title="点击切换录音">
                        <svg viewBox="0 0 24 24" width="36" height="36" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
                            <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
                            <line x1="12" y1="19" x2="12" y2="23"/>
                            <line x1="8" y1="23" x2="16" y2="23"/>
                        </svg>
                    </div>
                    <div id="voice-status-tip" class="voice-status-tip">点击麦克风开始说话</div>
                </div>

                <div class="voice-input-wrapper">
                    <input type="text" id="voice-query-input" class="voice-query-input" placeholder="例如: 播放庆余年第二集、暂停、换音轨" onkeydown="if(event.key==='Enter') submitVoiceCommandFromInput()">
                    <button type="button" class="voice-send-btn" onclick="submitVoiceCommandFromInput()" title="发送指令">
                        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <line x1="22" y1="2" x2="11" y2="13"/>
                            <polygon points="22 2 15 22 11 13 2 9 22 2"/>
                        </svg>
                    </button>
                </div>

                <div id="voice-feedback-area" class="voice-feedback-area" style="display: none;"></div>

                <div class="voice-quick-tags">
                    <span class="voice-quick-tag" onclick="quickSendVoice('播放')">▶ 播放</span>
                    <span class="voice-quick-tag" onclick="quickSendVoice('暂停')">⏸ 暂停</span>
                    <span class="voice-quick-tag" onclick="quickSendVoice('播放下一集')">⏭ 下一集</span>
                    <span class="voice-quick-tag" onclick="quickSendVoice('切换音轨')">🔊 换音轨</span>
                    <span class="voice-quick-tag" onclick="quickSendVoice('切换字幕')">💬 换字幕</span>
                    <span class="voice-quick-tag" onclick="quickSendVoice('快进')">⏩ 快进</span>
                </div>
            </div>
        </div>
    </div>
    `;

    function injectRemoteDOM() {
        if (!document.getElementById('remote-modal')) {
            document.body.insertAdjacentHTML('beforeend', remoteDOMTemplate);
            bindRemoteTouchEvents();
        }
    }

    /* ==================== 遥控器与播放控制器逻辑 ==================== */
    let activePlayerId = -1;
    let kodiConnected = false;
    let remotePollTimer = null;
    let isSeekingManual = false;
    let currentTracksData = { audio: [], subtitle: [] };
    let currentTotalSeconds = 0;
    let isSyncingKodiPlayback = false;
    let seekDebounceTimer = null;
    let lastRenderedPlaylistSignature = '';
    let lastRenderedCurrentPosition = -1;
    let cachedCurrentItem = null;
    let cachedCurrentItemPosition = -1;
    let cachedPlaylistItems = null;
    let cachedPlaylistId = -1;

    async function kodiJsonRpc(method, params = {}) {
        try {
            const res = await fetch('/api/kodi/jsonrpc', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    jsonrpc: '2.0',
                    method: method,
                    params: params,
                    id: Date.now()
                })
            });
            if (!res.ok) return null;
            const data = await res.json();
            return data.result;
        } catch (err) {
            console.error('[KodiRemote] RPC Error:', method, err);
            return null;
        }
    }

    async function sendKodiInput(action) {
        if (action === 'PlayerProcessInfo' || action === 'playerprocessinfo') {
            await kodiJsonRpc('Input.ExecuteAction', { action: 'playerprocessinfo' });
        } else if (action === 'ShowOSD' || action === 'osd') {
            await kodiJsonRpc('Input.ExecuteAction', { action: 'osd' });
        } else {
            await kodiJsonRpc('Input.' + action);
        }
    }

    async function checkKodiStatusAndOpenRemote() {
        try {
            const res = await fetch('/api/kodi/status');
            if (res.ok) {
                const data = await res.json();
                kodiConnected = data.connected;
                updateRemoteStatusBadge(data.connected);
                if (!data.connected) {
                    openRemoteConfigModal('检测到 Kodi HTTP 远程控制尚未开启或无法连通，请按指引配置：');
                    return;
                }
            } else {
                openRemoteConfigModal('无法连接到 Go 守护程序，请检查服务状态。');
                return;
            }
        } catch (err) {
            openRemoteConfigModal('连接失败: ' + err.message);
            return;
        }

        openRemoteModal();
    }

    function updateRemoteStatusBadge(connected) {
        const badge = document.getElementById('remote-status-badge');
        if (badge) {
            if (connected) {
                badge.className = 'remote-status-badge connected';
                badge.textContent = '已连接';
            } else {
                badge.className = 'remote-status-badge';
                badge.textContent = '未连接';
            }
        }
    }

    function openRemoteModal() {
        const modal = document.getElementById('remote-modal');
        if (modal) {
            modal.style.display = 'flex';
            document.body.classList.add('modal-open');
            const activeName = localStorage.getItem('juku_active_device_name') || 'Kodi 遥控器';
            const devNameEl = document.getElementById('remote-dev-name');
            if (devNameEl) devNameEl.textContent = activeName;
            updateRemoteStatusBadge(true);
            syncKodiPlayback();
            startRemotePolling();
        }
    }

    function closeRemoteModal() {
        const modal = document.getElementById('remote-modal');
        if (modal) modal.style.display = 'none';
        document.body.classList.remove('modal-open');
    }

    function bindRemoteTouchEvents() {
        const remoteModal = document.getElementById('remote-modal');
        if (remoteModal) {
            remoteModal.addEventListener('touchmove', (e) => {
                const isInputNode = e.target && (e.target.tagName === 'INPUT' || e.target.type === 'range');
                const scrollable = isInputNode || e.target.closest('.playlist-list, .track-modal-list, .config-modal-box, .remote-seekbar, input[type="range"], .player-progress-area');
                if (!scrollable) {
                    e.preventDefault();
                }
            }, { passive: false });
        }

        const elSeekbar = document.getElementById('remote-seekbar');
        if (elSeekbar) {
            let isTouchDragging = false;

            const calcTouchPct = (touch) => {
                const rect = elSeekbar.getBoundingClientRect();
                if (!rect.width) return 0;
                let clientX = touch.clientX;
                let offset = clientX - rect.left;
                let pct = Math.max(0, Math.min(100, (offset / rect.width) * 100));
                return pct;
            };

            elSeekbar.addEventListener('touchstart', (e) => {
                e.stopPropagation();
                isTouchDragging = true;
                handleSeekStart();
                if (e.touches && e.touches[0]) {
                    const pct = calcTouchPct(e.touches[0]);
                    elSeekbar.value = pct;
                    handleSeekInput(pct);
                    updateSeekbarFill(elSeekbar, pct);
                }
            }, { passive: false });

            elSeekbar.addEventListener('touchmove', (e) => {
                e.stopPropagation();
                if (isTouchDragging && e.touches && e.touches[0]) {
                    const pct = calcTouchPct(e.touches[0]);
                    elSeekbar.value = pct;
                    handleSeekInput(pct);
                    updateSeekbarFill(elSeekbar, pct);
                }
            }, { passive: false });

            elSeekbar.addEventListener('touchend', (e) => {
                e.stopPropagation();
                if (isTouchDragging) {
                    isTouchDragging = false;
                    const pct = parseFloat(elSeekbar.value || 0);
                    seekKodiPlayer(pct);
                }
            }, { passive: false });
        }
    }

    function openKodiPowerModal() {
        const modal = document.getElementById('remote-power-modal');
        if (modal) modal.style.display = 'flex';
    }

    function closeKodiPowerModal() {
        const modal = document.getElementById('remote-power-modal');
        if (modal) modal.style.display = 'none';
    }

    async function openKodiVolumeModal() {
        const modal = document.getElementById('remote-volume-modal');
        if (!modal) return;
        modal.style.display = 'flex';

        const slider = document.getElementById('kodi-volume-slider');
        if (slider) {
            updateSeekbarFill(slider, slider.value || 100);
        }

        const res = await kodiJsonRpc('Application.GetProperties', { properties: ['volume', 'muted'] });
        if (res) {
            const vol = typeof res.volume === 'number' ? res.volume : 100;
            const muted = !!res.muted;
            updateVolumeUI(vol, muted);
        }
    }

    function closeKodiVolumeModal() {
        const modal = document.getElementById('remote-volume-modal');
        if (modal) modal.style.display = 'none';
    }

    function updateVolumeUI(vol, muted) {
        const slider = document.getElementById('kodi-volume-slider');
        const badge = document.getElementById('volume-val-badge');
        if (slider) {
            slider.value = vol;
            const color = muted ? '#64748B' : '#6366F1';
            updateSeekbarFill(slider, vol, color);
        }
        if (badge) {
            if (muted) {
                badge.textContent = '🔇 已静音';
                badge.style.color = '#F87171';
            } else {
                badge.textContent = '🔊 ' + vol + '%';
                badge.style.color = '#818CF8';
            }
        }
    }

    async function handleKodiVolumeChange(val) {
        const vol = parseInt(val, 10);
        updateVolumeUI(vol, false);
        await kodiJsonRpc('Application.SetMute', { mute: false });
        await kodiJsonRpc('Application.SetVolume', { volume: vol });
    }

    async function toggleKodiMuteInModal() {
        await kodiJsonRpc('Application.SetMute', { mute: 'toggle' });
        const props = await kodiJsonRpc('Application.GetProperties', { properties: ['volume', 'muted'] });
        if (props) {
            updateVolumeUI(props.volume !== undefined ? props.volume : 100, !!props.muted);
        }
    }

    async function setKodiMaxVolume() {
        updateVolumeUI(100, false);
        await kodiJsonRpc('Application.SetMute', { mute: false });
        await kodiJsonRpc('Application.SetVolume', { volume: 100 });
    }

    async function playPreviousKodiItem() {
        if (activePlayerId < 0) return;
        try {
            const props = await kodiJsonRpc('Player.GetProperties', { playerid: activePlayerId, properties: ['playlistid', 'position'] });
            if (props && typeof props.position === 'number') {
                const plId = props.playlistid !== undefined ? props.playlistid : 1;
                if (props.position > 0) {
                    await kodiJsonRpc('Player.Open', { item: { playlistid: plId, position: props.position - 1 } });
                    setTimeout(syncKodiPlayback, 300);
                    return;
                }
            }
        } catch (e) {
            console.error('[KodiRemote] playPreviousKodiItem error:', e);
        }
        await kodiJsonRpc('Player.GoTo', { playerid: activePlayerId, to: 'previous' });
        setTimeout(syncKodiPlayback, 300);
    }

    async function playNextKodiItem() {
        if (activePlayerId < 0) return;
        try {
            const props = await kodiJsonRpc('Player.GetProperties', { playerid: activePlayerId, properties: ['playlistid', 'position'] });
            if (props && typeof props.position === 'number') {
                const plId = props.playlistid !== undefined ? props.playlistid : 1;
                await kodiJsonRpc('Player.Open', { item: { playlistid: plId, position: props.position + 1 } });
                setTimeout(syncKodiPlayback, 300);
                return;
            }
        } catch (e) {
            console.error('[KodiRemote] playNextKodiItem error:', e);
        }
        await kodiJsonRpc('Player.GoTo', { playerid: activePlayerId, to: 'next' });
        setTimeout(syncKodiPlayback, 300);
    }

    async function execKodiPowerAction(method) {
        closeKodiPowerModal();
        await kodiJsonRpc(method);
    }

    async function openRemoteConfigModal(msgText = '') {
        const modal = document.getElementById('remote-config-modal');
        const msgBox = document.getElementById('kodi-config-msg');
        if (msgText && msgBox) {
            msgBox.style.display = 'block';
            msgBox.style.color = '#F87171';
            msgBox.textContent = msgText;
        } else if (msgBox) {
            msgBox.style.display = 'none';
        }

        try {
            const res = await fetch('/api/kodi/config');
            if (res.ok) {
                const data = await res.json();
                if (data.config) {
                    const pInp = document.getElementById('kodi-port-input');
                    if (pInp) pInp.value = data.config.port || 8080;
                    const uInp = document.getElementById('kodi-user-input');
                    if (uInp) uInp.value = data.config.username || '';
                    const pwInp = document.getElementById('kodi-pass-input');
                    if (pwInp) pwInp.value = data.config.password || '';
                }
            }
        } catch (e) {}

        if (modal) modal.style.display = 'flex';
    }

    function closeRemoteConfigModal() {
        const modal = document.getElementById('remote-config-modal');
        if (modal) modal.style.display = 'none';
    }

    async function handleKodiConfigSubmit(e) {
        e.preventDefault();
        const btn = document.getElementById('kodi-save-btn');
        const msgBox = document.getElementById('kodi-config-msg');
        btn.disabled = true;
        btn.textContent = '正在测试连接...';
        msgBox.style.display = 'none';

        const payload = {
            port: parseInt(document.getElementById('kodi-port-input').value) || 8080,
            username: document.getElementById('kodi-user-input').value.trim(),
            password: document.getElementById('kodi-pass-input').value.trim()
        };

        try {
            const res = await fetch('/api/kodi/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (res.ok && data.connected) {
                kodiConnected = true;
                updateRemoteStatusBadge(true);
                msgBox.style.display = 'block';
                msgBox.style.color = '#34D399';
                msgBox.textContent = '✓ 连接成功！已保存配置。';
                setTimeout(() => {
                    btn.disabled = false;
                    btn.textContent = '保存并测试连接';
                    closeRemoteConfigModal();
                    openRemoteModal();
                }, 800);
            } else {
                msgBox.style.display = 'block';
                msgBox.style.color = '#F87171';
                msgBox.textContent = '✗ 尝试连接 Kodi 失败。请检查 Kodi 端口及“允许 HTTP 远程控制”选项是否开启。';
                btn.disabled = false;
                btn.textContent = '保存并测试连接';
            }
        } catch (err) {
            msgBox.style.display = 'block';
            msgBox.style.color = '#F87171';
            msgBox.textContent = '错误: ' + err.message;
            btn.disabled = false;
            btn.textContent = '保存并测试连接';
        }
    }

    function formatKodiTime(t) {
        if (!t) return '00:00';
        const hh = String(t.hours || 0).padStart(2, '0');
        const mm = String(t.minutes || 0).padStart(2, '0');
        const ss = String(t.seconds || 0).padStart(2, '0');
        if (t.hours > 0) return hh + ':' + mm + ':' + ss;
        return mm + ':' + ss;
    }

    async function syncKodiPlayback() {
        if (isSyncingKodiPlayback) return;
        isSyncingKodiPlayback = true;
        try {
            const activePlayers = await kodiJsonRpc('Player.GetActivePlayers');
            const miniBar = document.getElementById('mini-player-bar');
            const remotePlayerCard = document.getElementById('remote-player-card');
            const fabDot = document.getElementById('fab-playing-dot');

            if (!activePlayers || activePlayers.length === 0) {
                activePlayerId = -1;
                cachedCurrentItem = null;
                cachedCurrentItemPosition = -1;
                cachedPlaylistItems = null;
                cachedPlaylistId = -1;
                lastRenderedPlaylistSignature = '';
                lastRenderedCurrentPosition = -1;

                document.body.classList.remove('has-mini-player');
                if (miniBar) miniBar.style.display = 'none';
                if (remotePlayerCard) remotePlayerCard.style.display = 'none';
                if (fabDot) fabDot.style.display = 'none';
                const playlistCard = document.getElementById('remote-playlist-card');
                if (playlistCard) playlistCard.style.display = 'none';
                return;
            }

            document.body.classList.add('has-mini-player');
            updateRemoteStatusBadge(true);

            const videoPlayer = activePlayers.find(p => p.type === 'video') || activePlayers[0];
            const newPlayerId = videoPlayer.playerid;
            const playerChanged = (activePlayerId !== newPlayerId);
            activePlayerId = newPlayerId;

            if (fabDot) fabDot.style.display = 'block';

            // 1. 轻量拉取动态播放属性 (每秒只请求时间/进度/速度/位置，避免传输音轨字幕等臃肿大对象)
            const propsRes = await kodiJsonRpc('Player.GetProperties', {
                playerid: activePlayerId,
                properties: ['time', 'totaltime', 'percentage', 'speed', 'position', 'playlistid']
            }) || {};

            const curPos = (typeof propsRes.position === 'number' && propsRes.position >= 0) ? propsRes.position : -1;
            const targetPlaylistId = (typeof propsRes.playlistid === 'number' && propsRes.playlistid >= 0) ? propsRes.playlistid : 1;

            // 2. 动静分离：仅在起播、切集或播放器切换时按需拉取当前视频元数据 (Player.GetItem)
            const itemNeedsFetch = (!cachedCurrentItem || playerChanged || curPos !== cachedCurrentItemPosition);
            if (itemNeedsFetch) {
                const itemRes = await kodiJsonRpc('Player.GetItem', {
                    playerid: activePlayerId,
                    properties: ['title', 'showtitle', 'season', 'episode', 'thumbnail', 'file']
                }) || {};
                cachedCurrentItem = itemRes.item || {};
                cachedCurrentItemPosition = curPos;
            }

            const item = cachedCurrentItem || {};
            const title = item.title || item.label || '正在播放';

            let posterUrl = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="52" height="52" fill="%23334155"><rect width="52" height="52"/><text x="50%" y="55%" dominant-baseline="middle" text-anchor="middle" fill="%2394A3B8" font-size="20">🎬</text></svg>';
            if (item.thumbnail) {
                let cleanThumb = decodeURIComponent(item.thumbnail).replace('image://', '');
                if (cleanThumb.endsWith('/')) cleanThumb = cleanThumb.slice(0, -1);
                posterUrl = cleanThumb;
            }

            const curTimeStr = formatKodiTime(propsRes.time);
            const totTimeStr = formatKodiTime(propsRes.totaltime);
            currentTotalSeconds = parseKodiTotalSeconds(propsRes.totaltime);
            const timeRangeStr = curTimeStr + ' / ' + totTimeStr;
            const pct = typeof propsRes.percentage === 'number' ? propsRes.percentage : 0;
            const isPlaying = propsRes.speed !== undefined && propsRes.speed !== 0;

            // 1. 更新 Mini 播放条
            if (miniBar) {
                miniBar.style.display = 'flex';
                const elPoster = document.getElementById('mini-poster');
                if (elPoster) elPoster.src = posterUrl;
                const elTitle = document.getElementById('mini-title');
                if (elTitle) elTitle.textContent = title;
                const elTime = document.getElementById('mini-time-str');
                if (elTime) elTime.textContent = timeRangeStr;
                const elFill = document.getElementById('mini-progress-fill');
                if (elFill) elFill.style.width = pct + '%';

                const ppIcon = document.getElementById('mini-icon-pp');
                if (ppIcon) {
                    if (isPlaying) {
                        ppIcon.innerHTML = '<path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/>';
                    } else {
                        ppIcon.innerHTML = '<path d="M8 5v14l11-7z"/>';
                    }
                }
            }

            // 2. 更新全屏遥控器底栏
            if (remotePlayerCard) {
                remotePlayerCard.style.display = 'block';
                const elRPoster = document.getElementById('remote-poster');
                if (elRPoster) elRPoster.src = posterUrl;
                const elRTitle = document.getElementById('remote-media-title');
                if (elRTitle) elRTitle.textContent = title;

                const elCur = document.getElementById('remote-time-cur');
                if (elCur) elCur.textContent = curTimeStr;
                const elTot = document.getElementById('remote-time-tot');
                if (elTot) elTot.textContent = totTimeStr;

                if (!isSeekingManual) {
                    const elSeekbar = document.getElementById('remote-seekbar');
                    if (elSeekbar) {
                        const valPct = Math.round(pct);
                        elSeekbar.value = valPct;
                        updateSeekbarFill(elSeekbar, valPct);
                    }
                }

                const playIcon = document.getElementById('remote-play-icon');
                if (playIcon) {
                    if (isPlaying) {
                        playIcon.innerHTML = '<path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/>';
                    } else {
                        playIcon.innerHTML = '<path d="M8 5v14l11-7z"/>';
                    }
                }
            }

            // 3. 动静分离：仅在无缓存、playlistid改变或条目不匹配时才拉取播放列表 (Playlist.GetItems)
            let playlistNeedsFetch = false;
            if (!cachedPlaylistItems || !cachedPlaylistItems.items || cachedPlaylistId !== targetPlaylistId) {
                playlistNeedsFetch = true;
            } else if (item && item.file && curPos >= 0 && curPos < cachedPlaylistItems.items.length) {
                const curPlaylistItem = cachedPlaylistItems.items[curPos];
                if (curPlaylistItem && curPlaylistItem.file && curPlaylistItem.file !== item.file) {
                    playlistNeedsFetch = true;
                }
            } else if (item && item.file && curPos >= cachedPlaylistItems.items.length) {
                playlistNeedsFetch = true;
            }

            if (playlistNeedsFetch) {
                const plRes = await kodiJsonRpc('Playlist.GetItems', {
                    playlistid: targetPlaylistId,
                    properties: ['title', 'file']
                });
                if (plRes && plRes.items) {
                    cachedPlaylistItems = plRes;
                    cachedPlaylistId = targetPlaylistId;
                }
            }
            const playlistRes = cachedPlaylistItems;
            const playlistCard = document.getElementById('remote-playlist-card');
            if (playlistCard) {
                if (playlistRes && playlistRes.items && playlistRes.items.length > 0) {
                    playlistCard.style.display = 'block';
                    const elCount = document.getElementById('playlist-count');
                    if (elCount) elCount.textContent = playlistRes.items.length;
                    const listEl = document.getElementById('playlist-list');
                    if (listEl) {
                        const curPos = (typeof propsRes.position === 'number' && propsRes.position >= 0) ? propsRes.position : -1;
                        const firstFile = (playlistRes.items[0] && playlistRes.items[0].file) ? playlistRes.items[0].file : '';
                        const lastFile = (playlistRes.items[playlistRes.items.length - 1] && playlistRes.items[playlistRes.items.length - 1].file) ? playlistRes.items[playlistRes.items.length - 1].file : '';
                        const currentSignature = playlistRes.items.length + '_' + firstFile + '_' + lastFile;

                        if (currentSignature === lastRenderedPlaylistSignature && curPos === lastRenderedCurrentPosition) {
                            // 列表结构与当前播放项均未改变：严禁重建 DOM 或自动滚动，完整保留用户手动滚动位置
                        } else if (currentSignature === lastRenderedPlaylistSignature && listEl.children.length === playlistRes.items.length) {
                            // 仅换集（如自然连播下一集）：仅轻量切换 active 类与正在播放标签，仅平滑滚动定位一次新集
                            const items = listEl.querySelectorAll('.playlist-item');
                            let targetActiveDiv = null;
                            items.forEach((itemDiv, idx) => {
                                const isCur = (curPos === idx);
                                if (isCur) {
                                    itemDiv.classList.add('active');
                                    let indicator = itemDiv.querySelector('.playing-indicator');
                                    if (!indicator) {
                                        indicator = document.createElement('span');
                                        indicator.className = 'playing-indicator';
                                        indicator.style.cssText = 'display:inline-flex;align-items:center;color:#818CF8;margin-right:2px;';
                                        indicator.innerHTML = '<svg viewBox="0 0 24 24" width="13" height="13" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>';
                                        itemDiv.insertBefore(indicator, itemDiv.firstChild);
                                    }
                                    let badge = itemDiv.querySelector('.playing-badge');
                                    if (!badge) {
                                        badge = document.createElement('span');
                                        badge.className = 'playing-badge';
                                        badge.textContent = '正在播放';
                                        itemDiv.appendChild(badge);
                                    }
                                    targetActiveDiv = itemDiv;
                                } else {
                                    itemDiv.classList.remove('active');
                                    const indicator = itemDiv.querySelector('.playing-indicator');
                                    if (indicator) indicator.remove();
                                    const badge = itemDiv.querySelector('.playing-badge');
                                    if (badge) badge.remove();
                                }
                            });
                            lastRenderedCurrentPosition = curPos;
                            if (targetActiveDiv && listEl.style.display !== 'none') {
                                targetActiveDiv.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
                            }
                        } else {
                            // 首次打开或换剧：全量构建列表并平滑定位一次
                            listEl.innerHTML = '';
                            let activeItemDiv = null;

                            playlistRes.items.forEach((plItem, idx) => {
                                const itemDiv = document.createElement('div');
                                let isCur = false;
                                if (curPos >= 0) {
                                    isCur = (curPos === idx);
                                } else {
                                    const itemFile = item.file || '';
                                    const plFile = plItem.file || '';
                                    isCur = (itemFile && plFile && itemFile === plFile) ||
                                            (plItem.title === title || plItem.label === title) ||
                                            (title && plItem.label && (plItem.label.includes(title) || title.includes(plItem.label)));
                                }

                                itemDiv.className = 'playlist-item' + (isCur ? ' active' : '');
                                const epName = plItem.title || plItem.label || plItem.file || ('第 ' + (idx + 1) + ' 集');
                                const indicatorHtml = isCur 
                                    ? '<span class="playing-indicator" style="display:inline-flex;align-items:center;color:#818CF8;margin-right:2px;"><svg viewBox="0 0 24 24" width="13" height="13" fill="currentColor"><path d="M8 5v14l11-7z"/></svg></span>' 
                                    : '';
                                const badgeHtml = isCur 
                                    ? '<span class="playing-badge">正在播放</span>' 
                                    : '';

                                itemDiv.innerHTML = indicatorHtml + '<span>' + (idx + 1) + '.</span> <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + epName + '</span>' + badgeHtml;
                                itemDiv.onclick = async () => {
                                    await kodiJsonRpc('Player.Open', { item: { playlistid: targetPlaylistId, position: idx } });
                                    setTimeout(syncKodiPlayback, 300);
                                };
                                listEl.appendChild(itemDiv);
                                if (isCur) {
                                    activeItemDiv = itemDiv;
                                }
                            });

                            lastRenderedPlaylistSignature = currentSignature;
                            lastRenderedCurrentPosition = curPos;

                            if (activeItemDiv && listEl.style.display !== 'none') {
                                activeItemDiv.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
                            }
                        }
                    }
                } else {
                    playlistCard.style.display = 'none';
                    lastRenderedPlaylistSignature = '';
                    lastRenderedCurrentPosition = -1;
                }
            }
        } catch (err) {
            console.error('[KodiRemote] syncKodiPlayback error:', err);
        } finally {
            isSyncingKodiPlayback = false;
        }
    }

    async function toggleKodiPlayPause() {
        if (activePlayerId >= 0) {
            await kodiJsonRpc('Player.PlayPause', { playerid: activePlayerId });
            await syncKodiPlayback();
        }
    }

    async function stopKodiPlayback() {
        let pid = activePlayerId;
        if (pid < 0) {
            const activePlayers = await kodiJsonRpc('Player.GetActivePlayers');
            if (activePlayers && activePlayers.length > 0) {
                const videoPlayer = activePlayers.find(p => p.type === 'video') || activePlayers[0];
                pid = videoPlayer.playerid;
            }
        }
        if (pid >= 0) {
            await kodiJsonRpc('Player.Stop', { playerid: pid });
        } else {
            await kodiJsonRpc('Input.ExecuteAction', { action: 'stop' });
        }

        activePlayerId = -1;
        window.activePlayerId = -1;
        cachedCurrentItem = null;
        cachedCurrentItemPosition = -1;
        cachedPlaylistItems = null;
        cachedPlaylistId = -1;
        lastRenderedPlaylistSignature = '';
        lastRenderedCurrentPosition = -1;

        const miniBar = document.getElementById('mini-player-bar');
        if (miniBar) miniBar.style.display = 'none';
        const remotePlayerCard = document.getElementById('remote-player-card');
        if (remotePlayerCard) remotePlayerCard.style.display = 'none';
        const fabDot = document.getElementById('fab-playing-dot');
        if (fabDot) fabDot.style.display = 'none';
        const playlistCard = document.getElementById('remote-playlist-card');
        if (playlistCard) playlistCard.style.display = 'none';
        document.body.classList.remove('has-mini-player');

        setTimeout(syncKodiPlayback, 300);
    }

    function parseKodiTotalSeconds(t) {
        if (!t) return 0;
        return (t.hours || 0) * 3600 + (t.minutes || 0) * 60 + (t.seconds || 0);
    }

    function updateSeekbarFill(el, pct, fillColor = '#6366F1') {
        if (!el) return;
        const p = Math.max(0, Math.min(100, parseFloat(pct) || 0));
        el.style.background = 'linear-gradient(to right, ' + fillColor + ' 0%, ' + fillColor + ' ' + p + '%, rgba(255, 255, 255, 0.15) ' + p + '%, rgba(255, 255, 255, 0.15) 100%)';
    }

    function handleSeekStart() {
        isSeekingManual = true;
    }

    function handleSeekInput(val) {
        isSeekingManual = true;
        const tooltip = document.getElementById('seek-tooltip');
        const seekbar = document.getElementById('remote-seekbar');
        if (!tooltip || !seekbar) return;

        const targetSec = Math.round((parseFloat(val) / 100) * (currentTotalSeconds || 0));
        const hh = String(Math.floor(targetSec / 3600)).padStart(2, '0');
        const mm = String(Math.floor((targetSec % 3600) / 60)).padStart(2, '0');
        const ss = String(targetSec % 60).padStart(2, '0');
        const timeStr = currentTotalSeconds >= 3600 ? hh + ':' + mm + ':' + ss : mm + ':' + ss;

        tooltip.textContent = timeStr;
        tooltip.style.display = 'block';

        const pct = parseFloat(val);
        tooltip.style.left = 'calc(' + pct + '% + ' + (8 - pct * 0.16) + 'px)';
        updateSeekbarFill(seekbar, pct);
    }

    async function seekKodiPlayer(val) {
        if (seekDebounceTimer) clearTimeout(seekDebounceTimer);
        seekDebounceTimer = setTimeout(async () => {
            const tooltip = document.getElementById('seek-tooltip');
            if (tooltip) tooltip.style.display = 'none';

            if (activePlayerId >= 0) {
                const elSeekbar = document.getElementById('remote-seekbar');
                const targetVal = val !== undefined && val !== null ? val : (elSeekbar ? elSeekbar.value : 0);
                const pct = parseFloat(targetVal);
                await kodiJsonRpc('Player.Seek', {
                    playerid: activePlayerId,
                    value: { percentage: pct }
                });

                setTimeout(async () => {
                    await syncKodiPlayback();
                    isSeekingManual = false;
                }, 800);
            } else {
                isSeekingManual = false;
            }
        }, 60);
    }

    function togglePlaylistExpand() {
        const list = document.getElementById('playlist-list');
        const arrow = document.getElementById('playlist-arrow');
        if (list.style.display === 'none') {
            list.style.display = 'block';
            arrow.style.transform = 'rotate(180deg)';
            const activeItem = list.querySelector('.playlist-item.active');
            if (activeItem) {
                setTimeout(() => activeItem.scrollIntoView({ block: 'nearest', behavior: 'smooth' }), 50);
            }
        } else {
            list.style.display = 'none';
            arrow.style.transform = 'rotate(0deg)';
        }
    }

    async function openAudioTrackModal() {
        const modal = document.getElementById('remote-track-modal');
        document.getElementById('track-modal-title').textContent = '选择音轨';
        const listEl = document.getElementById('track-modal-list');
        listEl.innerHTML = '<div style="padding:16px;text-align:center;color:#94A3B8;">正在获取音轨...</div>';
        modal.style.display = 'flex';

        if (activePlayerId >= 0) {
            try {
                const p = await kodiJsonRpc('Player.GetProperties', {
                    playerid: activePlayerId,
                    properties: ['audiostreams', 'currentaudiostream']
                });
                if (p) {
                    currentTracksData.audio = p.audiostreams || [];
                    currentTracksData.currentAudio = p.currentaudiostream || {};
                }
            } catch (e) {
                console.error('[KodiRemote] load audio tracks error:', e);
            }
        }

        listEl.innerHTML = '';
        const streams = currentTracksData.audio;
        if (!streams || streams.length === 0) {
            listEl.innerHTML = '<div style="padding:16px;text-align:center;color:#94A3B8;">未探测到多音轨数据</div>';
        } else {
            streams.forEach((stream, idx) => {
                const isCur = currentTracksData.currentAudio && stream.index === currentTracksData.currentAudio.index;
                const item = document.createElement('div');
                item.className = 'track-item' + (isCur ? ' active' : '');
                const name = stream.name || stream.language || ('音轨 ' + (idx + 1));
                const details = (stream.codec || '') + ' ' + (stream.channels ? stream.channels + 'ch' : '');
                item.innerHTML = '<span>' + name + '</span> <span style="font-size:11px;opacity:0.7;">' + details + '</span>';
                item.onclick = async () => {
                    await kodiJsonRpc('Player.SetAudioStream', { playerid: activePlayerId, stream: stream.index });
                    closeTrackModal();
                    setTimeout(syncKodiPlayback, 300);
                };
                listEl.appendChild(item);
            });
        }
    }

    async function openSubtitleTrackModal() {
        const modal = document.getElementById('remote-track-modal');
        document.getElementById('track-modal-title').textContent = '字幕设置';
        const listEl = document.getElementById('track-modal-list');
        listEl.innerHTML = '<div style="padding:16px;text-align:center;color:#94A3B8;">正在获取字幕...</div>';
        modal.style.display = 'flex';

        if (activePlayerId >= 0) {
            try {
                const p = await kodiJsonRpc('Player.GetProperties', {
                    playerid: activePlayerId,
                    properties: ['subtitles', 'currentsubtitle']
                });
                if (p) {
                    currentTracksData.subtitle = p.subtitles || [];
                    currentTracksData.currentSubtitle = p.currentsubtitle || {};
                }
            } catch (e) {
                console.error('[KodiRemote] load subtitles error:', e);
            }
        }

        listEl.innerHTML = '';
        const subs = currentTracksData.subtitle;

        // 禁用/关闭字幕选项
        const offItem = document.createElement('div');
        const isOff = !currentTracksData.currentSubtitle || currentTracksData.currentSubtitle.index === undefined;
        offItem.className = 'track-item' + (isOff ? ' active' : '');
        offItem.innerHTML = '<span>🚫 关闭字幕</span>';
        offItem.onclick = async () => {
            await kodiJsonRpc('Player.SetSubtitle', { playerid: activePlayerId, subtitle: 'off' });
            closeTrackModal();
            setTimeout(syncKodiPlayback, 300);
        };
        listEl.appendChild(offItem);

        if (subs && subs.length > 0) {
            subs.forEach((sub, idx) => {
                const isCur = currentTracksData.currentSubtitle && sub.index === currentTracksData.currentSubtitle.index;
                const item = document.createElement('div');
                item.className = 'track-item' + (isCur ? ' active' : '');
                const name = sub.name || sub.language || ('字幕 ' + (idx + 1));
                item.innerHTML = '<span>💬 ' + name + '</span>';
                item.onclick = async () => {
                    await kodiJsonRpc('Player.SetSubtitle', { playerid: activePlayerId, subtitle: sub.index, enable: true });
                    closeTrackModal();
                    setTimeout(syncKodiPlayback, 300);
                };
                listEl.appendChild(item);
            });
        }
    }

    function closeTrackModal() {
        const modal = document.getElementById('remote-track-modal');
        if (modal) modal.style.display = 'none';
    }

    function startRemotePolling() {
        if (remotePollTimer) clearInterval(remotePollTimer);
        remotePollTimer = setInterval(() => {
            syncKodiPlayback();
        }, 1000);
    }

    // 暴露在 window 供页面各处和内联 onclick 调用
    window.kodiJsonRpc = kodiJsonRpc;
    window.sendKodiInput = sendKodiInput;
    window.checkKodiStatusAndOpenRemote = checkKodiStatusAndOpenRemote;
    window.openRemoteModal = openRemoteModal;
    window.closeRemoteModal = closeRemoteModal;
    window.openKodiPowerModal = openKodiPowerModal;
    window.closeKodiPowerModal = closeKodiPowerModal;
    window.openKodiVolumeModal = openKodiVolumeModal;
    window.closeKodiVolumeModal = closeKodiVolumeModal;
    window.handleKodiVolumeChange = handleKodiVolumeChange;
    window.toggleKodiMuteInModal = toggleKodiMuteInModal;
    window.setKodiMaxVolume = setKodiMaxVolume;
    window.playPreviousKodiItem = playPreviousKodiItem;
    window.playNextKodiItem = playNextKodiItem;
    window.execKodiPowerAction = execKodiPowerAction;
    window.openRemoteConfigModal = openRemoteConfigModal;
    window.closeRemoteConfigModal = closeRemoteConfigModal;
    window.handleKodiConfigSubmit = handleKodiConfigSubmit;
    window.toggleKodiPlayPause = toggleKodiPlayPause;
    window.stopKodiPlayback = stopKodiPlayback;
    window.handleSeekStart = handleSeekStart;
    window.handleSeekInput = handleSeekInput;
    window.seekKodiPlayer = seekKodiPlayer;
    window.togglePlaylistExpand = togglePlaylistExpand;
    window.openAudioTrackModal = openAudioTrackModal;
    window.openSubtitleTrackModal = openSubtitleTrackModal;
    window.closeTrackModal = closeTrackModal;
    window.syncKodiPlayback = syncKodiPlayback;

    /* ==================== 全局后台异步任务常驻状态管理器 ==================== */
    const JUKU_ACTIVE_TASK_KEY = 'juku_active_import_task';
    let globalImportTaskTimer = null;
    let globalTaskState = {
        taskId: null,
        title: '',
        collapsed: false,
        percent: 0,
        stage: ''
    };

    function getSavedActiveImportTask() {
        try {
            const raw = localStorage.getItem(JUKU_ACTIVE_TASK_KEY);
            if (!raw) return null;
            const data = JSON.parse(raw);
            if (data.timestamp && (Date.now() - data.timestamp > 3 * 3600 * 1000)) {
                localStorage.removeItem(JUKU_ACTIVE_TASK_KEY);
                return null;
            }
            return data;
        } catch (e) {
            return null;
        }
    }

    function saveActiveImportTask(data) {
        try {
            localStorage.setItem(JUKU_ACTIVE_TASK_KEY, JSON.stringify(data));
        } catch (e) {}
    }

    function clearSavedActiveImportTask() {
        try {
            localStorage.removeItem(JUKU_ACTIVE_TASK_KEY);
        } catch (e) {}
    }

    function collapseGlobalAsyncTaskBar() {
        globalTaskState.collapsed = true;
        const saved = getSavedActiveImportTask();
        if (saved) {
            saved.collapsed = true;
            saveActiveImportTask(saved);
        }
        const bar = document.getElementById('globalAsyncTaskBar');
        const badge = document.getElementById('globalAsyncTaskBadge');
        if (bar) bar.style.display = 'none';
        if (badge) {
            badge.style.display = 'inline-flex';
            const badgeText = document.getElementById('globalAsyncBadgeText');
            if (badgeText) {
                const pct = globalTaskState.percent !== undefined ? globalTaskState.percent : (saved && saved.percent ? saved.percent : 10);
                badgeText.innerText = '⚡ 导入中 ' + pct + '%';
            }
        }
    }

    function expandGlobalAsyncTaskBar() {
        globalTaskState.collapsed = false;
        const saved = getSavedActiveImportTask();
        if (saved) {
            saved.collapsed = false;
            saveActiveImportTask(saved);
        }
        const bar = document.getElementById('globalAsyncTaskBar');
        const badge = document.getElementById('globalAsyncTaskBadge');
        if (badge) badge.style.display = 'none';
        if (bar) bar.style.display = 'block';
    }

    function showGlobalAsyncTaskBar(taskId, title) {
        globalTaskState.taskId = taskId;
        globalTaskState.title = title || '网盘大包后台导入';

        // 确保写入 localStorage 以便跨页面保持
        let saved = getSavedActiveImportTask();
        if (!saved || saved.taskId !== taskId) {
            saved = {
                taskId: taskId,
                title: globalTaskState.title,
                collapsed: !!globalTaskState.collapsed,
                timestamp: Date.now()
            };
            saveActiveImportTask(saved);
        } else if (saved.collapsed !== undefined) {
            globalTaskState.collapsed = !!saved.collapsed;
        }

        const bar = document.getElementById('globalAsyncTaskBar');
        const badge = document.getElementById('globalAsyncTaskBadge');
        if (!bar) return;

        const titleEl = document.getElementById('globalAsyncTitle');
        if (titleEl) {
            titleEl.innerHTML = '<span class="async-task-spinner"></span><span>⚡ ' + (title || '后台任务执行中') + '</span>';
        }
        const btnCancel = document.getElementById('btnCancelGlobalAsyncTask');
        if (btnCancel) btnCancel.style.display = 'inline-block';

        if (globalTaskState.collapsed) {
            if (bar) bar.style.display = 'none';
            if (badge) {
                badge.style.display = 'inline-flex';
                const badgeText = document.getElementById('globalAsyncBadgeText');
                if (badgeText) {
                    const pct = globalTaskState.percent !== undefined ? globalTaskState.percent : (saved && saved.percent ? saved.percent : 10);
                    badgeText.innerText = '⚡ 导入中 ' + pct + '%';
                }
            }
        } else {
            if (badge) badge.style.display = 'none';
            if (bar) bar.style.display = 'block';
        }

        // 若未开启轮询，自动启动轮询保活
        if (taskId && !globalImportTaskTimer) {
            pollGlobalImportTask(taskId);
        }
    }

    function updateGlobalAsyncTaskBar(percent, stage) {
        globalTaskState.percent = percent;
        globalTaskState.stage = stage;
        const saved = getSavedActiveImportTask();
        if (saved) {
            saved.percent = percent;
            saved.stage = stage;
            saveActiveImportTask(saved);
        }

        const barFill = document.getElementById('globalAsyncBar');
        const pctEl = document.getElementById('globalAsyncPercent');
        const stgEl = document.getElementById('globalAsyncStage');
        if (barFill) barFill.style.width = percent + '%';
        if (pctEl) pctEl.innerText = percent + '%';
        if (stgEl) stgEl.innerText = stage || '正在处理中...';

        const badgeText = document.getElementById('globalAsyncBadgeText');
        if (badgeText) {
            badgeText.innerText = '⚡ 导入中 ' + percent + '%';
        }

        const bar = document.getElementById('globalAsyncTaskBar');
        const badge = document.getElementById('globalAsyncTaskBadge');
        if (globalTaskState.collapsed) {
            if (bar) bar.style.display = 'none';
            if (badge) badge.style.display = 'inline-flex';
        } else {
            if (badge) badge.style.display = 'none';
            if (bar) bar.style.display = 'block';
        }
    }

    function completeGlobalAsyncTaskBar(msg) {
        clearSavedActiveImportTask();
        globalTaskState.taskId = null;

        const barFill = document.getElementById('globalAsyncBar');
        const pctEl = document.getElementById('globalAsyncPercent');
        const stgEl = document.getElementById('globalAsyncStage');
        const titleEl = document.getElementById('globalAsyncTitle');
        const btnCancel = document.getElementById('btnCancelGlobalAsyncTask');
        if (titleEl) titleEl.innerHTML = '<span>🎉 导入任务已完成</span>';
        if (barFill) barFill.style.width = '100%';
        if (pctEl) pctEl.innerText = '100%';
        if (stgEl) stgEl.innerText = msg || '任务已完成';
        if (btnCancel) btnCancel.style.display = 'none';

        const badgeText = document.getElementById('globalAsyncBadgeText');
        const badgeSpinner = document.getElementById('globalAsyncBadgeSpinner');
        if (badgeSpinner) badgeSpinner.style.display = 'none';
        if (badgeText) {
            badgeText.innerText = '🎉 导入已完成';
            badgeText.style.color = '#34d399';
        }

        setTimeout(() => {
            const bar = document.getElementById('globalAsyncTaskBar');
            const badge = document.getElementById('globalAsyncTaskBadge');
            if (bar) bar.style.display = 'none';
            if (badge) badge.style.display = 'none';
            globalTaskState.collapsed = false;
            if (badgeSpinner) badgeSpinner.style.display = '';
            if (badgeText) badgeText.style.color = '#a5b4fc';
        }, 6000);
    }

    function failGlobalAsyncTaskBar(errMsg) {
        clearSavedActiveImportTask();
        globalTaskState.taskId = null;

        const stgEl = document.getElementById('globalAsyncStage');
        const titleEl = document.getElementById('globalAsyncTitle');
        const btnCancel = document.getElementById('btnCancelGlobalAsyncTask');
        if (titleEl) titleEl.innerHTML = '<span style="color: #ef4444;">❌ 导入失败</span>';
        if (stgEl) stgEl.innerText = errMsg || '任务失败';
        if (btnCancel) btnCancel.style.display = 'none';

        const badgeText = document.getElementById('globalAsyncBadgeText');
        const badgeSpinner = document.getElementById('globalAsyncBadgeSpinner');
        if (badgeSpinner) badgeSpinner.style.display = 'none';
        if (badgeText) {
            badgeText.innerText = '❌ 导入失败';
            badgeText.style.color = '#ef4444';
        }

        setTimeout(() => {
            const bar = document.getElementById('globalAsyncTaskBar');
            const badge = document.getElementById('globalAsyncTaskBadge');
            if (bar) bar.style.display = 'none';
            if (badge) badge.style.display = 'none';
            globalTaskState.collapsed = false;
            if (badgeSpinner) badgeSpinner.style.display = '';
            if (badgeText) badgeText.style.color = '#a5b4fc';
        }, 8000);
    }

    function cancelGlobalAsyncTaskBar() {
        clearSavedActiveImportTask();
        globalTaskState.taskId = null;

        const stgEl = document.getElementById('globalAsyncStage');
        const titleEl = document.getElementById('globalAsyncTitle');
        const btnCancel = document.getElementById('btnCancelGlobalAsyncTask');
        if (titleEl) titleEl.innerHTML = '<span style="color: #f59e0b;">⏹️ 任务已取消</span>';
        if (stgEl) stgEl.innerText = '导入任务已被取消';
        if (btnCancel) btnCancel.style.display = 'none';

        const badgeText = document.getElementById('globalAsyncBadgeText');
        const badgeSpinner = document.getElementById('globalAsyncBadgeSpinner');
        if (badgeSpinner) badgeSpinner.style.display = 'none';
        if (badgeText) {
            badgeText.innerText = '⏹️ 任务已取消';
            badgeText.style.color = '#f59e0b';
        }

        setTimeout(() => {
            const bar = document.getElementById('globalAsyncTaskBar');
            const badge = document.getElementById('globalAsyncTaskBadge');
            if (bar) bar.style.display = 'none';
            if (badge) badge.style.display = 'none';
            globalTaskState.collapsed = false;
            if (badgeSpinner) badgeSpinner.style.display = '';
            if (badgeText) badgeText.style.color = '#a5b4fc';
        }, 3000);
    }

    async function cancelCurrentGlobalImportTask() {
        const taskId = globalTaskState.taskId || (getSavedActiveImportTask() && getSavedActiveImportTask().taskId);
        if (!taskId) return;
        if (!confirm('确定要取消正在执行的后台导入任务吗？')) return;

        try {
            await fetch('/api/private/import_task?task_id=' + taskId, { method: 'DELETE' });
            cancelGlobalAsyncTaskBar();
        } catch (e) {
            console.error('Cancel task failed:', e);
        }
    }

    function pollGlobalImportTask(taskId) {
        if (!taskId) return;
        if (globalImportTaskTimer) clearTimeout(globalImportTaskTimer);

        fetch('/api/private/import_task?task_id=' + taskId)
            .then(res => res.json())
            .then(res => {
                if (!res.success) {
                    clearSavedActiveImportTask();
                    return;
                }
                const status = res.status;
                const prog = res.progress || {};
                const percent = prog.percent || 10;
                let stage = prog.stage || '正在处理中...';
                if (prog.total_files > 0) {
                    stage += ' (' + prog.processed_files + '/' + prog.total_files + ')';
                }

                updateGlobalAsyncTaskBar(percent, stage);

                window.dispatchEvent(new CustomEvent('juku:import_progress', { detail: { taskId, status, progress: prog, result: res.result } }));

                if (status === 'pending' || status === 'scanning' || status === 'matching' || status === 'saving') {
                    globalImportTaskTimer = setTimeout(() => {
                        pollGlobalImportTask(taskId);
                    }, 1200);
                } else if (status === 'completed') {
                    const resData = res.result || {};
                    const total = resData.total || ((resData.added || 0) + (resData.merged || 0));
                    completeGlobalAsyncTaskBar('🎉 异步导入完成！共入库 ' + total + ' 部影片');
                    window.dispatchEvent(new CustomEvent('juku:import_completed', { detail: res.result }));
                } else if (status === 'failed') {
                    failGlobalAsyncTaskBar(res.error_message || '导入任务执行失败');
                    window.dispatchEvent(new CustomEvent('juku:import_failed', { detail: res }));
                } else if (status === 'canceled') {
                    cancelGlobalAsyncTaskBar();
                    window.dispatchEvent(new CustomEvent('juku:import_canceled', { detail: res }));
                }
            })
            .catch(err => {
                globalImportTaskTimer = setTimeout(() => {
                    pollGlobalImportTask(taskId);
                }, 2500);
            });
    }

    function startGlobalImportTask(taskInfo) {
        if (!taskInfo || !taskInfo.taskId) return;
        const taskData = {
            taskId: taskInfo.taskId,
            title: taskInfo.title || '网盘大包后台导入',
            libraryId: taskInfo.libraryId || '',
            collapsed: false,
            timestamp: Date.now()
        };
        saveActiveImportTask(taskData);
        globalTaskState.taskId = taskInfo.taskId;
        globalTaskState.title = taskData.title;
        globalTaskState.collapsed = false;
        showGlobalAsyncTaskBar(taskInfo.taskId, taskData.title);
        pollGlobalImportTask(taskInfo.taskId);
    }

    function checkAndResumeGlobalAsyncTask() {
        const saved = getSavedActiveImportTask();
        if (saved && saved.taskId) {
            globalTaskState.taskId = saved.taskId;
            globalTaskState.title = saved.title || '网盘大包后台导入';
            globalTaskState.collapsed = !!saved.collapsed;
            showGlobalAsyncTaskBar(saved.taskId, globalTaskState.title);
            if (saved.percent) {
                updateGlobalAsyncTaskBar(saved.percent, saved.stage || '');
            }
            pollGlobalImportTask(saved.taskId);
        }
    }

    /* ==================== 语音控制与搜片逻辑 ==================== */
    let speechRecognizer = null;
    let isVoiceListening = false;

    function initSpeechRecognition() {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRecognition) return null;
        try {
            const recognition = new SpeechRecognition();
            recognition.lang = 'zh-CN';
            recognition.continuous = false;
            recognition.interimResults = true;
            recognition.maxAlternatives = 1;
            return recognition;
        } catch (e) {
            return null;
        }
    }

    function openVoiceCommandModal() {
        const modal = document.getElementById('remote-voice-modal');
        if (!modal) return;
        modal.style.display = 'flex';

        const input = document.getElementById('voice-query-input');
        const tip = document.getElementById('voice-status-tip');
        const fb = document.getElementById('voice-feedback-area');
        if (fb) fb.style.display = 'none';

        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (SpeechRecognition) {
            if (tip) tip.innerText = '点击上方麦克风说话，或直接输入';
            startVoiceListening();
        } else {
            if (tip) tip.innerText = '当前浏览器未开启系统语音听写，可使用输入法语音输入';
            if (input) {
                setTimeout(() => input.focus(), 200);
            }
        }
    }

    function closeVoiceCommandModal() {
        stopVoiceListening();
        const modal = document.getElementById('remote-voice-modal');
        if (modal) modal.style.display = 'none';
    }

    function startVoiceListening() {
        const tip = document.getElementById('voice-status-tip');
        const pulse = document.getElementById('voice-mic-pulse');
        const input = document.getElementById('voice-query-input');

        if (!speechRecognizer) {
            speechRecognizer = initSpeechRecognition();
        }
        if (!speechRecognizer) {
            if (tip) tip.innerText = '您的浏览器不支持 Web Speech，请使用下方输入框或输入法语音';
            if (input) setTimeout(() => input.focus(), 200);
            return;
        }

        try {
            isVoiceListening = true;
            if (pulse) pulse.classList.add('recording');
            if (tip) tip.innerText = '正在倾听中，请说话...';
            if (input) input.value = '';

            speechRecognizer.onresult = (event) => {
                let transcript = '';
                for (let i = event.resultIndex; i < event.results.length; ++i) {
                    transcript += event.results[i][0].transcript;
                }
                if (input) input.value = transcript;
                if (event.results[0] && event.results[0].isFinal) {
                    if (tip) tip.innerText = '识别完成，正在发送...';
                    stopVoiceListening();
                    sendVoiceCommand(transcript);
                }
            };

            speechRecognizer.onerror = (event) => {
                stopVoiceListening();
                if (event.error === 'not-allowed') {
                    if (tip) tip.innerText = '麦克风权限未开启，请在浏览器地址栏允许麦克风';
                } else if (event.error === 'no-speech') {
                    if (tip) tip.innerText = '未检测到声音，点击麦克风可重新尝试';
                } else if (event.error === 'network') {
                    if (tip) tip.innerText = '语音网络连接失败，请使用下方输入框或键盘语音';
                } else {
                    if (tip) tip.innerText = '识别遇到问题 (' + event.error + ')，请手动输入';
                }
            };

            speechRecognizer.onend = () => {
                stopVoiceListening();
            };

            speechRecognizer.start();
        } catch (e) {
            stopVoiceListening();
        }
    }

    function stopVoiceListening() {
        isVoiceListening = false;
        const pulse = document.getElementById('voice-mic-pulse');
        if (pulse) pulse.classList.remove('recording');
        if (speechRecognizer) {
            try { speechRecognizer.stop(); } catch (e) {}
        }
    }

    function toggleVoiceRecording() {
        if (isVoiceListening) {
            stopVoiceListening();
            const tip = document.getElementById('voice-status-tip');
            if (tip) tip.innerText = '已停止录音，点击麦克风可重新说话';
        } else {
            startVoiceListening();
        }
    }

    function submitVoiceCommandFromInput() {
        const input = document.getElementById('voice-query-input');
        const q = input ? input.value.trim() : '';
        if (!q) return;
        sendVoiceCommand(q);
    }

    function quickSendVoice(text) {
        const input = document.getElementById('voice-query-input');
        if (input) input.value = text;
        sendVoiceCommand(text);
    }

    function sendVoiceCommand(query) {
        query = (query || '').trim();
        if (!query) return;

        const tip = document.getElementById('voice-status-tip');
        const fb = document.getElementById('voice-feedback-area');
        if (tip) tip.innerText = '正在执行指令: ' + query;
        if (fb) {
            fb.style.display = 'block';
            fb.className = 'voice-feedback-area pending';
            fb.innerHTML = '⏳ 正在向电视发送指令...';
        }

        fetch('/api/voice/command', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: query })
        })
        .then(res => res.json())
        .then(data => {
            if (fb) {
                if (data.success) {
                    fb.className = 'voice-feedback-area success';
                    const msg = data.message || data.tts || ('已成功执行: ' + query);
                    fb.innerText = '✅ ' + msg;
                    if (tip) tip.innerText = '执行成功！';
                    setTimeout(() => {
                        closeVoiceCommandModal();
                    }, 1800);
                } else {
                    fb.className = 'voice-feedback-area error';
                    fb.innerText = '❌ ' + (data.error || '未能识别该指令');
                    if (tip) tip.innerText = '指令未能匹配，点击麦克风可重新说';
                }
            }
        })
        .catch(err => {
            if (fb) {
                fb.className = 'voice-feedback-area error';
                fb.innerText = '❌ 请求异常: ' + (err.message || '网络连接失败');
            }
        });
    }

    window.openVoiceCommandModal = openVoiceCommandModal;
    window.closeVoiceCommandModal = closeVoiceCommandModal;
    window.toggleVoiceRecording = toggleVoiceRecording;
    window.submitVoiceCommandFromInput = submitVoiceCommandFromInput;
    window.quickSendVoice = quickSendVoice;
    window.sendVoiceCommand = sendVoiceCommand;

    window.startGlobalImportTask = startGlobalImportTask;
    window.collapseGlobalAsyncTaskBar = collapseGlobalAsyncTaskBar;
    window.expandGlobalAsyncTaskBar = expandGlobalAsyncTaskBar;
    window.cancelCurrentGlobalImportTask = cancelCurrentGlobalImportTask;
    window.pollGlobalImportTask = pollGlobalImportTask;
    window.showGlobalAsyncTaskBar = showGlobalAsyncTaskBar;
    window.updateGlobalAsyncTaskBar = updateGlobalAsyncTaskBar;
    window.completeGlobalAsyncTaskBar = completeGlobalAsyncTaskBar;
    window.failGlobalAsyncTaskBar = failGlobalAsyncTaskBar;
    window.cancelGlobalAsyncTaskBar = cancelGlobalAsyncTaskBar;

    // 页面启动时自装配与开启轮询
    function initRemoteComponent() {
        injectRemoteDOM();
        syncKodiPlayback();
        startRemotePolling();
        checkAndResumeGlobalAsyncTask();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initRemoteComponent);
    } else {
        initRemoteComponent();
    }
})();
