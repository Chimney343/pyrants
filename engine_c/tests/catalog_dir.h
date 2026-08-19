#ifndef ENGINE_CATALOG_DIR_H
#define ENGINE_CATALOG_DIR_H

/* Header-only TEST helper: assemble the whole card catalog from per-card
 * JSON files in a directory. This is test-only code — it performs
 * platform-specific directory iteration, which AGENTS.md forbids in the pure
 * engine library sources. Production code assembles the catalog JSON in
 * Python and passes it to engine_load_definition_json instead. */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cJSON.h"
#include "loader.h"

#ifdef _WIN32
#include <windows.h>
#else
#include <dirent.h>
#endif

#define CATDIR_MAX_FILES 512

static char *catdir_strdup(const char *s) {
    size_t n = strlen(s) + 1;
    char *copy = (char *)malloc(n);
    if (!copy) return NULL;
    memcpy(copy, s, n);
    return copy;
}

static int catdir_cmp_str(const void *a, const void *b) {
    const char *const *sa = (const char *const *)a;
    const char *const *sb = (const char *const *)b;
    return strcmp(*sa, *sb);
}

static char *catdir_read_file(const char *path) {
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    if (fseek(f, 0, SEEK_END) != 0) { fclose(f); return NULL; }
    long sz = ftell(f);
    if (sz < 0) { fclose(f); return NULL; }
    if (fseek(f, 0, SEEK_SET) != 0) { fclose(f); return NULL; }
    char *buf = (char *)malloc((size_t)sz + 1);
    if (!buf) { fclose(f); return NULL; }
    size_t n = fread(buf, 1, (size_t)sz, f);
    fclose(f);
    buf[n] = '\0';
    return buf;
}

typedef struct {
    char *data;
    size_t len;
    size_t cap;
} CatdirBuf;

static void catdir_buf_init(CatdirBuf *b) {
    b->cap = 64 * 1024;
    b->data = (char *)malloc(b->cap);
    b->len = 0;
    if (b->data) b->data[0] = '\0';
}

static int catdir_buf_append(CatdirBuf *b, const char *s, size_t n) {
    if (!b->data) return -1;
    if (b->len + n + 1 > b->cap) {
        size_t newcap = b->cap;
        while (newcap < b->len + n + 1) {
            if (newcap > ((size_t)-1) / 2) return -1;
            newcap *= 2;
        }
        char *nd = (char *)realloc(b->data, newcap);
        if (!nd) return -1;
        b->data = nd;
        b->cap = newcap;
    }
    memcpy(b->data + b->len, s, n);
    b->len += n;
    b->data[b->len] = '\0';
    return 0;
}

/* Assemble the whole card catalog from per-card JSON files in `cards_dir`.
 * Returns a malloc'd JSON string {"catalog_id": "...", "cards": [...]} that
 * the caller must free, or NULL if `cards_dir` has no manifest.json.
 *
 * Card-file discrimination rule (matches the Python assembler): among *.json
 * files, a card is a JSON object with a string `card_id` key. Everything else
 * is skipped (manifest.json, cards_OCR.json, a legacy combined catalog.json). */
