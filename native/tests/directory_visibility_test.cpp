// SPDX-License-Identifier: GPL-2.0-or-later
// The included methods are extracted verbatim from the production checkout.
// Only surrounding Kodi services and the GUI visibility expression are stubs.
#include <cassert>
#include <iostream>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <vector>

using CCriticalSection = std::recursive_mutex;
static std::string accountScope = "account-a";
struct Condition
{
  std::string expected;
  bool Get(int) const { return accountScope == expected; }
};
struct InfoManager
{
  std::shared_ptr<Condition> Register(const std::string& value, int)
  {
    return value.empty() ? nullptr : std::make_shared<Condition>(Condition{value});
  }
};
struct GUI
{
  InfoManager manager;
  InfoManager& GetInfoManager() { return manager; }
};
struct CGUIStaticItem;
using CGUIStaticItemPtr = std::shared_ptr<CGUIStaticItem>;
struct CJob { virtual ~CJob() = default; };
struct CDirectoryJob : CJob
{
  std::vector<CGUIStaticItemPtr> rows;
  CDirectoryJob(std::string, std::string, int, int, int, int) {}
  explicit CDirectoryJob(std::vector<CGUIStaticItemPtr> value) : rows(std::move(value)) {}
  const std::vector<CGUIStaticItemPtr>& GetItems() const { return rows; }
  std::string GetTarget() const { return "videos"; }
  void GetItemTypes(std::vector<int>& value) const { value.clear(); }
};
struct JobManager
{
  void CancelJob(unsigned) {}
  unsigned AddJob(CDirectoryJob* job, void*) { delete job; return 1; }
};
struct CServiceBroker
{
  static GUI* GetGUI() { static GUI value; return &value; }
  static JobManager* GetJobManager() { static JobManager value; return &value; }
};
struct CLog { template<class... T> static void Log(T&&...) {} };
constexpr int LOGDEBUG = 0;
struct Label { std::string GetLabel(int, bool) { return "videos"; } };

struct CGUIListItem
{
  virtual ~CGUIListItem() = default;
  virtual bool IsFileItem() const { return true; }
};
struct CFileItem : CGUIListItem
{
  std::string path;
  explicit CFileItem(std::string value) : path(std::move(value)) {}
  const std::string& GetPath() const { return path; }
};
struct CGUIStaticItem : CFileItem
{
  bool m_visState;
  std::shared_ptr<Condition> m_visCondition;
  explicit CGUIStaticItem(const CFileItem& item);
  bool UpdateVisibility(int contextWindow);
  bool IsVisible() const;
  void SetVisibleCondition(const std::string& condition, int context);
};
struct CDirectoryProvider
{
  enum { OK, DONE, INVALIDATED } m_updateState = OK;
  mutable CCriticalSection m_section;
  unsigned m_jobID = 0;
  std::string m_currentUrl = "plugin://test";
  std::string m_currentTarget;
  std::vector<int> m_itemTypes;
  Label m_target;
  int m_parentID = 10000, m_currentSort = 0, m_currentLimit = 20, m_currentBrowse = 0;
  std::vector<CGUIStaticItemPtr> m_items;
  bool UpdateURL() { return false; }
  bool UpdateSort() { return false; }
  bool UpdateLimit() { return false; }
  bool UpdateBrowse() { return false; }
  bool Update(bool forceRefresh);
  void Fetch(std::vector<std::shared_ptr<CGUIListItem>>& items);
  bool IsUpdating() const;
  void OnJobComplete(unsigned int jobID, bool success, CJob* job);
};
struct CGUIControl
{
  bool enabled = true;
  bool CanFocus() const { return enabled; }
};
struct CGUIBaseContainer : CGUIControl
{
  std::shared_ptr<CDirectoryProvider> m_listProvider = std::make_shared<CDirectoryProvider>();
  std::vector<std::shared_ptr<CGUIListItem>> m_items;
  std::shared_ptr<CGUIListItem> m_lastItem;
  std::optional<int> m_lastPageControlOffset;
  bool m_wasReset = false;
  int selected = 0;
  int GetSelectedItem() const { return selected; }
  void SelectItem(int value) { selected = value; }
  void ResetAutoScrolling() {}
  void SetPageControlRange() {}
  void SetInvalid() {}
  void UpdateScrollByLetter() {}
  void Reset();
  void UpdateListProvider(bool forceRefresh = false);
  bool CanFocus() const;
  std::string currentPath() const
  {
    if (selected < 0 || selected >= static_cast<int>(m_items.size())) return {};
    return static_cast<CFileItem*>(m_items[selected].get())->GetPath();
  }
};

#include "actual_directory_visibility.inc"

