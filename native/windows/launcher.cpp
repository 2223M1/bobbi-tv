/* SPDX-License-Identifier: GPL-2.0-or-later */
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <bcrypt.h>
#include <shellapi.h>
#include <shlobj.h>
#include <filesystem>
#include <string>
#include <vector>
#include <stdexcept>
#include <cstdint>
#include <cwctype>
#include "launcher.h"

namespace fs = std::filesystem;
HANDLE lifecycleLock = nullptr;
bool quietFailure = false;
struct Handle {
  HANDLE value = nullptr;
  Handle() = default;
  explicit Handle(HANDLE h) : value(h) {}
  ~Handle() { if (value && value != INVALID_HANDLE_VALUE) CloseHandle(value); }
  Handle(const Handle&) = delete;
  Handle& operator=(const Handle&) = delete;
};

namespace {
int readOnlyKodiLocalePref() noexcept
{
  try {
    wchar_t module[32768];
    fs::path profile;
    if (GetModuleFileNameW(nullptr, module, 32768)) {
      const fs::path root = fs::path(module).parent_path();
      std::error_code ec;
      if (fs::exists(root / L"portable.flag", ec)) profile = root / L"profile";
    }
    if (profile.empty()) {
      wchar_t* local = nullptr;
      if (SUCCEEDED(SHGetKnownFolderPath(FOLDERID_LocalAppData, 0, nullptr, &local)) && local) {
        profile = fs::path(local) / L"bobbi TV" / L"profile";
        CoTaskMemFree(local);
      }
    }
    if (profile.empty()) return 0;
    const fs::path gui = profile / L"userdata" / L"guisettings.xml";
    Handle file(CreateFileW(gui.c_str(), GENERIC_READ,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr));
    if (file.value == INVALID_HANDLE_VALUE) return 0;
    LARGE_INTEGER size{};
    if (!GetFileSizeEx(file.value, &size) || size.QuadPart <= 0 || size.QuadPart > 512 * 1024) return 0;
    std::string raw(static_cast<size_t>(size.QuadPart), '\0');
    DWORD read = 0;
    if (!ReadFile(file.value, raw.data(), static_cast<DWORD>(raw.size()), &read, nullptr) || !read) return 0;
    raw.resize(read);
    const auto pos = raw.find("id=\"locale.language\"");
    if (pos == std::string::npos) return 0;
    const auto gt = raw.find('>', pos);
    const auto lt = gt == std::string::npos ? std::string::npos : raw.find('<', gt + 1);
    if (gt == std::string::npos || lt == std::string::npos || lt <= gt + 1) return 0;
    std::string val = raw.substr(gt + 1, lt - gt - 1);
    for (char& ch : val) ch = static_cast<char>(tolower(static_cast<unsigned char>(ch)));
    if (val.find("resource.language.en") != std::string::npos || val == "en" || val.rfind("en_", 0) == 0) return 1;
    if (val.find("resource.language.zh") != std::string::npos || val == "zh" || val.rfind("zh_", 0) == 0) return -1;
  } catch (...) {
  }
  return 0;
}

bool preferEnglishStartupUi() noexcept
{
  const int kodiPref = readOnlyKodiLocalePref();
  if (kodiPref != 0) return kodiPref > 0;
  wchar_t regBuf[32]{};
  DWORD regBytes = sizeof(regBuf);
  if (RegGetValueW(HKEY_CURRENT_USER, L"Software\\bobbi TV\\Installer", L"InstallerLanguage",
                   RRF_RT_REG_SZ, nullptr, regBuf, &regBytes) == ERROR_SUCCESS) {
    const std::wstring langId(regBuf);
    if (langId == L"1033") return true;
    if (langId == L"2052") return false;
  }
  DWORD regDword = 0;
  regBytes = sizeof(regDword);
  if (RegGetValueW(HKEY_CURRENT_USER, L"Software\\bobbi TV\\Installer", L"InstallerLanguage",
                   RRF_RT_REG_DWORD, nullptr, &regDword, &regBytes) == ERROR_SUCCESS) {
    if (regDword == 1033) return true;
    if (regDword == 2052) return false;
  }
  return PRIMARYLANGID(GetUserDefaultUILanguage()) == LANG_ENGLISH;
}

std::wstring loadResourceOrFallback(UINT id, const wchar_t* fallback) noexcept
{
  wchar_t buffer[1024]{};
  const int len = LoadStringW(GetModuleHandleW(nullptr), id, buffer,
                              static_cast<int>(sizeof(buffer) / sizeof(buffer[0])));
  if (len > 0) return std::wstring(buffer, static_cast<size_t>(len));
  return std::wstring(fallback);
}

void showStartupFailureDialog() noexcept
{
  const bool english = preferEnglishStartupUi();
  const std::wstring title = loadResourceOrFallback(
      english ? IDS_APP_TITLE_EN : IDS_APP_TITLE_ZH, L"bobbi TV");
  const std::wstring body = loadResourceOrFallback(
      english ? IDS_STARTUP_ERROR_EN : IDS_STARTUP_ERROR_ZH,
      english
          ? L"bobbi TV could not start safely. Close any existing instance, then retry.\n"
            L"If an update failed, keep the maintenance folder and use the previous installer.\n"
            L"No account data or profile has been removed."
          : L"bobbi TV \u672a\u80fd\u5b89\u5168\u542f\u52a8\u3002\u8bf7\u5148\u5173\u95ed\u5df2\u8fd0\u884c\u7684\u7a97\u53e3\u540e\u518d\u8bd5\u3002\n"
            L"\u82e5\u66f4\u65b0\u4e2d\u65ad\uff0c\u8bf7\u4fdd\u7559 maintenance \u6587\u4ef6\u5939\u5e76\u8fd0\u884c\u4e0a\u4e00\u7248\u672c\u7684\u5b89\u88c5\u7a0b\u5e8f\u3002\n"
            L"\u8d26\u53f7\u6570\u636e\u4e0e\u4e2a\u4eba\u914d\u7f6e\u5747\u672a\u88ab\u79fb\u9664\u3002");
  MessageBoxW(nullptr, body.c_str(), title.c_str(), MB_OK | MB_ICONERROR);
}
} // namespace

