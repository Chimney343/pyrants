#include "arena.h"
#include <assert.h>
#include <stdlib.h>
#include <string.h>

#define DEFAULT_BLOCK_SIZE (64 * 1024)
#define ALIGN(size) (((size) + 7) & ~7)

/* Hot-path arena recycling. engine_clone() creates a 512 KiB arena per rollout
 * step and destroys the previous one; parking the destroyed arena here lets
 * the next arena_create() reuse it instead of doing a 512 KiB malloc/free. See
 * arena.h for the contract. The pool is thread-local so a threaded host cannot
 * hand the same arena to two live states. */
#if defined(_MSC_VER)
#define ARENA_THREAD_LOCAL __declspec(thread)
#else
#define ARENA_THREAD_LOCAL _Thread_local
#endif
static ARENA_THREAD_LOCAL Arena *arena_pool[ARENA_POOL_CAP];
static ARENA_THREAD_LOCAL size_t arena_pool_size = 0;

size_t arena_pool_count(void) {
    return arena_pool_size;
}

static void arena_free(Arena *arena) {
    ArenaBlock *block = arena->head;
    while (block) {
        ArenaBlock *next = block->next;
        free(block->memory);
        free(block);
        block = next;
    }
    free(arena);
}

void arena_pool_clear(void) {
    while (arena_pool_size > 0) {
        arena_pool_size--;
        arena_free(arena_pool[arena_pool_size]);
    }
}

Arena *arena_create(size_t initial_capacity) {
    if (initial_capacity == 0) initial_capacity = DEFAULT_BLOCK_SIZE;

    if (arena_pool_size > 0) {
        Arena *reused = arena_pool[arena_pool_size - 1];
        if (reused->head && reused->head->capacity >= initial_capacity) {
            arena_pool_size--;
            /* The pool admits single-block arenas only (see arena_destroy), so
             * resetting is just restarting the bump pointer at the block base. */
            ArenaBlock *head = reused->head;
            assert(head->next == NULL);
            head->used = 0;
            reused->total_allocated = head->capacity;
            return reused;
        }
    }

    Arena *arena = (Arena *)malloc(sizeof(Arena));
    if (!arena) return NULL;
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
    /* Pool only the exact hot-path shape: a single block of
     * ARENA_POOL_BLOCK_SIZE. A grown arena (head->next) or a definition/test
     * sized block is freed as before so the pool cannot balloon. */
    if (arena_pool_size < ARENA_POOL_CAP && arena->head &&
        arena->head->next == NULL &&
        arena->head->capacity == ARENA_POOL_BLOCK_SIZE) {
        arena_pool[arena_pool_size++] = arena;
        return;
    }
    arena_free(arena);
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