static CGUIStaticItemPtr item(const std::string& path, const std::string& scope = "account-a")
{
  auto value = std::make_shared<CGUIStaticItem>(CFileItem(path));
  value->SetVisibleCondition(scope, 10000);
  return value;
}
static void completed(CGUIBaseContainer& list, std::vector<CGUIStaticItemPtr> rows)
{
  CDirectoryJob job(std::move(rows));
  list.m_listProvider->OnJobComplete(list.m_listProvider->m_jobID, true, &job);
}
static bool require(bool value, const char* message)
{
  if (!value) std::cerr << "FAIL " << message << '\n';
  return value;
}
int main()
{
  CGUIBaseContainer list;
  completed(list, {item("resume:a"), item("resume:b")});
  list.UpdateListProvider();
  if (!require(list.m_items.size() == 2 && list.CanFocus(), "DONE same-tick visibility/focusability")) return 1;

  // User navigated while the provider was fetching. Resolve that current path,
  // not a remembered selection from before the request started.
  list.m_listProvider->m_jobID = 9;
  list.SelectItem(1);
  completed(list, {item("resume:new"), item("resume:a"), item("resume:b")});
  list.UpdateListProvider();
  if (!require(list.currentPath() == "resume:b" && list.selected == 2 && list.CanFocus(),
               "late reordered refresh retains current path")) return 1;

  // A second result reorders that same path again. This fixture checks list
  // selection only; window focus ownership requires a separate device test.
  completed(list, {item("resume:b"), item("resume:a")});
  list.UpdateListProvider();
  if (!require(list.currentPath() == "resume:b" && list.selected == 0,
               "second reorder retains current path at new index")) return 1;

  const auto unchangedItems = list.m_items;
  list.m_wasReset = false;
  list.UpdateListProvider();
  if (!require(list.m_items == unchangedItems && list.currentPath() == "resume:b" &&
               list.selected == 0 && !list.m_wasReset && !list.m_listProvider->IsUpdating(),
               "unchanged OK preserves items and selection without resetting")) return 1;

  // Revoke the old account between request and completion. No old card may be
  // published for even one tick; mixed new/old rows must all be evaluated.
  accountScope = "account-b";
  completed(list, {item("old-secret"), item("new-account", "account-b"), item("old-tail")});
  list.UpdateListProvider();
  if (!require(list.m_items.size() == 1 && list.currentPath() == "new-account",
               "DONE scope replacement filters every old account row")) return 1;

  accountScope.clear();
  list.UpdateListProvider();
  if (!require(list.m_items.empty() && !list.CanFocus(), "logout hides existing rows immediately")) return 1;

  completed(list, {item("old-account", "account-b")});
  list.UpdateListProvider();
  if (!require(list.m_items.empty(), "late revoked account result stays hidden")) return 1;

  completed(list, {item("public-recovery", "")});
  list.UpdateListProvider();
  if (!require(list.m_items.size() == 1 && list.CanFocus(), "unconditional recovery row remains visible")) return 1;

  completed(list, {});
  list.UpdateListProvider();
  if (!require(list.m_items.empty() && !list.CanFocus() && !list.m_listProvider->IsUpdating(),
               "empty DONE clears rows and finishes updating")) return 1;

  // Deterministically exercise the legal callback boundary between Update's
  // and Fetch's separate locks, without a sleep or substitute visibility code.
  accountScope = "account-a";
  CGUIBaseContainer interleaved;
  completed(interleaved, {item("previous-account")});
  interleaved.UpdateListProvider();
  interleaved.m_listProvider->m_jobID = 9;
  accountScope = "account-b";
  if (!require(interleaved.m_listProvider->Update(false), "interleaved setup changes old visibility")) return 1;
  completed(interleaved, {item("current-account", "account-b")});
  std::vector<std::shared_ptr<CGUIListItem>> published;
  interleaved.m_listProvider->Fetch(published);
  if (!require(published.size() == 1 &&
               static_cast<CFileItem*>(published.front().get())->GetPath() == "current-account",
               "interleaved completion visibility before publication")) return 1;

  // The callback left DONE pending. Its next Update returns true, so the real
  // caller will Fetch again; revoke access between those two production calls
  // while retaining the exact item whose visibility was already true.
  if (!require(interleaved.m_listProvider->Update(false), "revocation setup consumes DONE")) return 1;
  accountScope.clear();
  interleaved.m_listProvider->Fetch(published);
  if (!require(published.empty(), "already visible row revoked between Update and Fetch stays hidden")) return 1;

  completed(interleaved, {item("revoked-account", "account-b")});
  interleaved.m_listProvider->Fetch(published);
  if (!require(published.empty(), "interleaved revoked completion remains hidden")) return 1;
  std::cout << "PASS 12 production directory visibility/selection cases\n";
}
