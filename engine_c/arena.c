#include "arena.h"
#include <stdlib.h>
#include <string.h>

#define DEFAULT_BLOCK_SIZE (64 * 1024)
#define ALIGN(size) (((size) + 7) & ~7)

Arena *arena_create(size_t initial_capacity) {
    Arena *arena = (Arena *)malloc(sizeof(Arena));
    if (!arena) return NULL;
    if (initial_capacity == 0) initial_capacity = DEFAULT_BLOCK_SIZE;
    ArenaBlock *block = (ArenaBlock *)malloc(sizeof(ArenaBlock));
    if (!block) { free(arena); return NULL; }
    block->memory = (char *)malloc(initial_capacity);
    if (!block->memory) { free(block); free(arena); return NULL; }
    block->capacity = initial_capacity;
    block->used = 0;
    block->next = NULL;
    arena->head = block;
    arena->total_allocated = initial_capacity;
    return arena;
}

void arena_destroy(Arena *arena) {
    if (!arena) return;
    ArenaBlock *block = arena->head;
    while (block) {
        ArenaBlock *next = block->next;
        free(block->memory);
        free(block);
        block = next;
    }
    free(arena);
}

static ArenaBlock *arena_new_block(size_t min_size) {
    size_t size = min_size > DEFAULT_BLOCK_SIZE ? min_size : DEFAULT_BLOCK_SIZE;
    ArenaBlock *block = (ArenaBlock *)malloc(sizeof(ArenaBlock));
    if (!block) return NULL;
    block->memory = (char *)malloc(size);
    if (!block->memory) { free(block); return NULL; }
    block->capacity = size;
    block->used = 0;
    block->next = NULL;
    return block;
}

void *arena_alloc(Arena *arena, size_t size) {
    if (!arena || size == 0) return NULL;
    size = ALIGN(size);
    ArenaBlock *block = arena->head;
    if (!block) { block = arena_new_block(size); if (!block) return NULL; arena->head = block; arena->total_allocated = block->capacity; }
    if (block->used + size > block->capacity) {
        ArenaBlock *new_block = arena_new_block(size);
        if (!new_block) return NULL;
        new_block->next = block;
        arena->head = new_block;
        arena->total_allocated += new_block->capacity;
        block = new_block;
    }
    void *ptr = block->memory + block->used;
    block->used += size;
    return ptr;
}

void *arena_calloc(Arena *arena, size_t count, size_t size) {
    size_t total = count * size;
    void *ptr = arena_alloc(arena, total);
    if (ptr) memset(ptr, 0, total);
    return ptr;
}

char *arena_strdup(Arena *arena, const char *s) {
    if (!s) return NULL;
    size_t len = strlen(s) + 1;
    char *copy = (char *)arena_alloc(arena, len);
    if (copy) memcpy(copy, s, len);
    return copy;
}

void arena_reset(Arena *arena) {
    if (!arena) return;
    ArenaBlock *block = arena->head;
    if (block) block->used = 0;
    ArenaBlock *rest = block ? block->next : NULL;
    if (block) block->next = NULL;
    while (rest) {
        ArenaBlock *next = rest->next;
        free(rest->memory);
        free(rest);
        rest = next;
    }
}

Arena *arena_clone(const Arena *src) {
    if (!src) return NULL;
    Arena *dst = (Arena *)malloc(sizeof(Arena));
    if (!dst) return NULL;
    dst->head = NULL;
    dst->total_allocated = 0;
    ArenaBlock *prev = NULL;
    for (ArenaBlock *sb = src->head; sb; sb = sb->next) {
        ArenaBlock *db = (ArenaBlock *)malloc(sizeof(ArenaBlock));
        if (!db) { arena_destroy(dst); return NULL; }
        db->capacity = sb->capacity;
        db->used = sb->used;
        db->memory = (char *)malloc(sb->capacity);
        if (!db->memory) { free(db); arena_destroy(dst); return NULL; }
        memcpy(db->memory, sb->memory, sb->used);
        db->next = NULL;
        if (!dst->head) dst->head = db;
        if (prev) prev->next = db;
        prev = db;
        dst->total_allocated += sb->capacity;
    }
    return dst;
}
