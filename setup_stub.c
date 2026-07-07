/* SondeR cat setup — fully graphical Windows installer (no terminal, ever).
 *
 * What it does, all with hidden child processes:
 *   1. unpack the app files embedded in this .exe (progress bar)
 *   2. find a WORKING Python 3.9+ (validated by executing it); if none,
 *      install one silently via winget or python.org (per-user, no admin)
 *   3. components (PySide6/pynput) ship PRE-EXTRACTED inside this exe —
 *      no pip, nothing to install, just a health check
 *   4. create a Desktop shortcut (cat icon), offer autostart
 *   5. launch the cat
 *
 * Payload layout appended to the exe: [zip][8-byte LE size]["SNDRCAT1"]
 */
#define WIN32_LEAN_AND_MEAN
#define _WIN32_IE 0x0600
#include <windows.h>
#include <commctrl.h>
#include <shlobj.h>
#include <shellapi.h>
#include <objbase.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "miniz.h"

#define WM_SETSTATUS (WM_APP + 1)   /* lParam = wchar_t* (heap, we free)   */
#define WM_SETBAR    (WM_APP + 2)   /* wParam: 0..100 pos, -1 = marquee    */
#define WM_FINISH    (WM_APP + 3)   /* wParam: 0 ok, 1 failed              */

#define PY_URL  L"https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe"

static HWND g_wnd, g_bar, g_label;
static HFONT g_font;
static volatile LONG g_busy = 1;
static wchar_t g_dest[MAX_PATH];      /* %LOCALAPPDATA%\SondeRcat          */
static wchar_t g_app[MAX_PATH];       /* ...\SondeRcat\sondercat           */
static wchar_t g_python[MAX_PATH];    /* full path to python.exe           */
static FILE *g_log;

static void logline(const char *s)
{
    if (g_log) { fputs(s, g_log); fputc('\n', g_log); fflush(g_log); }
}

static void status(const wchar_t *s)
{
    PostMessageW(g_wnd, WM_SETSTATUS, 0, (LPARAM)_wcsdup(s));
}

static void bar(int pos)
{
    PostMessageW(g_wnd, WM_SETBAR, (WPARAM)pos, 0);
}

static void fail(const wchar_t *s)
{
    MessageBoxW(g_wnd, s, L"SondeR cat setup", MB_OK | MB_ICONERROR);
    PostMessageW(g_wnd, WM_FINISH, 1, 0);
    ExitThread(1);
}

/* run a program with NO window; returns exit code, -1 on failure to start */
static int run_hidden(const wchar_t *exe, wchar_t *cmdline, DWORD timeout_ms)
{
    STARTUPINFOW si; PROCESS_INFORMATION pi;
    memset(&si, 0, sizeof si); si.cb = sizeof si;
    si.dwFlags = STARTF_USESHOWWINDOW; si.wShowWindow = SW_HIDE;
    if (!CreateProcessW(exe, cmdline, NULL, NULL, FALSE,
                        CREATE_NO_WINDOW, NULL, NULL, &si, &pi))
        return -1;
    WaitForSingleObject(pi.hProcess, timeout_ms);
    DWORD code = (DWORD)-1;
    GetExitCodeProcess(pi.hProcess, &code);
    CloseHandle(pi.hProcess); CloseHandle(pi.hThread);
    return (int)code;
}

static int python_ok(const wchar_t *exe)
{
    if (wcsstr(exe, L"WindowsApps"))
        return 0;                     /* Microsoft Store alias trap */
    wchar_t c[MAX_PATH + 160];
    _snwprintf(c, MAX_PATH + 160,
        L"\"%s\" -c \"import struct,sys;"
        L"sys.exit(0 if struct.calcsize('P')==8 and "
        L"sys.version_info>=(3,9) else 3)\"", exe);
    return run_hidden((wchar_t *)exe, c, 60 * 1000) == 0;
}

static int file_exists(const wchar_t *p)
{
    DWORD a = GetFileAttributesW(p);
    return a != INVALID_FILE_ATTRIBUTES && !(a & FILE_ATTRIBUTE_DIRECTORY);
}

