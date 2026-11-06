#ifndef ENGINE_PENDING_H
#define ENGINE_PENDING_H

#include "arena.h"
#include "state.h"

#include <stddef.h>
#include <stdint.h>

struct cJSON;

/* One owner for the engine's pending decisions. The first migration covers
 * pending_immediate/pending_eot; pending_ability and pending_generic are
 * exposed through the same record now and move behind the module's storage
 * later. PENDING_CHANCE is reserved for ADR-0002's parked F-003 work. */
typedef enum {
    PENDING_NONE = 0,
    PENDING_ABILITY,
    PENDING_IMMEDIATE,
    PENDING_EOT,
    PENDING_GENERIC,
    PENDING_CHANCE,  /* reserved; not built */
} PendingKind;

typedef struct {
    PendingKind kind;
    int priority;
    int count;
} PendingDecision;

PendingDecision pending_peek(const GameState *state);
int pending_priority(PendingKind kind);
const char *pending_kind_name(PendingKind kind);

int pending_promotion_count(const GameState *state, PendingKind kind);
const PendingPromotionState *pending_promotion_at(const GameState *state,
                                                   PendingKind kind, int index);
PendingPromotionState *pending_promotion_mut(GameState *state,
                                              PendingKind kind, int index);
int pending_promotion_push(GameState *state, PendingKind kind,
                           const PendingPromotionState *promotion);
int pending_promotion_pop(GameState *state, PendingKind kind);
void pending_promotion_set_count(GameState *state, PendingKind kind, int count);

void pending_clone(GameState *dst, const GameState *src, Arena *arena);
uint64_t pending_hash(const GameState *state);
void pending_describe(const GameState *state, char *buf, size_t cap);

int pending_save_json(struct cJSON *state_obj, const GameState *state);
int pending_load_json(const struct cJSON *state_obj, GameState *state);

#endif
