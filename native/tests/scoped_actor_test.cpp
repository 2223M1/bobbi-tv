/* SPDX-License-Identifier: GPL-2.0-or-later */
// Actor/dispatch bodies and message types are extracted from the candidate.
// Only dependencies are instrumented; this does not emulate decoder fidelity.
#include "cores/VideoPlayer/BobiScopedControl.h"
#include "cores/BobiOpenGate.h"
#include "utils/ScopeGuard.h"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <functional>
#include <future>
#include <iostream>
#include <memory>
#include <mutex>
#include <map>
#include <stdexcept>
#include <thread>
#include <vector>

using namespace std::chrono_literals;
using CCriticalSection = std::recursive_mutex;
constexpr int MSGQ_OK = 1, STREAM_NONE = 0, STREAM_AUDIO = 1, STREAM_SUBTITLE = 2;
constexpr int STREAM_SOURCE_NONE = 0, STREAM_SOURCE_NAV = 1;
enum StreamSource { STREAM_SOURCE_DEMUX = 2 };
int STREAM_SOURCE_MASK(int value) { return value; }
constexpr int DVDSTREAM_TYPE_DVD = 1, DVDSTATE_SEEK = 1;
constexpr int DVDSTREAM_TYPE_BLURAY = 2, BLURAY_AUDIO_STREAM = 1, BLURAY_PG_TEXTST_STREAM = 2;
constexpr int DVDSTREAM_TYPE_PVRMANAGER=3, AV_CODEC_ID_VC1=1, AV_CODEC_ID_WMV3=2;
constexpr int DVD_PLAYSPEED_NORMAL = 1000, DVD_PLAYSPEED_PAUSE = 0;
constexpr int CACHESTATE_FLUSH = 1, CACHESTATE_DONE=2, LOGDEBUG = 1, LOGINFO=2;
constexpr int LOGVIDEO = 1;
using ECacheState = int;
template<class... T> void logComponentM(T&&...) {}
template<class... T> void logM(T&&...) {}
struct CAdvancedSettings { int m_videoSeekMinimumDistanceBeforeEof=10; float m_maxTempo=2.1f; };
struct CSettingUtils { template<class T> static int GetAdvancedSettingValue(T, int value) { return value; } };
constexpr double DVD_NOPTS_VALUE = -1e30;
double DVD_MSEC_TO_TIME(double value) { return value * 1000; }
double DVD_TIME_TO_MSEC(double value) { return value / 1000; }
struct CLog { template<class... T> static void Log(T&&...) {} };
enum class MenuType { NONE, NATIVE };
struct IDVDStreamPlayer { static constexpr int SYNC_INSYNC = 1, SYNC_STARTING = 0; };
namespace KODI::UTILITY {
struct CDigest {
  enum class Type { SHA256 };
  static std::string Calculate(Type, const std::string& value) {
    // Cryptographic hashing itself is outside this harness. Distinct identities
    // produce distinct deterministic 64-byte values on both sides of the CAS.
    return std::string(64, value.empty() ? '0' : value.front());
  }
};
}
struct CDVDMsg {
  enum Message {
    PLAYER_BOBI_CONTROL, PLAYER_SET_AUDIOSTREAM, PLAYER_SET_VIDEOSTREAM,
    PLAYER_SET_SUBTITLESTREAM, PLAYER_SET_SUBTITLESTREAM_VISIBLE, SUBTITLE_ADDFILE,
    PLAYER_SEEK, PLAYER_SEEK_CHAPTER, PLAYER_SETSPEED, PLAYER_SET_PROGRAM,
    PLAYER_FRAME_ADVANCE, PLAYER_OPENFILE
  };
  explicit CDVDMsg(Message type): type(type) {}
  virtual ~CDVDMsg() = default;
  bool IsType(Message expected) const { return type == expected; }
  Message type;
};
template<class T> struct CDVDMsgType : CDVDMsg {
  CDVDMsgType(Message type, const T& value): CDVDMsg(type), m_value(value) {}
  T m_value;
};
using CDVDMsgBool = CDVDMsgType<bool>;
#include "actual_scoped_messages.inc"