/* ------------------------------------------------ find / install python -- */
static int reg_python(HKEY root, DWORD view)
{
    HKEY core;
    if (RegOpenKeyExW(root, L"Software\\Python\\PythonCore", 0,
                      KEY_READ | view, &core) != ERROR_SUCCESS)
        return 0;
    wchar_t best[64] = L"";
    for (DWORD i = 0;; i++) {
        wchar_t name[64]; DWORD n = 64;
        if (RegEnumKeyExW(core, i, name, &n, 0, 0, 0, 0) != ERROR_SUCCESS)
            break;
        if (wcsncmp(name, L"3.", 2) == 0 && wcscmp(name, best) > 0)
            wcscpy(best, name);
    }
    int ok = 0;
    if (best[0]) {
        wchar_t sub[128], path[MAX_PATH]; DWORD sz = sizeof path;
        _snwprintf(sub, 128, L"%s\\InstallPath", best);
        HKEY k;
        if (RegOpenKeyExW(core, sub, 0, KEY_READ | view, &k)
                == ERROR_SUCCESS) {
            if (RegQueryValueExW(k, NULL, 0, 0, (BYTE *)path, &sz)
                    == ERROR_SUCCESS) {
                _snwprintf(g_python, MAX_PATH, L"%s%spython.exe", path,
                           path[wcslen(path) - 1] == L'\\' ? L"" : L"\\");
                ok = python_ok(g_python);
            }
            RegCloseKey(k);
        }
    }
    RegCloseKey(core);
    return ok;
}

static int find_python(void)
{
    if (reg_python(HKEY_CURRENT_USER, 0)) return 1;
    if (reg_python(HKEY_LOCAL_MACHINE, 0)) return 1;
    if (reg_python(HKEY_LOCAL_MACHINE, KEY_WOW64_64KEY)) return 1;
    wchar_t found[MAX_PATH];
    if (SearchPathW(NULL, L"python.exe", NULL, MAX_PATH, found, NULL)
            && python_ok(found)) {
        wcscpy(g_python, found);
        return 1;
    }
    return 0;
}

static void ensure_python(void)
{
    if (find_python()) { logline("python found"); return; }
    /* preferred: Windows' own package manager (trusted, silent) */
    wchar_t wg[MAX_PATH];
    if (SearchPathW(NULL, L"winget.exe", NULL, MAX_PATH, wg, NULL)) {
        status(L"Installing Python via Windows' package manager\u2026");
        bar(-1);
        wchar_t c[640];
        _snwprintf(c, 640,
            L"\"%s\" install -e --id Python.Python.3.12 --silent "
            L"--scope user --accept-package-agreements "
            L"--accept-source-agreements", wg);
        run_hidden(wg, c, 15 * 60 * 1000);
        logline("winget attempted");
        if (find_python()) return;
    }
    status(L"Downloading Python 3.12 (about 25 MB, one time)\u2026");
    bar(-1);
    wchar_t tmp[MAX_PATH], inst[MAX_PATH];
    GetTempPathW(MAX_PATH, tmp);
    _snwprintf(inst, MAX_PATH, L"%spython-setup.exe", tmp);
    if (URLDownloadToFileW(NULL, PY_URL, inst, 0, NULL) != S_OK)
        fail(L"Couldn't download Python.\n\nCheck your internet connection "
             L"and run this installer again.");
    status(L"Installing Python (silent, no admin needed)\u2026");
    wchar_t cmd[1024];
    _snwprintf(cmd, 1024,
               L"\"%s\" /quiet InstallAllUsers=0 PrependPath=1 "
               L"Include_test=0 Include_launcher=0 SimpleInstall=1", inst);
    run_hidden(inst, cmd, 15 * 60 * 1000);
    DeleteFileW(inst);
    logline("python installer done");
    if (!find_python())
        fail(L"Python's installer finished but Python wasn't found.\n"
             L"Restart your PC and run this setup again.");
}

