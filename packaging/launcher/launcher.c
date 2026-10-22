/*
 * DJSync.exe — lanceur portable en UN SEUL FICHIER (Windows).
 *
 * L'application (dossier PyInstaller : DJSync.exe + _internal + tools) est un zip collé à la fin de
 * ce petit exe, suivi d'un bloc de fin :
 *     "DJSYNCPK" | u64 début du zip | u64 taille du zip | version (32 octets, zéros en fin)
 * (cherché dans les 64 derniers Ko : une signature Authenticode peut venir après)
 *
 * Au lancement :
 *   1. si <dossier de l'exe>\.djsync\app\VERSION.txt == version embarquée : on lance l'application ;
 *   2. sinon (premier lancement, exe déplacé seul, dossier supprimé, nouvelle version) : fenêtre de
 *      progression, extraction dans .djsync\app.new, remplacement de .djsync\app, puis lancement.
 *      Tout ce qui est dans .djsync est remplacé SAUF .djsync\data (réglages, journal, moteur yt-dlp).
 * .djsync reçoit les attributs « caché » + « système » : l'utilisateur ne voit que DJSync.exe.
 * L'application reçoit DJSYNC_APP_DIR = dossier de ce lanceur (où vivent ses données) et
 * DJSYNC_LAUNCHER = chemin de ce lanceur (pour pouvoir se désinstaller).
 *
 * Compilation (Linux, mingw-w64) : packaging/build_launcher.sh
 */
#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <commctrl.h>
#include <stdio.h>
#include <stdint.h>
#include <wchar.h>

#include "miniz.h"

#define MAGIC "DJSYNCPK"
#define TRAILER_SIZE (8 + 8 + 8 + 32)
#define CONTENTS L".djsync"

static HWND g_win, g_bar, g_text;

/* ------------------------------------------------------------------ messages */
static void fail(const wchar_t *what, DWORD code) {
    wchar_t msg[1024];
    swprintf(msg, 1024,
             L"DJSync could not start.\n%ls (error %lu)\n\n"
             L"DJSync n'a pas pu démarrer.\n\n"
             L"Check that the drive is not full or read-only, then try again.\n"
             L"Vérifiez que la clé n'est ni pleine ni protégée en écriture, puis réessayez.",
             what, (unsigned long)code);
    OutputDebugStringW(msg);                       /* visible dans un débogueur */
    fwprintf(stderr, L"%ls\n", msg);               /* CI / Wine : sortie d'erreur héritée */
    fflush(stderr);
    MessageBoxW(NULL, msg, L"DJSync", MB_ICONERROR | MB_OK);
}

/* ------------------------------------------------------------ petite fenêtre */
static LRESULT CALLBACK wndproc(HWND h, UINT m, WPARAM w, LPARAM l) {
    if (m == WM_CLOSE) return 0;                  /* pas d'interruption pendant l'extraction */
    return DefWindowProcW(h, m, w, l);
}

static void pump(void) {
    MSG msg;
    while (PeekMessageW(&msg, NULL, 0, 0, PM_REMOVE)) {
        TranslateMessage(&msg);
        DispatchMessageW(&msg);
    }
}