std::wstring quote(const std::wstring& value)
{
  std::wstring out = L"\"";
  size_t slashes = 0;
  for (wchar_t c : value) {
    if (c == L'\\') { ++slashes; continue; }
    out.append(c == L'"' ? slashes * 2 + 1 : slashes, L'\\');
    slashes = 0;
    out += c;
  }
  out.append(slashes * 2, L'\\');
  return out + L"\"";
}

std::string utf8(const std::wstring& value)
{
  const int n = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, value.data(),
      static_cast<int>(value.size()), nullptr, 0, nullptr, nullptr);
  if (!n && !value.empty()) throw std::runtime_error("UTF8 path");
  std::string out(n, '\0');
  WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, value.data(), static_cast<int>(value.size()),
      out.data(), n, nullptr, nullptr);
  return out;
}

std::string json(const std::wstring& value)
{
  std::string out = "\"";
  const char* hex = "0123456789abcdef";
  for (unsigned char c : utf8(value)) {
    if (c == '"' || c == '\\') { out += '\\'; out += c; }
    else if (c < 32) { out += "\\u00"; out += hex[c >> 4]; out += hex[c & 15]; }
    else out += c;
  }
  return out + "\"";
}

std::string nonce()
{
  unsigned char bytes[24];
  if (BCryptGenRandom(nullptr, bytes, sizeof(bytes), BCRYPT_USE_SYSTEM_PREFERRED_RNG) < 0)
    throw std::runtime_error("Random generator");
  std::string out;
  for (unsigned char c : bytes) { out += "0123456789abcdef"[c >> 4]; out += "0123456789abcdef"[c & 15]; }
  return out;
}

