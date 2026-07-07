/* SondeR cat setup stub
 *
 * A tiny native Windows installer: shows a friendly dialog, extracts the
 * zip payload appended to this .exe into %LOCALAPPDATA%\SondeRcat, and
 * hands over to install.bat.
 *
 * Payload layout (appended after the compiled stub):
 *     [zip bytes][8-byte little-endian zip size]["SNDRCAT1"]
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "miniz.h"

static const unsigned char MAGIC[8] = {'S','N','D','R','C','A','T','1'};

static void die(const wchar_t *msg)
{
    MessageBoxW(NULL, msg, L"SondeR cat setup", MB_OK | MB_ICONERROR);
    ExitProcess(1);
}

static int write_file(const wchar_t *path, const void *data, size_t n)
{
    HANDLE h = CreateFileW(path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS,
                           FILE_ATTRIBUTE_NORMAL, NULL);
    if (h == INVALID_HANDLE_VALUE)
        return 0;
    DWORD written = 0;
    BOOL ok = WriteFile(h, data, (DWORD)n, &written, NULL);
    CloseHandle(h);
    return ok && written == (DWORD)n;
}

int WINAPI wWinMain(HINSTANCE hInst, HINSTANCE hPrev, PWSTR cmdline, int show)
{
    if (MessageBoxW(NULL,
            L"Install SondeR cat \u2014 a pixel cat that lives on your "
            L"desktop?\n\nIt installs into your user folder only "
            L"(no admin rights needed).\nA small window will show the "
            L"setup progress.",
            L"SondeR cat setup",
            MB_YESNO | MB_ICONQUESTION) != IDYES)
        return 0;

    /* read our own bytes */
    wchar_t self[MAX_PATH];
    GetModuleFileNameW(NULL, self, MAX_PATH);
    FILE *f = _wfopen(self, L"rb");
    if (!f)
        die(L"Couldn't read the installer file.");
    fseek(f, 0, SEEK_END);
    long fsize = ftell(f);
    rewind(f);
    unsigned char *whole = (unsigned char *)malloc((size_t)fsize);
    if (!whole || fread(whole, 1, (size_t)fsize, f) != (size_t)fsize)
        die(L"Couldn't read the installer file.");
    fclose(f);

    /* locate payload via footer */
    if (fsize < 16 || memcmp(whole + fsize - 8, MAGIC, 8) != 0)
        die(L"This installer looks damaged (re-download it, please).");
    unsigned long long zsize = 0;
    memcpy(&zsize, whole + fsize - 16, 8);
    if (zsize == 0 || zsize > (unsigned long long)fsize - 16)
        die(L"This installer looks damaged (re-download it, please).");
    const unsigned char *zip = whole + fsize - 16 - zsize;

    /* destination: %LOCALAPPDATA%\SondeRcat\sondercat */
    wchar_t local[MAX_PATH], dest[MAX_PATH], sub[MAX_PATH];
    if (!GetEnvironmentVariableW(L"LOCALAPPDATA", local, MAX_PATH))
        die(L"Couldn't find your user folder.");
    _snwprintf(dest, MAX_PATH, L"%s\\SondeRcat", local);
    CreateDirectoryW(dest, NULL);
    _snwprintf(sub, MAX_PATH, L"%s\\sondercat", dest);
    CreateDirectoryW(sub, NULL);

    /* extract every payload file (all live under sondercat/) */
    mz_zip_archive za;
    memset(&za, 0, sizeof(za));
    if (!mz_zip_reader_init_mem(&za, zip, (size_t)zsize, 0))
        die(L"Couldn't open the embedded files (re-download, please).");
    int n = (int)mz_zip_reader_get_num_files(&za);
    for (int i = 0; i < n; i++) {
        mz_zip_archive_file_stat st;
        if (!mz_zip_reader_file_stat(&za, i, &st))
            die(L"Couldn't unpack a file.");
        if (mz_zip_reader_is_file_a_directory(&za, i))
            continue;
        size_t usz = 0;
        void *data = mz_zip_reader_extract_to_heap(&za, i, &usz, 0);
        if (!data)
            die(L"Couldn't unpack a file.");
        wchar_t wname[MAX_PATH];
        MultiByteToWideChar(CP_UTF8, 0, st.m_filename, -1, wname, MAX_PATH);
        for (wchar_t *p = wname; *p; p++)
            if (*p == L'/')
                *p = L'\\';
        wchar_t out[MAX_PATH];
        _snwprintf(out, MAX_PATH, L"%s\\%s", dest, wname);
        if (!write_file(out, data, usz))
            die(L"Couldn't write files (is SondeR cat running? Quit it "
                L"and run this installer again).");
        mz_free(data);
    }
    mz_zip_reader_end(&za);
    free(whole);

    /* hand over to the real installer */
    wchar_t bat[MAX_PATH];
    _snwprintf(bat, MAX_PATH, L"%s\\sondercat\\install.bat", dest);
    HINSTANCE r = ShellExecuteW(NULL, L"open", bat, NULL, sub, SW_SHOWNORMAL);
    if ((INT_PTR)r <= 32)
        die(L"Unpacked fine, but couldn't start the installer.\n"
            L"Open this folder and double-click install.bat:\n"
            L"%LOCALAPPDATA%\\SondeRcat\\sondercat");
    return 0;
}