static void show_window(int total) {
    INITCOMMONCONTROLSEX icc = {sizeof(icc), ICC_PROGRESS_CLASS};
    InitCommonControlsEx(&icc);
    WNDCLASSW wc = {0};
    wc.lpfnWndProc = wndproc;
    wc.hInstance = GetModuleHandleW(NULL);
    wc.hIcon = LoadIconW(wc.hInstance, MAKEINTRESOURCEW(1));
    wc.hCursor = LoadCursorW(NULL, (LPCWSTR)IDC_WAIT);
    wc.hbrBackground = (HBRUSH)(COLOR_WINDOW + 1);
    wc.lpszClassName = L"DJSyncSetup";
    RegisterClassW(&wc);
    int w = 460, h = 150;
    int x = (GetSystemMetrics(SM_CXSCREEN) - w) / 2, y = (GetSystemMetrics(SM_CYSCREEN) - h) / 2;
    g_win = CreateWindowExW(0, wc.lpszClassName, L"DJSync",
                            WS_OVERLAPPED | WS_CAPTION | WS_VISIBLE, x, y, w, h, NULL, NULL, wc.hInstance, NULL);
    g_text = CreateWindowExW(0, L"STATIC",
                             L"Preparing DJSync on this drive (first launch only)…\n"
                             L"Préparation de DJSync sur la clé (premier lancement seulement)…",
                             WS_CHILD | WS_VISIBLE, 16, 14, w - 40, 40, g_win, NULL, wc.hInstance, NULL);
    SendMessageW(g_text, WM_SETFONT, (WPARAM)GetStockObject(DEFAULT_GUI_FONT), TRUE);
    g_bar = CreateWindowExW(0, PROGRESS_CLASSW, NULL, WS_CHILD | WS_VISIBLE, 16, 64, w - 48, 22, g_win, NULL,
                            wc.hInstance, NULL);
    SendMessageW(g_bar, PBM_SETRANGE32, 0, total > 0 ? total : 1);
    pump();
}

/* ------------------------------------------------------------------ fichiers */
static int make_dirs(wchar_t *path) {            /* crée tous les dossiers de `path` (modifié puis rétabli) */
    for (wchar_t *p = path + 3; *p; p++) {
        if (*p == L'\\') {
            *p = 0;
            CreateDirectoryW(path, NULL);
            *p = L'\\';
        }
    }
    return CreateDirectoryW(path, NULL) || GetLastError() == ERROR_ALREADY_EXISTS;
}

static void remove_tree(const wchar_t *path) {
    wchar_t pattern[MAX_PATH * 2];
    swprintf(pattern, MAX_PATH * 2, L"%ls\\*", path);
    WIN32_FIND_DATAW fd;
    HANDLE h = FindFirstFileW(pattern, &fd);
    if (h != INVALID_HANDLE_VALUE) {
        do {
            if (!wcscmp(fd.cFileName, L".") || !wcscmp(fd.cFileName, L"..")) continue;
            wchar_t child[MAX_PATH * 2];
            swprintf(child, MAX_PATH * 2, L"%ls\\%ls", path, fd.cFileName);
            SetFileAttributesW(child, FILE_ATTRIBUTE_NORMAL);
            if (fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) remove_tree(child);
            else DeleteFileW(child);
        } while (FindNextFileW(h, &fd));
        FindClose(h);
    }
    SetFileAttributesW(path, FILE_ATTRIBUTE_NORMAL);
    RemoveDirectoryW(path);
}

static size_t write_cb(void *opaque, mz_uint64 ofs, const void *buf, size_t n) {
    DWORD done = 0;
    (void)ofs;                                    /* écriture séquentielle */
    return WriteFile((HANDLE)opaque, buf, (DWORD)n, &done, NULL) ? done : 0;
}

static int read_text(const wchar_t *path, char *out, int size) {
    HANDLE h = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
    if (h == INVALID_HANDLE_VALUE) return 0;
    DWORD n = 0;
    ReadFile(h, out, size - 1, &n, NULL);
    CloseHandle(h);
    out[n] = 0;
    return 1;
}

