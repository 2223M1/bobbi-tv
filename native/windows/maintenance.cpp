/* SPDX-License-Identifier: GPL-2.0-or-later */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <filesystem>
#include <string>
#include <vector>
#include <cstdio>

int wmain(int argc, wchar_t** argv)
{
  if (argc == 2 && std::wstring(argv[1]) == L"--lifecycle-probe") return 0;
  wchar_t buffer[32768];
  if (!GetModuleFileNameW(nullptr, buffer, 32768)) return 10;
  const auto root = std::filesystem::path(buffer).parent_path();
  const auto host = root / L"host";
  const auto home = host / L"system" / L"Python";
  SetDefaultDllDirectories(LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
  const auto hostDlls = AddDllDirectory(host.c_str());
  const auto pythonDlls = AddDllDirectory((home / L"DLLs").c_str());
  const auto library = LoadLibraryExW((host / L"python3.8.dll").c_str(), nullptr,
                                    LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
  if (!library) return 11;
  auto setHome = reinterpret_cast<void (*)(const wchar_t*)>(GetProcAddress(library, "Py_SetPythonHome"));
  auto setPath = reinterpret_cast<void (*)(const wchar_t*)>(GetProcAddress(library, "Py_SetPath"));
  auto pyMain = reinterpret_cast<int (*)(int, wchar_t**)>(GetProcAddress(library, "Py_Main"));
  if (!setHome || !setPath || !pyMain) return 12;
  const std::wstring homeString = home.wstring();
  const std::wstring path = (home / L"Lib").wstring() + L";" + (home / L"DLLs").wstring() +
                            L";" + (home / L"Lib" / L"site-packages").wstring() + L";" +
                            (host / L"addons" / L"script.module.bobbi.core" / L"lib").wstring();
  setHome(homeString.c_str());
  setPath(path.c_str());
  std::vector<std::wstring> arguments{L"bobbi-maintenance", L"-I", L"-B"};
  if (argc == 2 && std::wstring(argv[1]) == L"--crypto-self-test")
  {
    arguments.emplace_back(L"-c");
    arguments.emplace_back(L"from Cryptodome.Cipher import AES; from Cryptodome.PublicKey import ECC; "
      L"from Cryptodome.Signature import DSS; from Cryptodome.Hash import SHA256; import Cryptodome; "
      L"key=bytes.fromhex('000102030405060708090a0b0c0d0e0f'); "
      L"plain=bytes.fromhex('00112233445566778899aabbccddeeff'); "
      L"assert AES.new(key,AES.MODE_ECB).encrypt(plain).hex()=='69c4e0d86a7b0430d8cdb78070b4c55a'; "
      L"k=ECC.generate(curve='P-256'); h=SHA256.new(b'bobbi native host'); "
      L"sig=DSS.new(k,'fips-186-3').sign(h); DSS.new(k.public_key(),'fips-186-3').verify(h,sig); "
      L"print('NATIVE_CRYPTO_OK',Cryptodome.__version__)");
  }
  else if (argc == 2 && std::wstring(argv[1]) == L"--juku-self-test")
  {
    arguments.emplace_back(L"-c");
    arguments.emplace_back(L"from bobbi_core import juku_api as j; "
      L"ECC=j.crypto_module('Crypto.PublicKey.ECC'); DSS=j.crypto_module('Crypto.Signature.DSS'); "
      L"SHA256=j.crypto_module('Crypto.Hash.SHA256'); AES=j.crypto_module('Crypto.Cipher.AES'); "
      L"k=ECC.generate(curve='P-256'); h=SHA256.new(b'bobbi portable juku'); "
      L"sig=DSS.new(k,'fips-186-3').sign(h); DSS.new(k.public_key(),'fips-186-3').verify(h,sig); "
      L"key=bytes.fromhex('000102030405060708090a0b0c0d0e0f'); "
      L"plain=bytes.fromhex('00112233445566778899aabbccddeeff'); "
      L"assert AES.new(key,AES.MODE_ECB).encrypt(plain).hex()=='69c4e0d86a7b0430d8cdb78070b4c55a'; "
      L"print('JUKU_CRYPTO_OK',j._CRYPTO_NAMESPACE)");
  }
  else
  {
    arguments.push_back((host / L"tools" / L"private_maintenance.py").wstring());
    for (int i = 1; i < argc; ++i) arguments.emplace_back(argv[i]);
  }
  std::vector<wchar_t*> pointers;
  for (auto& item : arguments) pointers.push_back(item.data());
  const int result = pyMain(static_cast<int>(pointers.size()), pointers.data());
  FreeLibrary(library);
  if (pythonDlls) RemoveDllDirectory(pythonDlls);
  if (hostDlls) RemoveDllDirectory(hostDlls);
  return result;
}