struct Messenger {
  bool ended=false;
  std::deque<std::pair<int, std::shared_ptr<CDVDMsg>>> rows;
  std::function<void()> beforeGet;
  bool IsInited() const { return !ended; }
  void End() { ended=true; rows.clear(); }
  void Put(std::shared_ptr<CDVDMsg> value, int priority=0) {
    auto at = std::find_if(rows.begin(), rows.end(), [priority](const auto& row) { return row.first < priority; });
    rows.insert(at, {priority, std::move(value)});
  }
  int Get(std::shared_ptr<CDVDMsg>& value, std::chrono::milliseconds) {
    if (rows.empty()) return 0;
    if (beforeGet) beforeGet();
    value = rows.front().second; rows.pop_front(); return MSGQ_OK;
  }
  int GetPacketCount(CDVDMsg::Message type) const {
    return std::count_if(rows.begin(), rows.end(), [type](const auto& row) { return row.second->IsType(type); });
  }
};
struct Announcements {
  std::vector<CVariant> rows;
  void Announce(int, const char*, const CVariant& value) { rows.push_back(value); }
};
namespace ANNOUNCEMENT { constexpr int Player = 1; }
struct NativeSettings { int GetInt(const char*) { return 0; } };
struct SettingsComponent {
  NativeSettings* GetSettings() { static NativeSettings value; return &value; }
  CAdvancedSettings* GetAdvancedSettings() { static CAdvancedSettings value; return &value; }
};
struct CSettings { static constexpr const char* SETTING_COREELEC_AMLOGIC_DV_AUDIO_SEAMLESSBRANCH="sync"; };
struct WinSystem { template<class T> void UnregisterRenderLoop(T*) {} };
struct CVideoPlayer;
struct CApplicationPlayer {
  CVideoPlayer* inner=nullptr;
  CVideoPlayer* GetInternal() const { return inner; }
  CVariant GetBobiState() const;
};
struct AppComponents {
  CApplicationPlayer player;
  template<class T> T* GetComponent() { return &player; }
};
struct CServiceBroker {
  static AppComponents& GetAppComponents() { static AppComponents value; return value; }
  static Announcements* GetAnnouncementManager() { static Announcements value; return &value; }
  static WinSystem* GetWinSystem() { static WinSystem value; return &value; }
  static SettingsComponent* GetSettingsComponent() { static SettingsComponent value; return &value; }
};
struct Outbound { template<class F> void Submit(F work) { work(); } };
struct Settings {
  double m_AudioDelay=0, m_SubtitleDelay=0;
  bool m_SubtitleOn=true;
  int m_AudioStream=0, m_SubtitleStream=0;
  int audio = -1, subtitle = -1;
  bool visible = true;
  void SetAudioStream(int value) { audio = value; }
  void SetSubtitleStream(int value) { subtitle = value; }
  void SetSubtitleVisible(bool value) { visible = value; }
};
struct Process {
  Settings settings;
#ifdef BOBBI_USER_TRANSPORT
  std::recursive_mutex m_stateSection;
  float m_speed=1,m_newSpeed=1,m_tempo=1,m_newTempo=1;
  float &speed=m_speed,&newSpeed=m_newSpeed,&tempo=m_tempo;
  struct Cache { float tempo=1,speed=1; void SetSpeed(float t,float s) { tempo=t;speed=s; } } cache;
  Cache* m_dataCache=&cache;
#else
  float speed=1, newSpeed=1, tempo=1;
#endif
  std::function<void()> onSpeed;
  Settings& GetVideoSettingsLocked() { return settings; }
  Settings GetVideoSettings() { return settings; }
#ifdef BOBBI_USER_TRANSPORT
  void ProductionSetSpeed(float);
  void SetSpeed(float value) { ProductionSetSpeed(value); if(onSpeed) onSpeed(); }
  void SetNewSpeed(float);
  void SetTempo(float);
  void SetNewTempo(float);
  float GetNewSpeed();
  float GetNewTempo();
  float MinTempoPlatform();
  float MaxTempoPlatform();
  bool IsTempoAllowed(float);
#else
  void SetNewSpeed(float value) { newSpeed=value; }
  void SetSpeed(float value) { speed=value; if(onSpeed) onSpeed(); }
  void SetTempo(float value) { tempo=value; }
  bool IsTempoAllowed(float) { return false; }
#endif
  void SetFrameAdvance(bool) {}
  void SetStateSeeking(bool) {}
  void SeekFinished(int) {}
  int64_t GetMaxTime() { return 100000; }
};
enum StreamFlags { FLAG_NONE=0, FLAG_FORCED=1, FLAG_HEARING_IMPAIRED=2 };
struct SelectionStream {
  int source=2, demuxerId=10, id=20;
  std::string language="eng",name="track",codec="aac";
  int flags=0,channels=2;
};
struct SelectionStreams {
  void Clear(int, int) { audio.clear(); subtitle.clear(); }
  std::vector<SelectionStream> audio{{2, 10, 20}, {2, 10, 21}};
  std::vector<SelectionStream> subtitle{{2, 10, 30}, {2, 10, 31}};
  int CountType(int type) { return type == STREAM_AUDIO ? audio.size() : subtitle.size(); }
  SelectionStream& Get(int type, int index) { return type == STREAM_AUDIO ? audio.at(index) : subtitle.at(index); }
};
std::string BobiSubtitleKey(const SelectionStream& stream, const std::string& instance) {
  return instance + ":" + std::to_string(stream.demuxerId) + ":" + std::to_string(stream.id);
}
struct CurrentStream { int id=20, demuxerId=10; int syncState=1; struct Hint { int codec=0; } hint; };
struct CDemuxStream { int dvdNavId=0; };
struct Demuxer {
  double GetStreamLength() { return 100000; }
  bool result=true;
  int seeks=0;
  double lastTime=-1;
  CDemuxStream* GetStream(int, int) { return nullptr; }
  bool SeekTime(double time, bool, double* start=nullptr) {
    ++seeks; lastTime=time; if (start) *start=time*1000; return result;
  }
};
struct CDVDInputStream {
  struct IMenus { virtual ~IMenus()=default; };
  virtual ~CDVDInputStream() = default;
  bool IsStreamType(int) { return false; }
  void* GetIPosTime() { return nullptr; }
  void* GetITimes() { return nullptr; }
  void* GetIDisplayTime() { return nullptr; }
  bool IsRealtime() { return false; }
};
struct CInputStreamPVRBase : CDVDInputStream { void Pause(bool) {} };
struct CDVDInputStreamNavigator : CDVDInputStream {
  bool SetActiveAudioStream(int) { return true; }
  bool SetActiveSubtitleStream(int) { return true; }
};
struct CDVDInputStreamBluray : CDVDInputStream { void EnableStream(int, int, bool) {} };
struct Clock {
  double GetAbsoluteClock() { return 100000000; }
  double GetClock() { return 10000000; }
  void SetSpeed(int) {}
};
struct Edl { double GetTimeAfterRestoringCuts(double time) { return time; } bool HasCuts() { return false; } };
struct Decoder { int speed=1000; double GetCurrentPts() { return 10000000; } void SetSpeed(int value) { speed=value; } };
struct CFileItem {};
using CVideoSettings=Settings;
struct CBookmark { double totalTimeInSeconds=0,timeInSeconds=0; std::string player,playerState; };
struct IPlayerCallback {
  int pauses=0,resumes=0,stops=0,ends=0,errors=0;
  void OnPlayBackPaused() { ++pauses; }
  void OnPlayBackResumed() { ++resumes; }
  void OnPlayBackSpeedChanged(int) {}
  void OnPlayBackStopped() { ++stops; }
  void OnPlayBackEnded() { ++ends; }
  void OnPlayBackError() { ++errors; }
  void StoreVideoSettings(const CFileItem&,const Settings&) {}
  void OnPlayerCloseFile(const CFileItem&,const CBookmark&) {}
};
struct CBobiHandoff {
  static CBobiHandoff& Get() { static CBobiHandoff value; return value; }
  bool Restoring(const std::string&) { return false; }
  bool Restored(const std::string&,const CVariant&,uint64_t) { return true; }
  void Invalidate(const std::string&,const std::string&) {}
  void Terminal(const std::string&,const std::string&) {}
  CVariant Status() { return CVariant(); }
};
struct CBobiGuiGate {
  struct Window { std::string token,role,request,instance; };
  struct State { uint64_t generation=0,userIntent=0; std::string fullscreenInstance; std::map<int,Window> windows; };
  static CBobiGuiGate& Get() { static CBobiGuiGate gate; return gate; }
  State Snapshot() { return {}; }
};
using JSONRPC_STATUS=int;
constexpr int OK=0;
struct ITransportLayer {};
struct IClient {};
struct CPlayerOperations {
  static JSONRPC_STATUS BobiState(const std::string&,ITransportLayer*,IClient*,const CVariant&,CVariant&);
};
struct CBobiCompletion { CVariant Snapshot() const { return CVariant(CVariant::VariantTypeObject); } };
struct CFFmpegLog { static void ClearLogLevel() {} };
void AnnounceBobiReceipt(const CVariant& row) { CServiceBroker::GetAnnouncementManager()->Announce(1,"OnBobiState",row); }

