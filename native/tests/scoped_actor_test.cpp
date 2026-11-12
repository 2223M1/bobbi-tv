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
#include <stdexcept>
#include <thread>
#include <vector>

using namespace std::chrono_literals;
using CCriticalSection = std::recursive_mutex;
constexpr int MSGQ_OK = 1, STREAM_AUDIO = 1, STREAM_SUBTITLE = 2;
constexpr int STREAM_SOURCE_NONE = 0, STREAM_SOURCE_NAV = 1;
enum StreamSource { STREAM_SOURCE_DEMUX = 2 };
int STREAM_SOURCE_MASK(int value) { return value; }
constexpr int DVDSTREAM_TYPE_DVD = 1, DVDSTATE_SEEK = 1;
constexpr int DVDSTREAM_TYPE_BLURAY = 2, BLURAY_AUDIO_STREAM = 1, BLURAY_PG_TEXTST_STREAM = 2;
constexpr int DVD_PLAYSPEED_NORMAL = 1000, DVD_PLAYSPEED_PAUSE = 0;
constexpr int CACHESTATE_FLUSH = 1, LOGDEBUG = 1;
constexpr int LOGVIDEO = 1;
using ECacheState = int;
template<class... T> void logComponentM(T&&...) {}
template<class... T> void logM(T&&...) {}
struct CAdvancedSettings { int m_videoSeekMinimumDistanceBeforeEof=10; };
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
  std::deque<std::pair<int, std::shared_ptr<CDVDMsg>>> rows;
  std::function<void()> beforeGet;
  bool IsInited() const { return true; }
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
struct CServiceBroker {
  static Announcements* GetAnnouncementManager() { static Announcements value; return &value; }
};
struct Outbound { template<class F> void Submit(F work) { work(); } };
struct Settings {
  int audio = -1, subtitle = -1;
  bool visible = true;
  void SetAudioStream(int value) { audio = value; }
  void SetSubtitleStream(int value) { subtitle = value; }
  void SetSubtitleVisible(bool value) { visible = value; }
};
struct Process {
  Settings settings;
  Settings& GetVideoSettingsLocked() { return settings; }
  void SetStateSeeking(bool) {}
  void SeekFinished(int) {}
  int64_t GetMaxTime() { return 100000; }
};
struct SelectionStream { int source=2, demuxerId=10, id=20; };
struct SelectionStreams {
  std::vector<SelectionStream> audio{{2, 10, 20}, {2, 10, 21}};
  std::vector<SelectionStream> subtitle{{2, 10, 30}, {2, 10, 31}};
  int CountType(int type) { return type == STREAM_AUDIO ? audio.size() : subtitle.size(); }
  SelectionStream& Get(int type, int index) { return type == STREAM_AUDIO ? audio.at(index) : subtitle.at(index); }
};
std::string BobiSubtitleKey(const SelectionStream& stream, const std::string& instance) {
  return instance + ":" + std::to_string(stream.demuxerId) + ":" + std::to_string(stream.id);
}
struct CurrentStream { int id=20, demuxerId=10; int syncState=1; };
struct CDemuxStream { int dvdNavId=0; };
struct Demuxer {
  bool result=true;
  int seeks=0;
  double lastTime=-1;
  CDemuxStream* GetStream(int, int) { return nullptr; }
  bool SeekTime(double time, bool, double* start=nullptr) {
    ++seeks; lastTime=time; if (start) *start=time*1000; return result;
  }
};
struct CDVDInputStream {
  virtual ~CDVDInputStream() = default;
  bool IsStreamType(int) { return false; }
  void* GetIPosTime() { return nullptr; }
};
struct CDVDInputStreamNavigator : CDVDInputStream {
  bool SetActiveAudioStream(int) { return true; }
  bool SetActiveSubtitleStream(int) { return true; }
};
struct CDVDInputStreamBluray : CDVDInputStream { void EnableStream(int, int, bool) {} };
struct Clock {
  double GetAbsoluteClock() { return 100000000; }
  double GetClock() { return 100000000; }
};
struct Edl { double GetTimeAfterRestoringCuts(double time) { return time; } };