static char *test_load_catalog_json(const char *cards_dir) {
    char manifest_path[1024];
    snprintf(manifest_path, sizeof(manifest_path), "%s/manifest.json", cards_dir);
    char *manifest_text = catdir_read_file(manifest_path);
    if (!manifest_text) return NULL;
    cJSON *manifest = cJSON_Parse(manifest_text);
    free(manifest_text);
    if (!manifest) return NULL;

    const char *catalog_id = "base_catalog";
    cJSON *cid_item = cJSON_GetObjectItem(manifest, "catalog_id");
    if (cid_item && cJSON_IsString(cid_item)) catalog_id = cid_item->valuestring;

    char *filenames[CATDIR_MAX_FILES];
    int count = 0;

#ifdef _WIN32
    char pattern[1024];
    snprintf(pattern, sizeof(pattern), "%s/*.json", cards_dir);
    WIN32_FIND_DATAA fd;
    HANDLE hFind = FindFirstFileA(pattern, &fd);
    if (hFind != INVALID_HANDLE_VALUE) {
        do {
            if (!(fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) && count < CATDIR_MAX_FILES) {
                filenames[count++] = catdir_strdup(fd.cFileName);
            }
        } while (FindNextFileA(hFind, &fd));
        FindClose(hFind);
    }
#else
    DIR *dir = opendir(cards_dir);
    if (!dir) {
        cJSON_Delete(manifest);
        return NULL;
    }
    struct dirent *entry;
    while ((entry = readdir(dir)) != NULL) {
        const char *name = entry->d_name;
        size_t nl = strlen(name);
        if (nl > 5 && strcmp(name + nl - 5, ".json") == 0 && count < CATDIR_MAX_FILES) {
            filenames[count++] = catdir_strdup(name);
        }
    }
    closedir(dir);
#endif

    qsort(filenames, (size_t)count, sizeof(char *), catdir_cmp_str);

    CatdirBuf out;
    catdir_buf_init(&out);

    char prefix[2048];
    int plen = snprintf(prefix, sizeof(prefix), "{\"catalog_id\": \"%s\", \"cards\": [", catalog_id);
    if (plen < 0) plen = 0;
    catdir_buf_append(&out, prefix, (size_t)plen);

    int card_count = 0;
    for (int i = 0; i < count; i++) {
        char path[2048];
        snprintf(path, sizeof(path), "%s/%s", cards_dir, filenames[i]);
        char *body = catdir_read_file(path);
        if (!body) continue;
        cJSON *card = cJSON_Parse(body);
        int is_card = 0;
        if (card && cJSON_IsObject(card) && cJSON_GetObjectItem(card, "card_id")) {
            is_card = 1;
        }
        if (card) cJSON_Delete(card);
        if (is_card) {
            size_t blen = strlen(body);
            while (blen > 0 &&
                   (body[blen - 1] == '\n' || body[blen - 1] == '\r' ||
                    body[blen - 1] == ' ' || body[blen - 1] == '\t')) {
                body[--blen] = '\0';
            }
            if (card_count > 0) catdir_buf_append(&out, ",", 1);
            catdir_buf_append(&out, body, blen);
            card_count++;
        }
        free(body);
    }

    catdir_buf_append(&out, "]}", 2);

    for (int i = 0; i < count; i++) free(filenames[i]);
    cJSON_Delete(manifest);

    if (!out.data) return NULL;
    return out.data;
}

/* Assemble the catalog trying both "../data" and "data" path prefixes so it
 * works whether the test runs from engine_c/ (compile.bat) or the repo root
 * (just test-c). Returns a malloc'd string the caller frees, or NULL. */
static char *test_load_catalog_json_both(void) {
    char *json = test_load_catalog_json("../data/cards");
    if (!json) json = test_load_catalog_json("data/cards");
    return json;
}

/* Pick board/setup paths that resolve from the current working directory.
 * Used when serializing a state whose embedded paths will later be reloaded. */
static void test_board_setup_paths(const char **out_board, const char **out_setup) {
    static const char *board_up = "../data/boards/tyrants_of_the_underdark.json";
    static const char *setup_up = "../data/decks/base_setup.json";
    static const char *board_rel = "data/boards/tyrants_of_the_underdark.json";
    static const char *setup_rel = "data/decks/base_setup.json";
    FILE *f = fopen(board_up, "rb");
    if (f) {
        fclose(f);
        *out_board = board_up;
        *out_setup = setup_up;
    } else {
        *out_board = board_rel;
        *out_setup = setup_rel;
    }
}

/* Load a game definition from the per-card directory plus the default
 * board/setup files. Tries both "../data" and "data" path prefixes so it
 * works whether the test runs from engine_c/ (compile.bat) or the repo root
 * (just test-c). Returns NULL only if no catalog manifest was found. */
static GameDefinition *test_load_definition(Arena *arena) {
    char *json = test_load_catalog_json_both();
    if (!json) return NULL;
    const char *board_path;
    const char *setup_path;
    test_board_setup_paths(&board_path, &setup_path);
    GameDefinition *def = engine_load_definition_json(json, board_path, setup_path, arena);
    free(json);
    return def;
}

#endif