class CVideoPlayer {
public:
  CVideoPlayer() { Reset('a'); }
#ifdef BOBBI_USER_TRANSPORT
  ~CVideoPlayer();
  void FinishBobiUserStop(const CVariant& terminal=CVariant());
  CVariant BobiEvent(const std::string&,const std::string& reason="");
  void OnExit();
  void ProcessFailureProbe();
  void ResetStopProbe();
  CVariant GetBobiSubtitles() const;
#endif
  void Reset(char identity) {
#ifdef BOBBI_USER_TRANSPORT
    ResetStopProbe();
#endif
    m_bobiState = CVariant(CVariant::VariantTypeObject);
    m_bobiState["native_instance"] = std::string(36, identity);
    m_bobiState["request_id"] = std::string(32, identity);
    m_bobiState["file_identity"] = std::string(1, identity);
    m_bobiState["phase"] = "AV_STARTED";
    for (const auto* key : {"user_intent", "subtitle_intent", "audio_intent", "sequence"})
      m_bobiState[key] = uint64_t{0};
    m_bobiState["subtitle_auto_intent"] = uint64_t{0};
    m_bobiState["open_epoch"] = CBobiOpenGate::Get().Epoch();
    m_bobiState["paused"] = false;
    m_bobiState["transport_state"] = "playing";
    m_bobiCommands.Reset();
    m_bAbortRequest=false; m_bCloseRequest=false; m_messenger.ended=false;
  }
  CVariant Command(std::string action="seek", char id='d') {
    auto row = m_bobiState;
    row["action"] = action;
    row["control_protocol"] = 1;
    row["file_sha256"] = KODI::UTILITY::CDigest::Calculate(
        KODI::UTILITY::CDigest::Type::SHA256, row["file_identity"].asString());
    row["command_id"] = std::string(32, id);
    row["expected_sequence"] = row["sequence"];
    row["selection_epoch"] = row["open_epoch"];
    row["position_ms"] = 1000;
    row["index"] = 1;
    row["stream_key"] = BobiSubtitleKey(m_SelectionStreams.Get(
        action == "audio_stream" ? STREAM_AUDIO : STREAM_SUBTITLE, 1), row["native_instance"].asString());
    row["visible"] = false;
    return row;
  }
  std::string Status() { return m_bobiCommands.Recent()[0]["status"].asString(); }
  CVariant GetBobiState() const { std::unique_lock<CCriticalSection> lock(m_bobiLock); return m_bobiState; }
  void BobiUserIntent() { m_bobiState["user_intent"] = m_bobiState["user_intent"].asUnsignedInteger()+1; }
  void BobiSubtitleIntent() { m_bobiState["subtitle_intent"] = m_bobiState["subtitle_intent"].asUnsignedInteger()+1; }
  void InvalidateBobiCompletion() { ++invalidations; }
  bool CanSeek() { return m_State.canseek; }
  bool CanPause() { return m_State.canpause; }
  void SetSubtitleVisibleInternal(bool value) { visible=value; }
  bool GetSubtitleVisible() const { return visible; }
  void SetEnableStream(CurrentStream&, bool value) { enabled=value; }
  bool CloseStream(CurrentStream& current, bool) { if(onClose) onClose(); current.id=-1; return true; }
  bool OpenStream(CurrentStream& current, int, int id, int) {
    ++opens;
    if (onOpen) onOpen();
    if (openResult) current.id=id;
    return openResult;
  }
  void AdaptForcedSubtitles() { ++adaptations; visible=true; }
  int64_t GetUpdatedTime() { return 500; }
  int64_t GetTime() { return 500; }
  void RecallSubtitlesAfterSeek(double, double) {}
  void SetCaching(int) { ++cacheFlushes; }
  void FlushBuffers(double, bool, bool) { ++flushes; }
#ifdef BOBBI_USER_TRANSPORT
  void SetPlaySpeed(int);
  void SetSpeed(float);
  void SetTempo(float);
  bool IsPlaying() { return true; }
  bool IsInMenu() { return m_State.menuType!=MenuType::NONE; }
#else
  void SetPlaySpeed(int value) { m_playSpeed=value; }
#endif
  void UpdateFileItemStreamDetails(CFileItem&) {}
  void UpdatePlayState(int) {}
  void ObserveBobiCompletion(bool,bool,double) {}
  std::string GetPlayerState() { return ""; }
  void ClearSubtitleSeekCache() {}
  bool BobiControl(const CVariant& command);
  void HandleMessages();
#ifdef BOBBI_CE_SUBTITLE_SYNC
  void QueueSubtitleSwitchSeek(const SelectionStream&, const CVariant&, const CVariant&);
#endif
  mutable CCriticalSection m_bobiLock;
  mutable CCriticalSection m_StateSection;
  struct Content { CCriticalSection m_section; SelectionStreams m_selectionStreams; int m_subtitleIndex=0,m_audioIndex=0; };
  mutable Content m_content;
  ECacheState m_caching=0;
  int64_t m_lastChapterSeekTarget=0;
  bool m_subtitleDemuxerEof=false, m_subtitleSeekNewRun=false;
  CVariant m_bobiState;
  CVariant m_bobiStopCommand;
  CBobiCompletion m_bobiCompletion;
  CBobiScopedCommands m_bobiCommands;
  Messenger m_messenger;
  std::shared_ptr<Outbound> m_outboundEvents=std::make_shared<Outbound>();
  std::shared_ptr<Process> m_processInfo=std::make_shared<Process>();
  std::shared_ptr<Demuxer> m_pDemuxer=std::make_shared<Demuxer>();
  std::shared_ptr<Demuxer> m_pSubtitleDemuxer;
  std::shared_ptr<CDVDInputStream> m_pInputStream=std::make_shared<CDVDInputStream>();
  SelectionStreams m_SelectionStreams;
  CurrentStream m_CurrentAudio, m_CurrentVideo, m_CurrentSubtitle;
  CurrentStream m_CurrentTeletext,m_CurrentRadioRDS,m_CurrentAudioID3;
  struct State { MenuType menuType=MenuType::NONE; bool canseek=true,canpause=true;
    std::vector<std::pair<std::string,double>> chapters;
    double timeMax=100000, lastSeek=0, time_offset=0, dts=0,timestamp=0,time=0,startTime=0,timeMin=0; } m_State;
  struct Dvd { int iSelectedAudioStream=0, iSelectedSPUStream=0, state=0; } m_dvd;
  Clock m_clock;
  Edl m_Edl;
  CFileItem m_item;
  IPlayerCallback m_callback;
  std::string m_name="VideoPlayer";
  int m_offset_pts=0,m_streamPlayerSpeed=1000;
  struct Render { void Flush(bool,bool) {} } m_renderManager;
  std::shared_ptr<Decoder> m_VideoPlayerAudio=std::make_shared<Decoder>(),m_VideoPlayerVideo=std::make_shared<Decoder>();
  std::shared_ptr<Demuxer> m_pCCDemuxer;
  std::shared_ptr<CDVDInputStream::IMenus> m_menus;
  std::map<int,int> m_subtitleDemuxerMap;
  struct SpeedState { double rewindTargetPts=DVD_NOPTS_VALUE; } m_SpeedState;
  struct OriginalAudio { void Clear() {} } m_bobiOriginalAudio;
  int m_playSpeed=DVD_PLAYSPEED_NORMAL;
  bool m_bAbortRequest=false, m_bCloseRequest=false,m_bStop=false,m_error=false, visible=true, enabled=true, openResult=true;
  int opens=0, adaptations=0, invalidations=0, cacheFlushes=0, flushes=0;
  std::function<void()> onOpen;
  std::function<void()> onClose;
};
#include "actual_scoped_actor.inc"

