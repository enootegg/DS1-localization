#include "Injector.h"

#include "Util/XUtil.h"

#include <Windows.h>
#include <detours.h>

#include <algorithm>
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

// Folder next to the game's executable whose *.bin archives get mounted on top of the game's own.
static constexpr auto kArchiveDirectory = "localization";

// The engine's ref-counted string: a pointer to the characters, preceded by this header. Equality
// is pointer, then mLength, then memcmp -- mCrc is never consulted for the strings we hand over,
// so one built by hand is indistinguishable from the engine's own.
struct StringBuffer {
    uint32_t mRefCount;
    uint32_t mCrc;
    uint32_t mLength;
    uint32_t mCapacity;
    char mData[1];
};

struct String {
    const char *mData;
};

// Never freed, and starts with a reference count the engine can't bring down to zero, so it
// never tries to release memory that didn't come from its own allocator.
static String MakeString(const std::string &inText) {
    auto buffer = static_cast<StringBuffer *>(malloc(sizeof(StringBuffer) + inText.size()));
    buffer->mRefCount = 0x10000000;
    buffer->mCrc = 0;
    buffer->mLength = static_cast<uint32_t>(inText.size());
    buffer->mCapacity = static_cast<uint32_t>(inText.size());
    memcpy(buffer->mData, inText.c_str(), inText.size() + 1);
    return String{buffer->mData};
}

static std::wstring GameDirectory() {
    wchar_t path[MAX_PATH * 4];
    auto length = GetModuleFileNameW(nullptr, path, static_cast<DWORD>(std::size(path)));
    std::wstring result{path, length};
    return result.substr(0, result.find_last_of(L"\\/") + 1);
}

static void Log(const char *inFormat, ...) {
    static FILE *file = _wfopen((GameDirectory() + L"ds1_localizer.log").c_str(), L"w");
    if (!file) {
        return;
    }

    va_list args;
    va_start(args, inFormat);
    vfprintf(file, inFormat, args);
    va_end(args);
    fputc('\n', file);
    fflush(file);
}

// Archive names in mount order: the engine resolves a file from the most recently mounted archive
// that contains it, so of two archives carrying the same file the alphabetically later one wins.
static std::vector<std::string> FindArchives() {
    std::vector<std::string> names;

    WIN32_FIND_DATAW data;
    auto pattern = GameDirectory() + std::wstring{kArchiveDirectory, kArchiveDirectory + strlen(kArchiveDirectory)} + L"\\*.bin";
    auto handle = FindFirstFileW(pattern.c_str(), &data);
    if (handle == INVALID_HANDLE_VALUE) {
        return names;
    }

    do {
        if (data.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) {
            continue;
        }

        std::wstring_view name{data.cFileName};
        if (std::ranges::any_of(name, [](wchar_t c) { return c > 0x7e; })) {
            Log("Skipping '%ls': archive names must be plain ASCII", data.cFileName);
            continue;
        }

        names.emplace_back(name.size(), '\0');
        std::ranges::transform(name, names.back().begin(), [](wchar_t c) { return static_cast<char>(c); });
    } while (FindNextFileW(handle, &data));
    FindClose(handle);

    std::ranges::sort(names);
    return names;
}

class PackFileDevice;

// Mounts one archive. inIndex is the position in the device's archive list; -1 appends, which is
// how the game itself mounts its "Patch" archive so that it overrides everything before it.
static bool (*PackFileDevice_Mount)(PackFileDevice *, const String &inPath, int inIndex);

// Mounts every known archive found in the given directory ("source:data/"). Archives are matched
// against a fixed list of 144 names, so an extra one dropped into data\ would simply be ignored.
static void (*PackFileDevice_MountAll)(PackFileDevice *, const String &inDirectory);

static void PackFileDevice_MountAll_Hook(PackFileDevice *inDevice, const String &inDirectory) {
    PackFileDevice_MountAll(inDevice, inDirectory);

    for (const auto &name: FindArchives()) {
        auto path = MakeString(std::string{"source:"} + kArchiveDirectory + "/" + name);
        auto mounted = PackFileDevice_Mount(inDevice, path, -1);
        Log("%s %s", mounted ? "Mounted" : "FAILED to mount", path.mData);
    }
}

template<typename T>
static bool Resolve(T &outFunction, const char *inName, const char *inSignature) {
    auto base = reinterpret_cast<uintptr_t>(GetModuleHandleW(nullptr));
    uintptr_t start = 0, end = 0;
    if (!XUtil::GetPESectionRange(base, ".text", &start, &end)) {
        Log("Can't find the code section");
        return false;
    }

    auto size = end - start - 64;
    auto matches = XUtil::FindPatterns(start, size, inSignature);
    if (matches.size() != 1) {
        Log("%s: expected 1 signature match, found %zu -- unsupported game version?", inName, matches.size());
        return false;
    }

    outFunction = reinterpret_cast<T>(matches.front());
    return true;
}

static bool sAttached;

void Injector::Attach() {
    // @formatter:off
    bool resolved =
        Resolve(PackFileDevice_MountAll, "PackFileDevice::MountAll", "4C 8B DC 55 53 56 41 56 49 8D 6B A1 48 81 EC B8 00 00 00 48 8B 05 ? ? ? ? 48 33 C4 48 89 45 1F 4D 89 63 D8 4C 8D 05") &&
        Resolve(PackFileDevice_Mount,    "PackFileDevice::Mount",    "40 55 53 57 41 55 41 57 48 8D 6C 24 E0 48 81 EC 20 01 00 00 48 8B 05 ? ? ? ? 48 33 C4 48 89 45 00 48 8B 59 38 4C 8D 79 30");
    // @formatter:on

    if (!resolved) {
        return;
    }

    DetourTransactionBegin();
    DetourUpdateThread(GetCurrentThread());
    DetourAttach(reinterpret_cast<PVOID *>(&PackFileDevice_MountAll), static_cast<PVOID>(PackFileDevice_MountAll_Hook));
    sAttached = DetourTransactionCommit() == NO_ERROR;

    Log(sAttached ? "Hooked, waiting for the game to mount its archives" : "Failed to install the hook");
}

void Injector::Detach() {
    if (!sAttached) {
        return;
    }

    DetourTransactionBegin();
    DetourUpdateThread(GetCurrentThread());
    DetourDetach(reinterpret_cast<PVOID *>(&PackFileDevice_MountAll), static_cast<PVOID>(PackFileDevice_MountAll_Hook));
    DetourTransactionCommit();
}