/* --------------------------------------------------------- shortcuts ----- */
static void make_shortcut(int csidl, const wchar_t *pythonw)
{
    wchar_t dir[MAX_PATH], lnk[MAX_PATH], script[MAX_PATH], icon[MAX_PATH];
    if (FAILED(SHGetFolderPathW(NULL, csidl, NULL, 0, dir)))
        return;
    _snwprintf(lnk, MAX_PATH, L"%s\\SondeR cat.lnk", dir);
    _snwprintf(script, MAX_PATH, L"\"%s\\sondercat.py\"", g_app);
    _snwprintf(icon, MAX_PATH, L"%s\\sondercat_gray.ico", g_app);
    IShellLinkW *sl = NULL;
    if (FAILED(CoCreateInstance(&CLSID_ShellLink, NULL, CLSCTX_INPROC_SERVER,
                                &IID_IShellLinkW, (void **)&sl)))
        return;
    sl->lpVtbl->SetPath(sl, pythonw);
    sl->lpVtbl->SetArguments(sl, script);
    sl->lpVtbl->SetWorkingDirectory(sl, g_app);
    sl->lpVtbl->SetIconLocation(sl, icon, 0);
    sl->lpVtbl->SetDescription(sl, L"A pixel cat for your desktop");
    IPersistFile *pf = NULL;
    if (SUCCEEDED(sl->lpVtbl->QueryInterface(sl, &IID_IPersistFile,
                                             (void **)&pf))) {
        pf->lpVtbl->Save(pf, lnk, TRUE);
        pf->lpVtbl->Release(pf);
    }
    sl->lpVtbl->Release(sl);
}