DWORD run(const fs::path& executable, const std::vector<std::wstring>& arguments,
          HANDLE inherited, HANDLE job, DWORD& pid)
{
  std::wstring command = quote(executable.wstring());
  for (const auto& value : arguments) command += L" " + quote(value);
  STARTUPINFOEXW startup{};
  startup.StartupInfo.cb = sizeof(startup);
  SIZE_T bytes = 0;
  std::vector<char> attributes;
  DWORD flags = CREATE_SUSPENDED | CREATE_NO_WINDOW;
  std::vector<HANDLE> handles;
  if (inherited) handles.push_back(inherited);
  if (lifecycleLock) handles.push_back(lifecycleLock);
  Handle log, input;
  if (executable.filename() == L"bobbi-maintenance.exe") {
    SECURITY_ATTRIBUTES security{sizeof(SECURITY_ATTRIBUTES), nullptr, TRUE};
    const auto logs = executable.parent_path() / L"maintenance";
    fs::create_directories(logs);
    log.value = CreateFileW((logs / L"launcher.log").c_str(), FILE_APPEND_DATA, FILE_SHARE_READ,
                           &security, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    input.value = CreateFileW(L"NUL", GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,
                             &security, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (log.value == INVALID_HANDLE_VALUE || input.value == INVALID_HANDLE_VALUE)
      throw std::runtime_error("Maintenance diagnostics");
    startup.StartupInfo.dwFlags |= STARTF_USESTDHANDLES;
    startup.StartupInfo.hStdInput = input.value;
    startup.StartupInfo.hStdOutput = startup.StartupInfo.hStdError = log.value;
    handles.push_back(input.value);
    handles.push_back(log.value);
  }
  if (!handles.empty()) {
    InitializeProcThreadAttributeList(nullptr, 1, 0, &bytes);
    attributes.resize(bytes);
    startup.lpAttributeList = reinterpret_cast<LPPROC_THREAD_ATTRIBUTE_LIST>(attributes.data());
    if (!InitializeProcThreadAttributeList(startup.lpAttributeList, 1, 0, &bytes) ||
        !UpdateProcThreadAttribute(startup.lpAttributeList, 0, PROC_THREAD_ATTRIBUTE_HANDLE_LIST,
                                   handles.data(), handles.size() * sizeof(HANDLE), nullptr, nullptr))
      throw std::runtime_error("Handle inheritance");
    flags |= EXTENDED_STARTUPINFO_PRESENT;
  }
  else startup.StartupInfo.cb = sizeof(STARTUPINFOW);
  PROCESS_INFORMATION process{};
  const bool started = CreateProcessW(executable.c_str(), command.data(), nullptr, nullptr,
      !handles.empty(), flags, nullptr, executable.parent_path().c_str(), &startup.StartupInfo, &process);
  if (startup.lpAttributeList) DeleteProcThreadAttributeList(startup.lpAttributeList);
  if (!started) throw std::runtime_error("Start process");
  Handle processHandle(process.hProcess), thread(process.hThread);
  pid = process.dwProcessId;
  if (!AssignProcessToJobObject(job, process.hProcess)) {
    TerminateProcess(process.hProcess, 20);
    throw std::runtime_error("Lifecycle job");
  }
  if (ResumeThread(process.hThread) == static_cast<DWORD>(-1)) throw std::runtime_error("Resume process");
  if (WaitForSingleObject(process.hProcess, INFINITE) != WAIT_OBJECT_0) throw std::runtime_error("Wait process");
  DWORD result = 1;
  if (!GetExitCodeProcess(process.hProcess, &result)) throw std::runtime_error("Process result");
  return result;
}

void pipe(Handle& read, Handle& write)
{
  SECURITY_ATTRIBUTES security{sizeof(SECURITY_ATTRIBUTES), nullptr, TRUE};
  if (!CreatePipe(&read.value, &write.value, &security, 16384) ||
      !SetHandleInformation(write.value, HANDLE_FLAG_INHERIT, 0)) throw std::runtime_error("Lease pipe");
}

void maintenance(const fs::path& root, const fs::path& work, const std::wstring& operation,
                 const std::wstring& bundle, DWORD kodi, HANDLE job)
{
  Handle read, write;
  pipe(read, write);
  const auto addons = root / L"host" / L"addons";
  const std::string receipt = "{\"operation\":" + json(operation) + ",\"bundle\":" + json(bundle) +
      ",\"addons_root\":" + json(addons.wstring()) + ",\"work_root\":" + json(work.wstring()) +
      ",\"profile\":\"windows\",\"parent_pid\":" + std::to_string(GetCurrentProcessId()) +
      ",\"kodi_pid\":" + std::to_string(kodi) + ",\"nonce\":\"" + nonce() + "\"}\n";
  DWORD written = 0;
  if (receipt.size() > 8192 || !WriteFile(write.value, receipt.data(), static_cast<DWORD>(receipt.size()),
                                        &written, nullptr) || written != receipt.size())
    throw std::runtime_error("Lease receipt");
  std::vector<std::wstring> args{operation, L"--addons-root", addons.wstring(), L"--work-root", work.wstring(),
      L"--profile", L"windows", L"--lease-pipe-handle", std::to_wstring(reinterpret_cast<uintptr_t>(read.value))};
  if (!bundle.empty()) { args.push_back(L"--bundle"); args.push_back(bundle); }
  DWORD pid;
  if (run(root / L"bobbi-maintenance.exe", args, read.value, job, pid)) throw std::runtime_error("Maintenance failed");
}

int WINAPI wWinMain(HINSTANCE, HINSTANCE, PWSTR, int)
{
  try {
    wchar_t module[32768];
    if (!GetModuleFileNameW(nullptr, module, 32768)) throw std::runtime_error("Program path");
    const auto root = fs::canonical(fs::path(module).parent_path());
    int argc = 0;
    wchar_t** argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    bool portable = fs::exists(root / L"portable.flag"), noLaunch = false, leaseCheck = false;
    std::wstring operation, bundle;
    for (int i = 1; i < argc; ++i) {
      const std::wstring arg(argv[i]);
      if (arg == L"--portable") portable = true;
      else if (arg == L"--no-launch") { noLaunch = true; quietFailure = true; }
      else if (arg == L"--lease-check") { leaseCheck = true; quietFailure = true; }
      else if (arg == L"--rollback" && operation.empty()) operation = L"rollback";
      else if (arg == L"--apply" && operation.empty() && i + 1 < argc) {
        operation = L"apply"; bundle = fs::canonical(argv[++i]).wstring();
      }
      else { LocalFree(argv); throw std::runtime_error("Arguments"); }
    }
    LocalFree(argv);
    fs::path profile;
    if (portable) profile = root / L"profile";
    else {
      wchar_t* local = nullptr;
      if (FAILED(SHGetKnownFolderPath(FOLDERID_LocalAppData, 0, nullptr, &local))) throw std::runtime_error("Profile path");
      profile = fs::path(local) / L"bobbi TV" / L"profile";
      CoTaskMemFree(local);
    }
    fs::create_directories(profile);
    profile = fs::canonical(profile);
    uint64_t hash = 14695981039346656037ull;
    for (wchar_t c : profile.wstring()) { hash ^= static_cast<uint64_t>(towlower(c)); hash *= 1099511628211ull; }
    Handle mutex(CreateMutexW(nullptr, FALSE, (L"Local\\bobbi.lifecycle." + std::to_wstring(hash)).c_str()));
    const DWORD wait = WaitForSingleObject(mutex.value, 0);
    if (wait != WAIT_OBJECT_0 && wait != WAIT_ABANDONED) throw std::runtime_error("Already running");
    // Inherited, nonshared file ownership survives launcher death until every
    // child has actually exited, closing the abandoned-mutex/orphan race.
    SECURITY_ATTRIBUTES security{sizeof(SECURITY_ATTRIBUTES), nullptr, TRUE};
    Handle fileLock(CreateFileW((profile / L"host-lifecycle.lock").c_str(), GENERIC_READ | GENERIC_WRITE,
        0, &security, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr));
    if (fileLock.value == INVALID_HANDLE_VALUE) throw std::runtime_error("Profile lifecycle lock");
    lifecycleLock = fileLock.value;
    Handle job(CreateJobObjectW(nullptr, nullptr));
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    if (!job.value || !SetInformationJobObject(job.value, JobObjectExtendedLimitInformation, &limits, sizeof(limits)))
      throw std::runtime_error("Lifecycle job");
    // A bootstrap probe supplies a verified exited process for first-start
    // recovery; it is not represented as a Kodi playback process.
    DWORD exited = 0;
    if (run(root / L"bobbi-maintenance.exe", {L"--lifecycle-probe"}, nullptr, job.value, exited))
      throw std::runtime_error("Lifecycle probe");
    const auto work = root / L"maintenance";
    fs::create_directories(work);
    maintenance(root, work, L"recover", L"", exited, job.value);
    if (!operation.empty()) maintenance(root, work, operation, bundle, exited, job.value);
    if (!noLaunch) {
      Handle read, write;
      pipe(read, write);
      SetEnvironmentVariableW(L"BOBBI_PROFILE_PATH", profile.c_str());
      SetEnvironmentVariableW(L"BOBBI_LAUNCHER_PIPE", std::to_wstring(reinterpret_cast<uintptr_t>(read.value)).c_str());
      SetEnvironmentVariableW(L"BOBBI_LAUNCHER_PID", std::to_wstring(GetCurrentProcessId()).c_str());
      SetEnvironmentVariableW(L"BOBBI_LAUNCHER_LOCK", std::to_wstring(reinterpret_cast<uintptr_t>(fileLock.value)).c_str());
      DWORD kodi = 0;
      const std::vector<std::wstring> hostArgs = leaseCheck ? std::vector<std::wstring>{L"--bobbi-lease-check"} : std::vector<std::wstring>{};
      const DWORD code = run(root / L"host" / L"kodi.exe", hostArgs, read.value, job.value, kodi);
      SetEnvironmentVariableW(L"BOBBI_LAUNCHER_PIPE", nullptr);
      SetEnvironmentVariableW(L"BOBBI_LAUNCHER_PID", nullptr);
      SetEnvironmentVariableW(L"BOBBI_LAUNCHER_LOCK", nullptr);
      maintenance(root, work, L"recover", L"", kodi, job.value);
      if (code) throw std::runtime_error("Player exited with error");
    }
    ReleaseMutex(mutex.value);
    return 0;
  }
  catch (...) {
    if (!quietFailure) showStartupFailureDialog();
    return 1;
  }
}
