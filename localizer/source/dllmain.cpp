#define DLL_PROXY_EXPORT_LISTING_FILE "exports.inc"             // List of exported functions
#define DLL_PROXY_CHECK_MISSING_EXPORTS                         // Strict validation
#define DLL_PROXY_DECLARE_IMPLEMENTATION                        // Then define the whole implementation
#include <QuickDllProxy/DllProxy.h>

#include "Injector/Injector.h"

[[maybe_unused]] BOOL APIENTRY DllMain(HINSTANCE instance, DWORD reason, LPVOID *reserved) {
    (void) instance;
    (void) reserved;

    if (reason == DLL_PROCESS_ATTACH) {
        DllProxy::Initialize();
        Injector::Attach();
    }

    if (reason == DLL_PROCESS_DETACH) {
        Injector::Detach();
    }

    return TRUE;
}
