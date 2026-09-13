#ifndef ENGINE_ARENA_H
#define ENGINE_ARENA_H

#include <stddef.h>
#include <stdint.h>

typedef struct ArenaBlock {
    char *memory;
    size_t capacity;
    size_t used;
    struct ArenaBlock *next;
} ArenaBlock;

typedef struct {
    ArenaBlock *head;
    size_t total_allocated;
} Arena;

/* Hot-path arena recycling. engine_clone() creates a 512 KiB arena per
 * rollout step and destroys the previous one, so the hot loop pays a 512 KiB
 * malloc/free pair every step. arena_destroy() parks destroyed arenas of
 * exactly ARENA_POOL_BLOCK_SIZE (single block) in a small per-process pool and
 * arena_create() hands the most recent one straight back, reset. Larger
 * definition/test arenas and grown multi-block arenas are freed as before.
 *
 * Per-thread: each thread recycles its own hot-path arenas, so a threaded host
 * cannot hand one arena to two live states. arena_pool_clear() releases the
 * calling thread's pooled memory (test isolation / long-lived host cleanup);
 * arena_pool_count() is a diagnostic. */
#define ARENA_POOL_CAP 64
#define ARENA_POOL_BLOCK_SIZE (512 * 1024)

Arena *arena_create(size_t initial_capacity);
void   arena_destroy(Arena *arena);
void  *arena_alloc(Arena *arena, size_t size);
void  *arena_calloc(Arena *arena, size_t count, size_t size);
char  *arena_strdup(Arena *arena, const char *s);
void   arena_reset(Arena *arena);
Arena *arena_clone(const Arena *src);
size_t arena_pool_count(void);
void   arena_pool_clear(void);

#endif