/* ------------------------------------------------------------ worker ----- */
static DWORD WINAPI worker(LPVOID arg)
{
    /* 0. stop any running cats so the update actually takes effect */
    status(L"Stopping any running cats\u2026");
    {
        wchar_t kill[512];
        _snwprintf(kill, 512,
            L"powershell -NoProfile -Command \"Get-CimInstance "
            L"Win32_Process | Where-Object { $_.Name -like 'python*' -and "
            L"$_.CommandLine -match 'sondercat' } | ForEach-Object "
            L"{ Stop-Process -Id $_.ProcessId -Force }\"");
        run_hidden(NULL, kill, 60 * 1000);
        Sleep(400);
    }

    /* 1. unpack embedded payload (RCDATA resource) */
    status(L"Unpacking SondeR cat\u2026");
    HRSRC rc = FindResourceW(NULL, MAKEINTRESOURCEW(2),
                             (LPCWSTR)RT_RCDATA);
    if (!rc) fail(L"This download looks damaged \u2014 please re-download it.");
    DWORD zsize = SizeofResource(NULL, rc);
    const unsigned char *zipb =
        (const unsigned char *)LockResource(LoadResource(NULL, rc));
    if (!zipb || !zsize)
        fail(L"This download looks damaged \u2014 please re-download it.");

    CreateDirectoryW(g_dest, NULL);
    CreateDirectoryW(g_app, NULL);
    mz_zip_archive za; memset(&za, 0, sizeof za);
    if (!mz_zip_reader_init_mem(&za, zipb, (size_t)zsize, 0))
        fail(L"This download looks damaged \u2014 please re-download it.");
    int n = (int)mz_zip_reader_get_num_files(&za);
    for (int i = 0; i < n; i++) {
        mz_zip_archive_file_stat st;
        if (!mz_zip_reader_file_stat(&za, i, &st) ||
            mz_zip_reader_is_file_a_directory(&za, i))
            continue;
        size_t usz = 0;
        void *data = mz_zip_reader_extract_to_heap(&za, i, &usz, 0);
        if (!data) fail(L"Couldn't unpack a file.");
        wchar_t wname[MAX_PATH], out[MAX_PATH];
        MultiByteToWideChar(CP_UTF8, 0, st.m_filename, -1, wname, MAX_PATH);
        for (wchar_t *p = wname; *p; p++) if (*p == L'/') *p = L'\\';
        _snwprintf(out, MAX_PATH, L"%s\\%s", g_dest, wname);
        for (wchar_t *p = out + wcslen(g_dest) + 1; *p; p++)
            if (*p == L'\\') { *p = 0; CreateDirectoryW(out, NULL);
                                 *p = L'\\'; }
        HANDLE h = CreateFileW(out, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS,
                               FILE_ATTRIBUTE_NORMAL, NULL);
        DWORD wr = 0;
        if (h == INVALID_HANDLE_VALUE ||
            !WriteFile(h, data, (DWORD)usz, &wr, NULL) || wr != usz)
            fail(L"Couldn't write files. If a SondeR cat is running, "
                 L"quit it (right-click the cat) and run this again.");
        CloseHandle(h);
        mz_free(data);
        bar((i + 1) * 100 / n);
    }
    mz_zip_reader_end(&za);
    logline("unpacked");

    /* 2. python */
    status(L"Checking for Python\u2026");
    bar(-1);
    ensure_python();

    /* 3. components are pre-extracted into libs\ — just prove they load */
    status(L"Checking everything works\u2026");
    wchar_t cmd[2048];
    _snwprintf(cmd, 2048,
        L"\"%s\" -c \"import sys; sys.path.insert(0, r'%s\\libs'); "
        L"import PySide6.QtWidgets, pynput\"", g_python, g_dest);
    if (run_hidden(g_python, cmd, 5 * 60 * 1000) != 0)
        fail(L"The bundled components failed to load with your Python.\n\n"
             L"A log was saved to %TEMP%\\SondeRcat_setup.log \u2014 "
             L"send it to the developer and this gets fixed fast.");
    logline("health check ok");

    /* 4. shortcuts */
    status(L"Creating shortcuts\u2026");
    wchar_t pythonw[MAX_PATH];
    wcscpy(pythonw, g_python);
    wchar_t *slash = wcsrchr(pythonw, L'\\');
    if (slash) wcscpy(slash + 1, L"pythonw.exe");
    if (!file_exists(pythonw)) wcscpy(pythonw, g_python);
    CoInitialize(NULL);
    make_shortcut(CSIDL_DESKTOPDIRECTORY, pythonw);
    if (MessageBoxW(g_wnd,
            L"Start SondeR cat automatically when Windows starts?",
            L"SondeR cat setup", MB_YESNO | MB_ICONQUESTION) == IDYES)
        make_shortcut(CSIDL_STARTUP, pythonw);
    CoUninitialize();

    /* 5. launch */
    status(L"Done! Launching your cat\u2026");
    bar(100);
    wchar_t args[MAX_PATH * 2];
    _snwprintf(args, MAX_PATH * 2, L"\"%s\" \"%s\\sondercat.py\"",
               pythonw, g_app);
    STARTUPINFOW si; PROCESS_INFORMATION pi;
    memset(&si, 0, sizeof si); si.cb = sizeof si;
    if (CreateProcessW(pythonw, args, NULL, NULL, FALSE, 0, NULL,
                       g_app, &si, &pi)) {
        CloseHandle(pi.hProcess); CloseHandle(pi.hThread);
    }
    Sleep(900);
    PostMessageW(g_wnd, WM_FINISH, 0, 0);
    return 0;
}