/* ---------------------------------------------------------------- extraction */
static int extract(const wchar_t *self, uint64_t start, uint64_t size, const wchar_t *base, const char *version) {
    wchar_t staging[MAX_PATH * 2], app[MAX_PATH * 2], data[MAX_PATH * 2];
    swprintf(staging, MAX_PATH * 2, L"%ls\\app.new", base);
    swprintf(app, MAX_PATH * 2, L"%ls\\app", base);
    swprintf(data, MAX_PATH * 2, L"%ls\\data", base);

    FILE *f = _wfopen(self, L"rb");
    if (!f) { fail(L"Cannot read DJSync.exe", GetLastError()); return 0; }
    _fseeki64(f, (long long)start, SEEK_SET);
    mz_zip_archive zip;
    memset(&zip, 0, sizeof(zip));
    if (!mz_zip_reader_init_cfile(&zip, f, size, 0)) {
        fclose(f);
        fail(L"DJSync.exe is damaged: download it again", 0);
        return 0;
    }
    int count = (int)mz_zip_reader_get_num_files(&zip);
    show_window(count);
    make_dirs((wchar_t *)base);
    remove_tree(staging);
    int ok = make_dirs(staging);
    for (int i = 0; ok && i < count; i++) {
        mz_zip_archive_file_stat st;
        if (!mz_zip_reader_file_stat(&zip, i, &st)) { ok = 0; break; }
        wchar_t rel[MAX_PATH], target[MAX_PATH * 2];
        MultiByteToWideChar(CP_UTF8, 0, st.m_filename, -1, rel, MAX_PATH);
        for (wchar_t *p = rel; *p; p++) if (*p == L'/') *p = L'\\';
        swprintf(target, MAX_PATH * 2, L"%ls\\%ls", staging, rel);
        size_t len = wcslen(target);
        if (st.m_is_directory) {
            if (len && target[len - 1] == L'\\') target[len - 1] = 0;
            make_dirs(target);
        } else {
            wchar_t *slash = wcsrchr(target, L'\\');
            *slash = 0;
            make_dirs(target);
            *slash = L'\\';
            HANDLE h = CreateFileW(target, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
            if (h == INVALID_HANDLE_VALUE) { fail(target, GetLastError()); ok = 0; break; }
            ok = mz_zip_reader_extract_to_callback(&zip, i, write_cb, h, 0);
            CloseHandle(h);
            if (!ok) fail(L"Cannot write the files of DJSync (drive full?)", GetLastError());
        }
        SendMessageW(g_bar, PBM_SETPOS, i + 1, 0);
        pump();
    }
    mz_zip_reader_end(&zip);
    fclose(f);
    if (!ok) { remove_tree(staging); return 0; }

    /* version, puis remplacement : tout .djsync sauf data (anciennes versions, ancienne disposition) */
    wchar_t stamp[MAX_PATH * 2];
    swprintf(stamp, MAX_PATH * 2, L"%ls\\VERSION.txt", staging);
    HANDLE h = CreateFileW(stamp, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    DWORD n;
    if (h != INVALID_HANDLE_VALUE) { WriteFile(h, version, (DWORD)strlen(version), &n, NULL); CloseHandle(h); }

    wchar_t pattern[MAX_PATH * 2];
    swprintf(pattern, MAX_PATH * 2, L"%ls\\*", base);
    WIN32_FIND_DATAW fd;
    HANDLE fh = FindFirstFileW(pattern, &fd);
    if (fh != INVALID_HANDLE_VALUE) {
        do {
            if (!wcscmp(fd.cFileName, L".") || !wcscmp(fd.cFileName, L"..") || !_wcsicmp(fd.cFileName, L"data")
                || !_wcsicmp(fd.cFileName, L"app.new")) continue;
            wchar_t child[MAX_PATH * 2];
            swprintf(child, MAX_PATH * 2, L"%ls\\%ls", base, fd.cFileName);
            if (fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) remove_tree(child);
            else { SetFileAttributesW(child, FILE_ATTRIBUTE_NORMAL); DeleteFileW(child); }
        } while (FindNextFileW(fh, &fd));
        FindClose(fh);
    }
    if (GetFileAttributesW(app) != INVALID_FILE_ATTRIBUTES || !MoveFileExW(staging, app, 0)) {
        fail(L"An older DJSync is still open: close it, then start DJSync again", GetLastError());
        return 0;
    }
    (void)data;
    return 1;
}

/* ------------------------------------------------------------------- lancement */
int WINAPI wWinMain(HINSTANCE inst, HINSTANCE prev, LPWSTR args, int show) {
    (void)inst; (void)prev; (void)show;
    wchar_t self[MAX_PATH * 2], dir[MAX_PATH * 2], base[MAX_PATH * 2], exe[MAX_PATH * 2], stamp[MAX_PATH * 2];
    DWORD len = GetModuleFileNameW(NULL, self, MAX_PATH * 2);
    if (!len || len >= MAX_PATH * 2) { fail(L"Path too long", 0); return 1; }
    wcscpy(dir, self);
    *wcsrchr(dir, L'\\') = 0;
    swprintf(base, MAX_PATH * 2, L"%ls\\%ls", dir, CONTENTS);
    swprintf(exe, MAX_PATH * 2, L"%ls\\app\\DJSync.exe", base);
    swprintf(stamp, MAX_PATH * 2, L"%ls\\app\\VERSION.txt", base);

    /* bloc de fin : normalement les 56 derniers octets ; un exe signé (Authenticode) a ensuite sa
       signature en fin de fichier, on le cherche donc dans les 64 derniers Ko */
    HANDLE h = CreateFileW(self, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
    if (h == INVALID_HANDLE_VALUE) { fail(L"Cannot read DJSync.exe", GetLastError()); return 1; }
    LARGE_INTEGER fsize;
    GetFileSizeEx(h, &fsize);
    DWORD tail_len = fsize.QuadPart < 65536 ? (DWORD)fsize.QuadPart : 65536;
    unsigned char *tail = (unsigned char *)HeapAlloc(GetProcessHeap(), 0, tail_len);
    LARGE_INTEGER pos;
    pos.QuadPart = fsize.QuadPart - tail_len;
    DWORD got = 0;
    SetFilePointerEx(h, pos, NULL, FILE_BEGIN);
    ReadFile(h, tail, tail_len, &got, NULL);
    CloseHandle(h);
    uint64_t start = 0, size = 0;
    char version[33] = {0};
    int found = 0;
    for (long i = (long)got - TRAILER_SIZE; i >= 0 && !found; i--) {
        if (memcmp(tail + i, MAGIC, 8)) continue;
        memcpy(&start, tail + i + 8, 8);
        memcpy(&size, tail + i + 16, 8);
        if (start + size == (uint64_t)(pos.QuadPart + i)) {       /* le zip finit juste avant le bloc */
            memcpy(version, tail + i + 24, 32);
            found = 1;
        }
    }
    HeapFree(GetProcessHeap(), 0, tail);
    if (!found) { fail(L"DJSync.exe is incomplete: download it again", 0); return 1; }

    char current[64] = {0};
    int ready = GetFileAttributesW(exe) != INVALID_FILE_ATTRIBUTES && read_text(stamp, current, sizeof(current))
                && !strcmp(current, version);
    if (!ready) {
        if (!extract(self, start, size, base, version)) return 1;
        if (g_win) DestroyWindow(g_win);
    }
    SetFileAttributesW(base, FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM | FILE_ATTRIBUTE_DIRECTORY);

    SetEnvironmentVariableW(L"DJSYNC_APP_DIR", dir);
    SetEnvironmentVariableW(L"DJSYNC_LAUNCHER", self);           /* V1.2.0 : « Retirer DJSync de cette clé » */
    wchar_t cmd[32768];
    swprintf(cmd, 32768, L"\"%ls\" %ls", exe, args ? args : L"");
    STARTUPINFOW si = {sizeof(si)};
    PROCESS_INFORMATION pi;
    if (!CreateProcessW(exe, cmd, NULL, NULL, FALSE, 0, NULL, dir, &si, &pi)) {
        fail(L"Cannot start DJSync", GetLastError());
        return 1;
    }
    DWORD code = 0;
    wchar_t flag[8];
    if (GetEnvironmentVariableW(L"DJSYNC_SELFTEST", flag, 8)) {   /* CI : attendre le résultat de l'autotest */
        WaitForSingleObject(pi.hProcess, INFINITE);
        GetExitCodeProcess(pi.hProcess, &code);
    }
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return (int)code;
}