void require(bool value, const char* message) { if (!value) throw std::runtime_error(message); }

#ifdef BOBBI_USER_TRANSPORT
void transportTest(const std::string& name) {
  CVideoPlayer p;
  const auto archive=[] { return CBobiScopedTerminals::Get().Recent(); };
  const auto stop=[&] { auto c=p.Command("user_stop"); require(p.BobiControl(c),"stop admission");
    p.HandleMessages(); require(p.Status()=="queued", "stop applied before terminal"); return c; };
  if(name=="user_pause" || name=="user_resume") {
    if(name=="user_resume") { p.m_playSpeed=0; p.m_bobiState["paused"]=true; }
    auto c=p.Command(name); require(p.BobiControl(c),"user admission");
    require(p.Status()=="queued", "admission applied"); p.HandleMessages();
    require(p.Status()=="applied", "user target not applied");
    require(p.m_playSpeed==(name=="user_pause" ? 0 : 1000), "wrong explicit speed");
    require(p.m_bobiState["user_intent"].asUnsignedInteger()==1, "lease not revoked");
    require(p.m_bobiCommands.Recent()[0]["user_intent"]==c["user_intent"],"original intent overwritten");
  } else if(name=="user_idempotent") {
    p.m_playSpeed=0; p.m_bobiState["paused"]=true;
    require(p.BobiControl(p.Command("user_pause")),"same pause admission"); p.HandleMessages();
    require(p.m_playSpeed==0 && p.m_callback.pauses==0 && p.m_bobiState["user_intent"].asUnsignedInteger()==1,
        "same pause toggled or retained lease");
    require(p.BobiControl(p.Command("user_resume",'e')),"resume admission"); p.HandleMessages();
    require(p.BobiControl(p.Command("user_resume",'f')),"same resume admission"); p.HandleMessages();
    require(p.m_playSpeed==1000 && p.m_callback.resumes==1,"resume toggled playing");
  } else if(name=="user_no_seek") {
    p.m_State.canseek=false;
    require(p.BobiControl(p.Command("user_pause")),"no seek pause"); p.HandleMessages();
    require(p.Status()=="applied" && p.m_playSpeed==0,"pause required seek");
    require(p.BobiControl(p.Command("user_resume",'e')),"no seek resume"); p.HandleMessages();
    require(p.m_playSpeed==1000,"resume required seek");
    auto c=p.Command("user_stop",'f'); require(p.BobiControl(c),"no seek stop"); p.HandleMessages(); p.OnExit();
    require(archive()[0]["status"].asString()=="applied","stop required seek");
  } else if(name=="user_unsupported") {
    p.m_State.canpause=false; p.m_State.canseek=false;
    for(auto action : {"user_pause","user_resume"}) {
      auto c=p.Command(action,action[5]=='p'?'d':'e'); require(p.BobiControl(c),"unsupported admission"); p.HandleMessages();
    }
    const auto rows=p.m_bobiCommands.Recent();
    for(size_t i=0;i<rows.size();++i) require(rows[i]["status"].asString()=="rejected","unsupported executed");
    require(p.m_bobiState["user_intent"].asUnsignedInteger()==0,"unsupported intent changed");
  } else if(name=="user_stale" || name=="user_execution_race") {
    for(auto action : {"user_pause","user_resume","user_stop"})
      for(auto field : {"request_id","file_sha256","expected_sequence","selection_epoch","user_intent","subtitle_intent","audio_intent"}) {
        CVideoPlayer q; auto c=q.Command(action);
        if(name=="user_stale") { if(c[field].isString()) c[field]="wrong"; else c[field]=uint64_t{9}; }
        require(q.BobiControl(c),"stale queued admission");
        if(name=="user_execution_race") {
          const std::string key=field;
          if(key=="request_id") q.m_bobiState[key]=std::string(32,'b');
          else if(key=="file_sha256") q.m_bobiState["file_identity"]="b";
          else if(key=="expected_sequence") q.m_bobiState["sequence"]=uint64_t{9};
          else if(key=="selection_epoch") require(CBobiOpenGate::Get().Reserve(CBobiOpenGate::Get().Epoch(),""),"race reserve");
          else q.m_bobiState[key]=uint64_t{9};
        }
        q.HandleMessages();
        require(q.Status()=="rejected" && !q.m_bAbortRequest && q.m_playSpeed==1000,"stale user action executed");
      }
    for(auto action : {"user_pause","user_resume","user_stop"}) {
      CVideoPlayer q; auto wrong=q.Command(action); wrong["native_instance"]=std::string(36,'b');
      require(!q.BobiControl(wrong),"wrong-instance admission");
      auto c=q.Command(action); require(q.BobiControl(c),"replacement admission"); q.Reset('b'); q.HandleMessages();
      require(!q.m_bAbortRequest && q.m_playSpeed==1000 && q.m_bobiCommands.Recent().empty(),"replacement executed user command");
    }
  } else if(name=="user_stop_onexit") {
    auto c=stop();
    require(archive()[0]["status"].asString()=="queued","stop result premature");
    int closed=0; p.onClose=[&] { ++closed; require(archive()[0]["status"].asString()=="queued","stop before stream close"); };
    p.OnExit(); auto row=archive()[0];
    require(closed>=6 && p.m_messenger.ended && p.m_bStop && p.m_callback.stops==1,"real OnExit not completed");
    require(row["status"].asString()=="applied" && row["terminal_reason"].asString()=="STOP","terminal stop result");
    require(row["terminal_sequence"].asUnsignedInteger()>c["expected_sequence"].asUnsignedInteger(),"terminal sequence not advanced");
    CServiceBroker::GetAnnouncementManager()->rows.clear(); p.Reset('b');
    require(archive()[0]==row,"lost announcement/new instance erased result");
  } else if(name=="user_stop_error") {
    stop(); p.m_error=true; p.OnExit();
    require(archive()[0]["status"].asString()=="failed" && archive()[0]["terminal_reason"].asString()=="ERROR","error claimed stop");
  } else if(name=="user_stop_unknown") {
    stop(); auto hold=p.m_pInputStream; bool threw=false;
    try { p.OnExit(); } catch(const std::runtime_error&) { threw=true; }
    require(threw && archive()[0]["status"].asString()=="unknown" && !archive()[0].isMember("terminal_reason"),"OnExit exception claimed terminal");
  } else if(name=="user_stop_reset") {
    stop(); p.Reset('b');
    require(archive()[0]["status"].asString()=="unknown","reset stranded pending");
  } else if(name=="user_stop_destroy") {
    { CVideoPlayer q; require(q.BobiControl(q.Command("user_stop")),"destroy stop"); q.HandleMessages(); }
    require(archive()[0]["status"].asString()=="unknown","destruction stranded pending");
  } else if(name=="user_stop_process_exception") {
    stop(); try { p.ProcessFailureProbe(); } catch(const std::runtime_error&) {}
    require(archive()[0]["status"].asString()=="unknown","Process exception stranded pending");
  } else if(name=="user_stop_original_scope") {
    for(auto key:{"user_intent","subtitle_intent","audio_intent","sequence"}) p.m_bobiState[key]=uint64_t{7};
    auto c=stop(); p.OnExit(); auto row=archive()[0];
    require(BobiScopedSameCommand(row,c),"terminal result replaced original scope");
    require(row["terminal_user_intent"].asUnsignedInteger()==8 && row["user_intent"].asUnsignedInteger()==7,"original and terminal intent mixed");
    require(!p.BobiControl(c),"terminal replay admitted");
  } else if(name=="user_stop_full") {
    for(size_t i=0;i<CBobiScopedTerminals::CAPACITY;++i) {
      auto c=p.Command("user_stop"); std::string id(32,'a'); id[30]="0123456789abcdef"[i/16]; id[31]="0123456789abcdef"[i%16]; c["command_id"]=id;
      require(CBobiScopedTerminals::Get().Reserve(c),"archive fill");
    }
    require(!CBobiScopedTerminals::Get().Available(),"full capability");
    require(!p.GetBobiSubtitles()["can_stop"].asBoolean(),"full archive advertised stop");
    require(p.BobiControl(p.Command("user_stop")),"full actor admission"); p.HandleMessages();
    require(p.Status()=="rejected" && !p.m_bAbortRequest && p.m_bobiState["user_intent"].asUnsignedInteger()==0,"full archive stopped player");
  } else if(name=="user_stop_ttl") {
    CBobiScopedTerminals ledger; const auto t=CBobiScopedTerminals::Clock::now(); auto c=p.Command("user_stop");
    require(ledger.Reserve(c,t),"ttl reserve");
    require(ledger.Recent(t+10000s)[0]["status"].asString()=="queued","pending expired");
    require(ledger.Finish(c,CVariant(),"",t+10001s)["status"].asString()=="unknown","unknown settlement");
    require(ledger.Recent(t+10600s).size()==1 && ledger.Recent(t+10601s).size()==0,"final retention boundary");
  } else if(name=="user_stop_no_terminal_inference") {
    p.BobiEvent("TERMINAL","STOP"); require(archive().empty(),"unassociated STOP manufactured command result");
    p.Reset('a'); auto c=stop(); auto wrong=p.GetBobiState(); wrong["phase"]="TERMINAL"; wrong["reason"]="STOP";
    wrong["sequence"]=uint64_t{9}; wrong["native_instance"]=std::string(36,'b');
    p.FinishBobiUserStop(wrong);
    require(archive()[0]["status"].asString()=="unknown","other instance terminal applied");
  } else if(name=="user_resume_sync" || name=="user_resume_replacement" || name=="user_resume_new_intent") {
    p.m_playSpeed=-2000;
    int dequeues=0;
    if(name=="user_resume_replacement") p.m_messenger.beforeGet=[&] { if(++dequeues==2) p.Reset('b'); };
    if(name=="user_resume_new_intent") p.m_processInfo->onSpeed=[&] { p.BobiUserIntent(); };
    require(p.BobiControl(p.Command("user_resume")),"resume sync admission"); p.HandleMessages();
    require(p.m_playSpeed==1000,"resume not normal");
    require(p.m_pDemuxer->seeks==(name=="user_resume_sync"?1:0),"resume sync escaped original intent/instance");
    if(name=="user_resume_sync") require(p.Status()=="applied" && p.cacheFlushes==0 && p.m_bobiState["user_intent"].asUnsignedInteger()==1,"resume sync changed result/mode/intent");
  } else if(name=="user_state_read") {
    auto& app=CServiceBroker::GetAppComponents().player;
    app.inner=&p;
    const auto read=[] { CVariant row; require(CPlayerOperations::BobiState("",nullptr,nullptr,CVariant(),row)==OK,"state read"); return row; };
    const auto command=stop(); auto row=read();
    require(row["control_protocol"].isInteger() && row["control_protocol"].asInteger()==1 &&
        row["terminal_commands"][0]["status"].asString()=="queued","pending RPC projection");
    require(p.m_bobiState["user_intent"].asUnsignedInteger()==1,"RPC read executed control");
    p.OnExit(); auto terminal=read()["terminal_commands"][0];
    require(terminal["status"].asString()=="applied" && BobiScopedSameCommand(command,terminal),"RPC terminal original command");
    app.inner=nullptr;
    for(int i=0;i<3;++i) { row=read(); require(row["playback"].isNull() && row["terminal_commands"][0]==terminal,"lost result after inner player release"); }
    CVideoPlayer replacement; replacement.Reset('b'); app.inner=&replacement; row=read();
    require(row["playback"]["native_instance"]!=terminal["native_instance"] && row["terminal_commands"][0]==terminal,"new playback overwrote terminal archive");
    app.inner=nullptr;
  } else if(name=="user_capabilities") {
    for(bool pause:{false,true}) for(bool seek:{false,true}) for(bool abort:{false,true}) for(bool menu:{false,true}) {
      p.m_State.canpause=pause; p.m_State.canseek=seek; p.m_bAbortRequest=abort;
      p.m_State.menuType=menu?MenuType::NATIVE:MenuType::NONE; p.m_State.timeMax=0;
      auto row=p.GetBobiSubtitles();
      require(row["status"].asString()=="READY" && row["transport_protocol"].isInteger() && row["transport_protocol"].asInteger()==1,"transport protocol projection");
      for(auto key:{"can_pause","can_resume","can_stop"}) require(row[key].isBoolean(),"capability not bool");
      require(row["can_pause"].asBoolean()==(!abort&&!menu&&pause) && row["can_resume"].asBoolean()==(!abort&&!menu&&(pause||seek)) && row["can_stop"].asBoolean()==(!abort&&!menu),"independent capabilities wrong");
      require(!row["can_seek"].asBoolean(),"unknown duration seeks");
    }
    for(auto state:{"playing","paused","other"}) { p.m_bobiState["transport_state"]=state; require(p.GetBobiSubtitles()["transport_state"].asString()==state,"transport state projection"); }
    p.m_bobiState["phase"]="TERMINAL"; require(p.GetBobiSubtitles().isNull(),"terminal advertised READY capabilities");
  } else if(name=="user_terminal_binding") {
    for(auto field:{"phase","request_id","file_sha256","open_epoch","sequence","user_intent"}) {
      CBobiScopedTerminals archive; auto command=p.Command("user_stop"); auto terminal=p.GetBobiState();
      terminal["phase"]="TERMINAL"; terminal["reason"]="STOP"; terminal["sequence"]=uint64_t{1}; terminal["user_intent"]=uint64_t{1};
      std::string file=command["file_sha256"].asString();
      const std::string key=field;
      if(key=="file_sha256") file=std::string(64,'b');
      else if(key=="phase"||key=="request_id") terminal[key]="wrong";
      else terminal[key]=key=="open_epoch"?uint64_t{99}:uint64_t{0};
      require(archive.Reserve(command),"terminal binding reserve");
      auto result=archive.Finish(command,terminal,file);
      require(result["status"].asString()=="unknown" && !result.isMember("terminal_reason"),"unbound terminal applied");
      terminal["sequence"]=uint64_t{10}; terminal["user_intent"]=uint64_t{10};
      require(archive.Finish(command,terminal,file).isNull() && archive.Recent()[0]==result,"unknown terminal rewritten");
    }
  } else if(name=="user_pending_open" || name=="user_gate_contention" || name=="user_duplicate" || name=="user_active_full") {
    for(auto action:{"user_pause","user_resume","user_stop"}) {
      CVideoPlayer q; const auto command=q.Command(action);
      if(name=="user_active_full") {
        for(int i=0;i<256;++i) { auto fill=q.Command("seek"); std::string id(32,'a'); id[30]="0123456789abcdef"[i/16]; id[31]="0123456789abcdef"[i%16]; fill["command_id"]=id; require(q.m_bobiCommands.Admit(fill),"active fill"); }
        require(!q.BobiControl(command) && !q.m_bAbortRequest,"full active ledger admitted"); continue;
      }
      require(q.BobiControl(command),"guard admission");
      if(name=="user_duplicate") {
        require(!q.BobiControl(command),"duplicate user admission"); q.HandleMessages();
        require(!q.BobiControl(command) && q.m_bobiState["user_intent"].asUnsignedInteger()==1,"duplicate user replay"); continue;
      }
      if(name=="user_pending_open") q.m_messenger.Put(std::make_shared<CDVDMsg>(CDVDMsg::PLAYER_OPENFILE));
      if(name=="user_gate_contention") {
        std::promise<void> locked,done; auto finished=done.get_future();
        std::thread holder([&] { std::lock_guard<std::recursive_mutex> lock(CBobiOpenGate::Get().Mutex()); locked.set_value(); finished.wait(); });
        locked.get_future().wait(); q.HandleMessages(); done.set_value(); holder.join();
      } else q.HandleMessages();
      require(q.Status()=="rejected" && q.m_playSpeed==1000 && !q.m_bAbortRequest && q.m_bobiState["user_intent"].asUnsignedInteger()==0,"pending open/gate executed user action");
    }
  } else if(name=="user_strict_counters") {
    for(auto action:{"user_pause","user_resume","user_stop"})
      for(auto key:{"expected_sequence","selection_epoch","user_intent","subtitle_intent","audio_intent"})
        for(const auto& value:{CVariant(false),CVariant("0"),CVariant(0.0),CVariant(-1),CVariant()}) {
          CVideoPlayer q; auto command=q.Command(action); command[key]=value;
          require(q.BobiControl(command),"strict counter admission"); q.HandleMessages();
          require(q.Status()=="rejected" && !q.m_bAbortRequest && q.m_bobiState["user_intent"].asUnsignedInteger()==0,"noninteger counter executed");
        }
  } else if(name=="user_retire_many") {
    const char* actions[]={"user_pause","user_resume","seek","audio_stream","manual_subtitle_stream","subtitle_visible"};
    for(int i=0;i<600;++i) {
      auto command=p.Command(actions[i%6]); std::string id(32,'a');
      for(int n=0;n<4;++n) id[31-n]="0123456789abcdef"[(i>>(4*n))&15];
      command["command_id"]=id;
      require(p.BobiControl(command),"native final ledger exhausted after 256"); p.HandleMessages();
      const auto rows=p.m_bobiCommands.Recent();
      require(rows.size()==1 && rows[0]["status"].asString()=="applied" && BobiScopedSameCommand(rows[0],command),"retirement lost original receipt");
    }
  } else if(name=="user_retire_replay") {
    auto original=p.Command("user_pause");require(p.BobiControl(original),"original pause");p.HandleMessages();
    auto next=p.Command("user_resume",'e');require(p.BobiControl(next),"new resume");p.HandleMessages();
    const auto intent=p.m_bobiState["user_intent"];
    require(p.BobiControl(original),"retired ID queues only");p.HandleMessages();
    const auto rows=p.m_bobiCommands.Recent();
    require(rows[0]["status"].asString()=="rejected" && BobiScopedSameCommand(rows[0],original) && p.m_playSpeed==1000 && p.m_bobiState["user_intent"]==intent,"retired original scope replayed");
    auto current=p.Command("user_pause",'f');require(p.BobiControl(current),"current after replay");p.HandleMessages();
    auto reused=p.Command("user_resume");require(p.BobiControl(reused),"reused ID new scope");p.HandleMessages();
    require(BobiScopedSameCommand(p.m_bobiCommands.Recent()[0],reused) && !BobiScopedSameCommand(p.m_bobiCommands.Recent()[0],original),"reused UUID cross-bound original scope");
  } else if(name=="user_retirement_guards" || name=="user_retirement_real_state") {
    for(auto status:{"queued","unknown","applied","rejected","failed"}) {
      CVideoPlayer q;
      for(int i=0;i<256;++i) {
        auto fill=q.Command("seek");std::string id(32,'a');id[30]="0123456789abcdef"[i/16];id[31]="0123456789abcdef"[i%16];fill["command_id"]=id;
        if(name=="user_retirement_guards" && std::string(status)!="queued" && std::string(status)!="unknown") fill["expected_sequence"]=uint64_t{99};
        require(q.m_bobiCommands.Admit(fill),"retirement guard fill");
        if(std::string(status)!="queued")q.m_bobiCommands.Finish(fill,status);
      }
      if(name=="user_retirement_guards")q.m_bobiState["user_intent"]=uint64_t{1};
      auto incoming=q.Command("user_pause");incoming["sequence"]=uint64_t{100};incoming["user_intent"]=uint64_t{100};
      require(!q.BobiControl(incoming),"pending/unknown/future/current final evicted using guest state");
    }
  } else if(name.rfind("user_tempo_",0)==0) {
    const float initial=name=="user_tempo_200"?2.0f:1.5f;
    p.SetTempo(initial);p.HandleMessages();
    require(p.m_playSpeed==static_cast<int>(initial*1000) && p.m_processInfo->GetNewTempo()==initial,"real tempo setup");
    if(name=="user_tempo_legacy_reset") {
      p.SetTempo(1.0f);p.HandleMessages();p.SetSpeed(1.0f);p.HandleMessages();
    } else if(name=="user_tempo_pause") {
      require(p.BobiControl(p.Command("user_pause")),"tempo pause");p.HandleMessages();
      require(p.Status()=="applied" && p.m_playSpeed==0 && p.m_processInfo->GetNewTempo()==initial && p.m_processInfo->tempo==initial && p.GetBobiState()["transport_state"].asString()=="paused","pause erased remembered tempo");
      return;
    } else if(name=="user_tempo_projection") {
      CDVDMsgPlayerSetSpeed::SpeedParams params{1000,false};
      p.m_messenger.Put(std::make_shared<CDVDMsgPlayerSetSpeed>(params));p.HandleMessages();
      require(p.m_playSpeed==1000 && p.m_processInfo->GetNewTempo()==initial && p.GetBobiState()["transport_state"].asString()=="other","mixed speed/tempo claimed normal1x");
      return;
    } else {
      if(name=="user_tempo_applied_guard")p.m_processInfo->onSpeed=[&] { p.BobiUserIntent();p.m_processInfo->SetNewTempo(initial); };
      require(p.BobiControl(p.Command("user_resume")),"tempo resume");p.HandleMessages();
      if(name=="user_tempo_applied_guard") {
        require(p.Status()=="failed" && p.m_playSpeed==1000 && p.m_processInfo->GetNewTempo()==initial && p.GetBobiState()["transport_state"].asString()=="other","applied ignored remembered tempo race");
        return;
      }
      require(p.Status()=="applied","tempo resume result");
      if(name=="user_tempo_legacy_rebound") { p.SetSpeed(0.0f);p.HandleMessages();p.SetSpeed(1.0f);p.HandleMessages(); }
    }
    require(p.m_playSpeed==1000 && p.m_processInfo->GetNewSpeed()==1.0f && p.m_processInfo->GetNewTempo()==1.0f && p.m_processInfo->tempo==1.0f && p.m_processInfo->cache.tempo==1.0f && p.m_processInfo->cache.speed==1.0f,"resume retained/revived old tempo");
    require(p.m_VideoPlayerAudio->speed==1000 && p.m_VideoPlayerVideo->speed==1000 && p.GetBobiState()["transport_state"].asString()=="playing","resume clock/decoder projection");
  } else if(name=="user_full_result_fields") {
    for(auto action:{"seek","audio_stream","manual_subtitle_stream","subtitle_visible","user_pause","user_resume","user_stop"}) {
      CVideoPlayer q;auto command=q.Command(action);
      for(auto field:{"expected_sequence","selection_epoch","user_intent","subtitle_intent","audio_intent"}) command[field]=static_cast<int64_t>(command[field].asUnsignedInteger());
      require(q.BobiControl(command),"full result admission");
      require(BobiScopedSameCommand(q.m_bobiCommands.Recent()[0],command),"queued result lacks original scope");
      CServiceBroker::GetAnnouncementManager()->rows.clear();q.HandleMessages();
      if(std::string(action)=="user_stop")q.OnExit();
      require(q.m_bobiCommands.Recent()[0]["status"].asString()=="applied","valid signed counters not applied");
      require(BobiScopedSameCommand(q.m_bobiCommands.Recent()[0],command),"final Recent lacks original scope");
      bool found=false;for(const auto& row:CServiceBroker::GetAnnouncementManager()->rows) if(row["command_id"]==command["command_id"] && row["action"]==command["action"]) {
        require(BobiScopedSameCommand(row,command),"OnBobiControl lost original scope");found=true;
      }
      require(found,"no original-command result event");
    }
#ifdef BOBBI_CE_SUBTITLE_SYNC
  } else if(name=="user_ce_vc1_resume" || name=="user_ce_vc1_replacement" || name=="user_ce_vc1_new_intent") {
    p.m_playSpeed=0; p.m_bobiState["paused"]=true; p.m_CurrentVideo.hint.codec=AV_CODEC_ID_VC1;
    int dequeues=0;
    if(name=="user_ce_vc1_replacement") p.m_messenger.beforeGet=[&] { if(++dequeues==2) p.Reset('b'); };
    if(name=="user_ce_vc1_new_intent") p.m_processInfo->onSpeed=[&] { p.BobiUserIntent(); };
    require(p.BobiControl(p.Command("user_resume")),"VC1 resume"); p.HandleMessages();
    require(p.m_playSpeed==1000 && p.m_pDemuxer->seeks==(name=="user_ce_vc1_resume"?1:0),"VC1 sync escaped original scope");
    if(name=="user_ce_vc1_resume") require(p.Status()=="applied" && p.cacheFlushes==0 && p.m_pDemuxer->lastTime==10000,"VC1 original mode changed");
#endif
  } else if(name=="user_intent_lock") {
    bool available=false; p.m_processInfo->onSpeed=[&] { std::thread reader([&] { std::unique_lock<CCriticalSection> lock(p.m_bobiLock,std::try_to_lock); available=lock.owns_lock(); }); reader.join(); };
    require(p.BobiControl(p.Command("user_pause")),"pause lock admission"); p.HandleMessages();
    require(available && p.Status()=="applied","speed decoder held receipt lock");
  } else throw std::runtime_error("unknown transport case");
}
#endif