/* --------------------------------------------------------------- UI ------ */
static LRESULT CALLBACK wndproc(HWND w, UINT m, WPARAM wp, LPARAM lp)
{
    switch (m) {
    case WM_SETSTATUS:
        SetWindowTextW(g_label, (wchar_t *)lp);
        free((void *)lp);
        return 0;
    case WM_SETBAR:
        if ((int)wp < 0) {
            SetWindowLongPtrW(g_bar, GWL_STYLE,
                GetWindowLongPtrW(g_bar, GWL_STYLE) | PBS_MARQUEE);
            SendMessageW(g_bar, PBM_SETMARQUEE, TRUE, 30);
        } else {
            SendMessageW(g_bar, PBM_SETMARQUEE, FALSE, 0);
            SetWindowLongPtrW(g_bar, GWL_STYLE,
                GetWindowLongPtrW(g_bar, GWL_STYLE) & ~PBS_MARQUEE);
            SendMessageW(g_bar, PBM_SETPOS, wp, 0);
        }
        return 0;
    case WM_FINISH:
        g_busy = 0;
        DestroyWindow(w);
        return 0;
    case WM_CLOSE:
        if (g_busy) return 0;          /* no closing mid-install */
        DestroyWindow(w);
        return 0;
    case WM_DESTROY:
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProcW(w, m, wp, lp);
}

int WINAPI wWinMain(HINSTANCE hInst, HINSTANCE hp, PWSTR cl, int show)
{
    wchar_t local[MAX_PATH], tmp[MAX_PATH], logp[MAX_PATH];
    GetEnvironmentVariableW(L"LOCALAPPDATA", local, MAX_PATH);
    _snwprintf(g_dest, MAX_PATH, L"%s\\SondeRcat", local);
    _snwprintf(g_app, MAX_PATH, L"%s\\sondercat", g_dest);
    GetTempPathW(MAX_PATH, tmp);
    _snwprintf(logp, MAX_PATH, L"%sSondeRcat_setup.log", tmp);
    g_log = _wfopen(logp, L"w");

    INITCOMMONCONTROLSEX icc = {sizeof icc, ICC_PROGRESS_CLASS};
    InitCommonControlsEx(&icc);

    WNDCLASSW wc = {0};
    wc.lpfnWndProc = wndproc;
    wc.hInstance = hInst;
    wc.lpszClassName = L"SondeRcatSetup";
    wc.hbrBackground = (HBRUSH)(COLOR_WINDOW + 1);
    wc.hCursor = LoadCursorW(NULL, IDC_ARROW);
    wc.hIcon = LoadIconW(hInst, MAKEINTRESOURCEW(1));
    RegisterClassW(&wc);

    int W = 480, H = 170;
    RECT scr; SystemParametersInfoW(SPI_GETWORKAREA, 0, &scr, 0);
    g_wnd = CreateWindowExW(0, wc.lpszClassName, L"SondeR cat Setup",
        WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX,
        (scr.right - W) / 2, (scr.bottom - H) / 2, W, H,
        NULL, NULL, hInst, NULL);

    NONCLIENTMETRICSW ncm = {sizeof ncm};
    SystemParametersInfoW(SPI_GETNONCLIENTMETRICS, sizeof ncm, &ncm, 0);
    g_font = CreateFontIndirectW(&ncm.lfMessageFont);

    HWND ico = CreateWindowExW(0, L"STATIC", NULL,
        WS_CHILD | WS_VISIBLE | SS_ICON, 18, 22, 48, 48,
        g_wnd, NULL, hInst, NULL);
    SendMessageW(ico, STM_SETICON,
                 (WPARAM)LoadImageW(hInst, MAKEINTRESOURCEW(1), IMAGE_ICON,
                                    48, 48, 0), 0);
    g_label = CreateWindowExW(0, L"STATIC",
        L"Getting ready\u2026",
        WS_CHILD | WS_VISIBLE, 84, 28, 370, 40, g_wnd, NULL, hInst, NULL);
    SendMessageW(g_label, WM_SETFONT, (WPARAM)g_font, TRUE);
    g_bar = CreateWindowExW(0, PROGRESS_CLASSW, NULL,
        WS_CHILD | WS_VISIBLE | PBS_SMOOTH, 18, 92, 430, 20,
        g_wnd, NULL, hInst, NULL);
    SendMessageW(g_bar, PBM_SETRANGE32, 0, 100);

    ShowWindow(g_wnd, SW_SHOW);
    UpdateWindow(g_wnd);
    CreateThread(NULL, 0, worker, NULL, 0, NULL);

    MSG msg;
    while (GetMessageW(&msg, NULL, 0, 0) > 0) {
        TranslateMessage(&msg);
        DispatchMessageW(&msg);
    }
    if (g_log) fclose(g_log);
    return 0;
}