class CVideoPlayer {
public:
  CVideoPlayer() { Reset('a'); }
  void Reset(char identity) {
    m_bobiState = CVariant(CVariant::VariantTypeObject);
    m_bobiState["native_instance"] = std::string(36, identity);
    m_bobiState["request_id"] = std::string(32, identity);
    m_bobiState["file_identity"] = std::string(1, identity);
    m_bobiState["phase"] = "AV_STARTED";
    for (const auto* key : {"user_intent", "subtitle_intent", "audio_intent", "sequence"})
      m_bobiState[key] = uint64_t{0};
    m_bobiState["subtitle_auto_intent"] = uint64_t{0};
    m_bobiState["open_epoch"] = CBobiOpenGate::Get().Epoch();
    m_bobiCommands.Reset();
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
  CVariant GetBobiState() { std::unique_lock<CCriticalSection> lock(m_bobiLock); return m_bobiState; }
  void BobiUserIntent() { m_bobiState["user_intent"] = m_bobiState["user_intent"].asUnsignedInteger()+1; }
  void BobiSubtitleIntent() { m_bobiState["subtitle_intent"] = m_bobiState["subtitle_intent"].asUnsignedInteger()+1; }
  void InvalidateBobiCompletion() { ++invalidations; }
  bool CanSeek() { return m_State.canseek; }
  void SetSubtitleVisibleInternal(bool value) { visible=value; }
  bool GetSubtitleVisible() { return visible; }
  void SetEnableStream(CurrentStream&, bool value) { enabled=value; }
  bool CloseStream(CurrentStream& current, bool) { current.id=-1; return true; }
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
  void SetPlaySpeed(int value) { m_playSpeed=value; }
  bool BobiControl(const CVariant& command);
  void HandleMessages();
#ifdef BOBBI_CE_SUBTITLE_SYNC
  void QueueSubtitleSwitchSeek(const SelectionStream&, const CVariant&, const CVariant&);
#endif
  CCriticalSection m_bobiLock;
  CCriticalSection m_StateSection;
  ECacheState m_caching=0;
  int64_t m_lastChapterSeekTarget=0;
  bool m_subtitleDemuxerEof=false, m_subtitleSeekNewRun=false;
  CVariant m_bobiState;
  CBobiScopedCommands m_bobiCommands;
  Messenger m_messenger;
  std::shared_ptr<Outbound> m_outboundEvents=std::make_shared<Outbound>();
  std::shared_ptr<Process> m_processInfo=std::make_shared<Process>();
  std::shared_ptr<Demuxer> m_pDemuxer=std::make_shared<Demuxer>();
  std::shared_ptr<Demuxer> m_pSubtitleDemuxer;
  std::shared_ptr<CDVDInputStream> m_pInputStream=std::make_shared<CDVDInputStream>();
  SelectionStreams m_SelectionStreams;
  CurrentStream m_CurrentAudio, m_CurrentVideo, m_CurrentSubtitle;
  struct State { MenuType menuType=MenuType::NONE; bool canseek=true;
    double timeMax=100000, lastSeek=0, time_offset=0, dts=0; } m_State;
  struct Dvd { int iSelectedAudioStream=0, iSelectedSPUStream=0, state=0; } m_dvd;
  Clock m_clock;
  Edl m_Edl;
  struct OriginalAudio { void Clear() {} } m_bobiOriginalAudio;
  int m_playSpeed=DVD_PLAYSPEED_NORMAL;
  bool m_bAbortRequest=false, visible=true, enabled=true, openResult=true;
  int opens=0, adaptations=0, invalidations=0, cacheFlushes=0, flushes=0;
  std::function<void()> onOpen;
};
#include "actual_scoped_actor.inc"

void require(bool value, const char* message) { if (!value) throw std::runtime_error(message); }

void test(const std::string& name) {
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
