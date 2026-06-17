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

Arena *arena_create(size_t initial_capacity);
void   arena_destroy(Arena *arena);
void  *arena_alloc(Arena *arena, size_t size);
void  *arena_calloc(Arena *arena, size_t count, size_t size);
char  *arena_strdup(Arena *arena, const char *s);
void   arena_reset(Arena *arena);
Arena *arena_clone(const Arena *src);

#endif
