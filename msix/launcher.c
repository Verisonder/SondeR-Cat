/*
 * SondeR cat — MSIX launcher
 *
 * The Microsoft Store build is a self-contained MSIX: it bundles its own
 * embeddable Python runtime, so it never needs Python installed on the
 * machine (that was the blocker for the Store). This tiny native exe is the
 * package's entry point. It simply starts the bundled pythonw.exe against
 * sondercat.py, with the working directory set to the app folder.
 *
 * Layout inside the package (relative to this exe):
 *     SondeRCat.exe        <- this launcher
 *     python\pythonw.exe   <- bundled embeddable Python
 *     sondercat.py         <- the app (single source, shared with GitHub build)
 *     libs\                <- vendored PySide6 / pynput
 *     STORE_BUILD          <- marker: flips the app to the Store channel
 *
 * Build (Windows): cl /O2 launcher.c /Fe:SondeRCat.exe
 *              or:  x86_64-w64-mingw32-gcc launcher.c -o SondeRCat.exe -mwindows
 */
#include <windows.h>
#include <shlwapi.h>
#pragma comment(lib, "shlwapi.lib")

int WINAPI wWinMain(HINSTANCE hInst, HINSTANCE hPrev, PWSTR pCmd, int nShow)
{
    (void)hInst; (void)hPrev; (void)pCmd; (void)nShow;

    /* directory this exe lives in = the app root */
    wchar_t dir[MAX_PATH];
    GetModuleFileNameW(NULL, dir, MAX_PATH);
    PathRemoveFileSpecW(dir);

    wchar_t pyw[MAX_PATH];
    wchar_t script[MAX_PATH];
    PathCombineW(pyw, dir, L"python\\pythonw.exe");
    PathCombineW(script, dir, L"sondercat.py");

    /* command line: "python\pythonw.exe" "sondercat.py" */
    wchar_t cmd[MAX_PATH * 3];
    wsprintfW(cmd, L"\"%s\" \"%s\"", pyw, script);

    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    ZeroMemory(&pi, sizeof(pi));

    if (!CreateProcessW(NULL, cmd, NULL, NULL, FALSE,
                        CREATE_NO_WINDOW, NULL, dir, &si, &pi)) {
        MessageBoxW(NULL,
            L"Could not start the bundled Python runtime.",
            L"SondeR cat", MB_ICONERROR | MB_OK);
        return 1;
    }
    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);
    return 0;
}