void test(const std::string& name) {
#ifdef BOBBI_USER_TRANSPORT
  if(name.rfind("user_",0)==0) { transportTest(name); return; }
#endif
  CVideoPlayer p;
  if (name == "seek_receipt") {
    auto command=p.Command();
    require(p.BobiControl(command), "seek admission");
    require(p.Status()=="queued" && p.m_pDemuxer->seeks==0, "queued must not mean applied");
    p.HandleMessages();
    require(p.Status()=="applied" && p.m_pDemuxer->seeks==1, "seek final applied");
  } else if (name == "seek_failed") {
    p.m_pDemuxer->result=false;
    require(p.BobiControl(p.Command()), "failed seek admission"); p.HandleMessages();
    require(p.Status()=="failed", "failed demuxer seek not applied");
  } else if (name == "stale_cas") {
    for (const auto* field : {"request_id", "file_sha256", "user_intent", "subtitle_intent",
                             "audio_intent", "expected_sequence", "selection_epoch"}) {
      CVideoPlayer trial;
      auto command=trial.Command();
      if (command[field].isString()) command[field]="wrong"; else command[field]=uint64_t{9};
      require(trial.BobiControl(command), "stale admitted only as queued"); trial.HandleMessages();
      require(trial.Status()=="rejected" && trial.m_pDemuxer->seeks==0, "stale CAS touched demuxer");
    }
  } else if (name == "stream_key") {
    auto command=p.Command("audio_stream"); command["stream_key"]="wrong";
    require(p.BobiControl(command), "stream admission"); p.HandleMessages();
    require(p.Status()=="rejected" && p.opens==0, "unbound stream executed");
  } else if (name == "duplicate") {
    auto command=p.Command(); require(p.BobiControl(command), "first admit");
    require(!p.BobiControl(command), "duplicate before execution"); p.HandleMessages();
    require(!p.BobiControl(command) && p.m_pDemuxer->seeks==1, "duplicate after execution");
  } else if (name == "manual_subtitle_off") {
    auto stale=p.Command("manual_subtitle_stream", 'e');
    require(p.BobiControl(p.Command("subtitle_visible")), "off admit"); p.HandleMessages();
    require(p.Status()=="applied" && !p.visible && !p.enabled, "manual off did not apply");
    require(p.m_bobiState["subtitle_intent"].asUnsignedInteger()==1, "manual off watermark");
    require(p.BobiControl(stale), "stale subtitle admit"); p.HandleMessages();
    require(!p.visible && p.opens==0, "stale selection reenabled subtitle");
    auto audio=p.Command("audio_stream", 'f'); require(p.BobiControl(audio), "audio after off");
    p.HandleMessages(); require(!p.visible && p.adaptations==0, "audio reversed manual subtitle off");
  } else if (name == "audio_failed") {
    p.openResult=false; require(p.BobiControl(p.Command("audio_stream")), "audio admit");
    p.HandleMessages(); require(p.Status()=="failed", "failed OpenStream reported applied");
  } else if (name == "audio_resync") {
    require(p.BobiControl(p.Command("audio_stream")), "audio admit"); p.HandleMessages();
    require(p.Status()=="applied" && p.opens==1 && p.m_pDemuxer->seeks==1, "audio resync path");
    require(p.cacheFlushes==0, "internal audio resync lost trickplay mode");
    require(p.m_bobiState["user_intent"].asUnsignedInteger()==1, "internal resync created user intent");
  } else if (name == "resync_replacement") {
    int dequeues=0;
    p.m_messenger.beforeGet=[&] { if (++dequeues==2) p.Reset('b'); };
    require(p.BobiControl(p.Command("audio_stream")), "audio admit"); p.HandleMessages();
    require(p.opens==1 && p.m_pDemuxer->seeks==0, "old audio sync reached replacement player");
  } else if (name == "decoder_intent_lock") {
    bool available=false;
    p.onOpen=[&] {
      std::thread reader([&] {
        std::unique_lock<CCriticalSection> lock(p.m_bobiLock, std::try_to_lock);
        available=lock.owns_lock();
      });
      reader.join();
    };
    require(p.BobiControl(p.Command("audio_stream")), "audio admit"); p.HandleMessages();
    require(available, "decoder opening retains intent lock and blocks readers/manual intent");
  } else if (name == "resync_new_manual") {
    p.onOpen=[&] { p.BobiUserIntent(); };
    require(p.BobiControl(p.Command("audio_stream")), "audio admit"); p.HandleMessages();
    require(p.Status()=="applied" && p.opens==1, "original audio result");
    require(p.m_pDemuxer->seeks==0, "audio sync borrowed a newer manual intent");
  } else if (name == "same_id_replacement") {
    auto old=p.Command(); require(p.BobiControl(old), "old admit");
    p.Reset('b'); auto current=p.Command(); require(p.BobiControl(current), "replacement admit");
    p.HandleMessages();
    require(p.Status()=="applied" && p.m_pDemuxer->seeks==1, "stale command overwrote replacement receipt");
#ifdef BOBBI_CE_SUBTITLE_SYNC
  } else if (name == "ce_subtitle_resync") {
    require(p.BobiControl(p.Command("manual_subtitle_stream")), "subtitle admit"); p.HandleMessages();
    require(p.Status()=="applied" && p.opens==1 && p.m_pDemuxer->seeks==1, "CE subtitle resync retained");
    require(p.cacheFlushes==0 && p.m_bobiState["user_intent"].asUnsignedInteger()==1,
        "CE subtitle resync mode/intent drift");
  } else if (name == "ce_subtitle_replacement") {
    int dequeues=0;
    p.m_messenger.beforeGet=[&] { if (++dequeues==2) p.Reset('b'); };
    require(p.BobiControl(p.Command("manual_subtitle_stream")), "subtitle admit"); p.HandleMessages();
    require(p.opens==1 && p.m_pDemuxer->seeks==0, "CE old subtitle sync reached replacement");
  } else if (name == "ce_subtitle_new_manual") {
    p.onOpen=[&] { p.BobiSubtitleIntent(); };
    require(p.BobiControl(p.Command("manual_subtitle_stream")), "subtitle admit"); p.HandleMessages();
    require(p.Status()=="applied" && p.m_pDemuxer->seeks==0, "CE subtitle sync borrowed newer intent");
  } else if (name == "ce_subtitle_original_mode") {
    p.m_CurrentAudio.syncState=IDVDStreamPlayer::SYNC_STARTING;
    p.m_State.dts=700000; p.m_State.time_offset=100000;
    p.m_messenger.Put(std::make_shared<CDVDMsgPlayerSetSubtitleStream>(1)); p.HandleMessages();
    require(p.m_pDemuxer->seeks==1 && p.m_pDemuxer->lastTime==700 && p.cacheFlushes==0,
        "CE original subtitle dts/time offset resync changed");
  } else if (name == "ce_subtitle_non_demux") {
    p.m_SelectionStreams.subtitle[1].source=3;
    require(p.BobiControl(p.Command("manual_subtitle_stream")), "subtitle admit"); p.HandleMessages();
    require(p.Status()=="applied" && p.m_pDemuxer->seeks==0, "CE non-demux subtitle added seek");
#endif
  } else if (name == "pending_manual") {
    require(p.BobiControl(p.Command()), "seek admit");
    p.m_messenger.Put(std::make_shared<CDVDMsg>(CDVDMsg::PLAYER_OPENFILE));
    p.HandleMessages(); require(p.Status()=="rejected" && !p.m_pDemuxer->seeks, "pending open not fenced");
  } else if (name == "gate_contention") {
    std::promise<void> locked, done;
    auto future=done.get_future();
    std::thread holder([&] { std::lock_guard<std::recursive_mutex> guard(CBobiOpenGate::Get().Mutex());
      locked.set_value(); future.wait(); });
    locked.get_future().wait();
    require(p.BobiControl(p.Command()), "contention admit"); p.HandleMessages();
    done.set_value(); holder.join();
    require(p.Status()=="rejected" && p.m_pDemuxer->seeks==0, "open gate contention not fail-closed");
  } else throw std::runtime_error("unknown test case");
}
int main(int argc, char** argv) {
  try { require(argc==2, "one case required"); test(argv[1]); std::cout<<"PASS "<<argv[1]<<"\n"; }
  catch (const std::exception& error) { std::cerr<<"FAIL "<<error.what()<<"\n"; return 1; }
}
