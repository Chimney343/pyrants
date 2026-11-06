/* visibility.h - what one player can know about a game state.
 *
 * One rule table answers "what does player p know?". For each card zone and
 * each relation between the zone's owner and the observer it says whether the
 * observer sees the cards or only how many there are, and whether
 * determinization resamples the zone. Everything that depends on the answer
 * reads that table:
 *
 *   engine_player_view_json  the observer's view as JSON: the OpenSpiel
 *                            observation string and the NN's observed features.
 *   engine_infostate_hash    the IS-MCTS tree key: a fingerprint of the same
 *                            view, equal exactly when the views are equal.
 *
 * The view is produced by one canonical walk over the state, so every consumer
 * sees the same fields in the same order. See docs/adr/0007.
 */
#ifndef VISIBILITY_H
#define VISIBILITY_H

#include "state.h"
#include <stddef.h>
#include <stdint.h>

/* What an observer sees of one zone. Every zone's size is public. */
typedef enum { VIS_COUNT = 0, VIS_CARDS = 1 } Vis;

/* Card zones the rule covers. The first six belong to a player; the rest are
 * shared. The board is always public and is not a row. */
typedef enum {
    VZ_HAND = 0,
    VZ_DECK,
    VZ_DISCARD,
    VZ_PLAYED,
    VZ_INNER_CIRCLE,
    VZ_TROPHY_HALL,
    VZ_MARKET_ROW,
    VZ_MARKET_DECK,
    VZ_MARKET_DISCARD,
    VZ_DEVOUR,
    VZ_ZONE_COUNT
} VisZone;

#define VZ_PLAYER_ZONE_COUNT 6

/* The observer's relation to the owner of a player zone. Shared zones read the
 * same in both columns. */
typedef enum { VIS_SELF = 0, VIS_OPPONENT = 1 } VisRelation;

typedef struct {
    Vis vis;      /* what the observer sees */
    int resample; /* 1: determinization reshuffles the zone */
} VisRule;

/* The rule for one zone and relation. Out-of-range arguments return
 * {VIS_COUNT, 0}. */
VisRule vis_rule(VisZone zone, VisRelation rel);

/* Write player_id's view of state as JSON into buf (at most cap bytes,
 * NUL-terminated when cap > 0). Returns the length the full view needs,
 * excluding the NUL; a return >= cap means buf was too small. Returns 0 and
 * writes an empty string when state is NULL or player_id is not a player.
 * The bytes equal json.dumps(view, sort_keys=True) of the Python view this
 * function replaced (F-013 G1 pins them). */
size_t engine_player_view_json(const GameState *state, Sym player_id, char *buf, size_t cap);

/* player_id's tree key: a 128-bit fingerprint of the same walk that renders
 * the view, so two states share a key exactly when they share a view (up to
 * hash collisions). Values are only comparable inside one process. Writes
 * {0, 0} when state is NULL or player_id is not a player. */
void engine_infostate_hash(const GameState *state, Sym player_id, uint64_t out[2]);

#endif
