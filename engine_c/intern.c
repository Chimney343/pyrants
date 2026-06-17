#include "intern.h"
#include <stdlib.h>
#include <string.h>

#define FNV_OFFSET 14695981039346656037ULL
#define FNV_PRIME  1099511628211ULL
#define DEFAULT_TABLE_SIZE 1024

typedef struct InternEntry {
    Sym         sym;
    char       *str;
    int         len;
    struct InternEntry *next;
} InternEntry;

static InternEntry **table = NULL;
static int           table_size = 0;
static int           entry_count = 0;
static Sym           next_sym = 1;
static const char  **sym_strs = NULL;
static int           sym_strs_cap = 0;

static uint64_t fnv1a(const char *s, int len) {
    uint64_t hash = FNV_OFFSET;
    for (int i = 0; i < len; i++) {
        hash ^= (unsigned char)s[i];
        hash *= FNV_PRIME;
    }
    return hash;
}

void intern_init(int capacity) {
    if (capacity <= 0) capacity = DEFAULT_TABLE_SIZE;
    table_size = capacity;
    table = (InternEntry **)calloc((size_t)table_size, sizeof(InternEntry *));
    sym_strs_cap = table_size;
    sym_strs = (const char **)calloc((size_t)sym_strs_cap, sizeof(const char *));
    entry_count = 0;
    next_sym = 1;
}

Sym intern_len(const char *s, int len) {
    if (!s || len <= 0) return SYM_NULL;
    if (!table) intern_init(0);
    uint64_t hash = fnv1a(s, len);
    int idx = (int)(hash % (uint64_t)table_size);
    for (InternEntry *e = table[idx]; e; e = e->next) {
        if (e->len == len && memcmp(e->str, s, (size_t)len) == 0) {
            return e->sym;
        }
    }
    InternEntry *entry = (InternEntry *)malloc(sizeof(InternEntry));
    entry->sym = next_sym++;
    if (entry->sym >= (Sym)sym_strs_cap) {
        int new_cap = sym_strs_cap * 2;
        sym_strs = (const char **)realloc(sym_strs, (size_t)new_cap * sizeof(const char *));
        for (int ci = sym_strs_cap; ci < new_cap; ci++) {
            sym_strs[ci] = NULL;
        }
        for (int bi = 0; bi < table_size; bi++) {
            for (InternEntry *pe = table[bi]; pe; pe = pe->next) {
                sym_strs[pe->sym] = pe->str;
            }
        }
        sym_strs_cap = new_cap;
    }
    entry->str = (char *)malloc((size_t)(len + 1));
    memcpy(entry->str, s, (size_t)len);
    entry->str[len] = '\0';
    sym_strs[entry->sym] = entry->str;
    entry->len = len;
    entry->next = table[idx];
    table[idx] = entry;
    entry_count++;
    return entry->sym;
}

Sym intern(const char *s) {
    if (!s) return SYM_NULL;
    return intern_len(s, (int)strlen(s));
}

const char *intern_str(Sym sym) {
    if (sym == SYM_NULL || sym >= (Sym)sym_strs_cap) return NULL;
    return sym_strs[sym];
}

void intern_destroy(void) {
    if (!table) return;
    for (int i = 0; i < table_size; i++) {
        InternEntry *e = table[i];
        while (e) {
            InternEntry *next = e->next;
            free(e->str);
            free(e);
            e = next;
        }
    }
    free(table);
    table = NULL;
    table_size = 0;
    entry_count = 0;
    next_sym = 1;
    free(sym_strs);
    sym_strs = NULL;
    sym_strs_cap = 0;
}

int intern_count(void) {
    return entry_count;
}
