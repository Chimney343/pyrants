#include "engine.h"
#include "moves.h"
#include "helpers.h"
#include "phases.h"
#include "rules.h"
#include "generic_runtime.h"
#include <stdio.h>
#include <assert.h>
#include <string.h>

static GameDefinition *g_def = NULL;

static void setup(void) {
    Arena *arena = arena_create(2 * 1024 * 1024);
    g_def = engine_load_definition(
        "../data/cards/catalog.json",
        "../data/boards/tyrants_of_the_underdark.json",
        "../data/decks/base_setup.json",
        arena
    );
    if (!g_def || g_def->catalog.card_count == 0) {
        g_def = engine_load_definition(
            "data/cards/catalog.json",
            "data/boards/tyrants_of_the_underdark.json",
            "data/decks/base_setup.json",
            arena
        );
    }
    assert(g_def);
    register_default_effects();
}

int main(void) {
    setup();
    printf("Death Tyrant C engine test\n");

    const char *pids[] = {"p1", "p2", "p3", "p4"};
    GameState *gs = engine_create_game_definition(g_def, pids, 4, 4);
    assert(gs);

    /* Advance past setup */
    Move legal[256];
    int n;
    GameState *tmp;
    int rounds = 0;
    while (gs->phase == PHASE_SETUP && rounds < 400) {
        n = engine_legal_moves(gs, legal, 256);
        if (n == 0) break;
        tmp = engine_apply(gs, &legal[0]);
        engine_destroy(gs);
        gs = tmp;
        rounds++;
    }
    printf("  Phase after setup: %d\n", gs->phase);

    /* Advance to p2's turn in main phase */
    while (strcmp(intern_str(gs->current_player_id), "p2") != 0 || gs->phase != PHASE_MAIN) {
        n = engine_legal_moves(gs, legal, 256);
        if (n == 0) break;
        int played = 0;
        for (int i = 0; i < n; i++) {
            if (legal[i].type == MOVE_END_MAIN_PHASE) {
                tmp = engine_apply(gs, &legal[i]);
                engine_destroy(gs);
                gs = tmp;
                played = 1;
                break;
            }
            if (strcmp(intern_str(gs->current_player_id), "p2") == 0
                && legal[i].type == MOVE_PLAY_CARD) {
                tmp = engine_apply(gs, &legal[i]);
                engine_destroy(gs);
                gs = tmp;
                played = 1;
                break;
            }
        }
        if (!played) {
            n = engine_legal_moves(gs, legal, 256);
            tmp = engine_apply(gs, &legal[0]);
            engine_destroy(gs);
            gs = tmp;
        }
    }

    printf("  Current player: %s, phase: %d\n",
           intern_str(gs->current_player_id), gs->phase);

    /* Set up test: p2 has death_tyrant, spy at buiyrandyn, enemy troops there */
    Sym p2_id = intern("p2");
    Sym dt_id = intern("death_tyrant");
    Sym buy_id = intern("site_buiyrandyn");

    int p2_idx = -1;
    for (int i = 0; i < gs->player_count; i++)
        if (gs->players[i].player_id == p2_id) { p2_idx = i; break; }
    assert(p2_idx >= 0);

    /* Replace hand with death_tyrant */
    PlayerState *ps = cow_player(gs, p2_id);
    ps->hand[0] = dt_id;
    ps->hand_count = 1;
    ps->deck_count = 0;
    ps->discard_pile_count = 0;
    ps->played_cards_count = 0;

    /* Ensure p2 has spy at buiyrandyn */
    int buy_ni = -1;
    for (int i = 0; i < gs->node_count; i++)
        if (gs->nodes[i].node_id == buy_id) { buy_ni = i; break; }
    assert(buy_ni >= 0);
    NodeState *bns = cow_node(gs, buy_id);
    int has_spy = 0;
    for (int s = 0; s < bns->spy_count; s++)
        if (bns->spies[s] == p2_id) { has_spy = 1; break; }
    if (!has_spy && bns->spy_count < MAX_SPY_SLOTS)
        bns->spies[bns->spy_count++] = p2_id;

    /* Set enemy troops at buiyrandyn */
    bns->troop_slots[0] = intern("p3");
    bns->troop_slots[1] = intern("p3");
    bns->troop_slots[2] = intern("p4");
    bns->troop_slot_count = 3;

    int inf_before = gs->resource_pool.influence;
    printf("  Influence before: %d, troops at buiyrandyn: [%s, %s, %s]\n",
           inf_before,
           intern_str(bns->troop_slots[0] ? bns->troop_slots[0] : 0),
           intern_str(bns->troop_slots[1] ? bns->troop_slots[1] : 0),
           intern_str(bns->troop_slots[2] ? bns->troop_slots[2] : 0));

    /* Play Death Tyrant using engine_apply */
    Sym in_hand = ps->hand[0];
    printf("  Card in hand index 0: %s\n", intern_str(in_hand));
    Move play_move = make_play_card_move(in_hand, 0);
    tmp = engine_apply(gs, &play_move);
    if (!tmp) { printf("  FAIL: engine_apply returned NULL for play_card\n"); engine_destroy(gs); return 1; }
    engine_destroy(gs);
    gs = tmp;
    printf("  After play card, pending: %s\n",
           gs->pending_generic ? "yes" : "no");

    if (!gs->pending_generic) {
        printf("  FAIL: no pending_generic after playing Death Tyrant\n");
        engine_destroy(gs);
        return 1;
    }

    /* Check what actions are pending */
    PendingGenericChoiceState *p = gs->pending_generic;
    printf("  Pending exec_kind=%d, actions=%d, index=%d, awaiting=%d\n",
           p->exec_kind, p->current_action_count, p->next_action_index, p->awaiting_option);

    for (int i = 0; i < p->current_action_count; i++) {
        const char *op = intern_str(p->current_actions[i].op);
        const char *aid = intern_str(p->current_actions[i].action_id);
        int opt = p->current_actions[i].optional;
        int meta = p->current_actions[i].metadata_count;
        printf("    action[%d]: op=%s action_id=%s optional=%d metadata_count=%d\n",
               i, op ? op : "NULL", aid ? aid : "NULL", opt, meta);
        for (int j = 0; j < meta; j++) {
            const char *mk = intern_str(p->current_actions[i].metadata[j].key);
            const char *mv = intern_str(p->current_actions[i].metadata[j].value);
            printf("      metadata[%d]: %s = %s\n", j, mk ? mk : "NULL", mv ? mv : "NULL");
        }
    }

    /* Get legal moves for the pending choice */
    n = engine_legal_moves(gs, legal, 256);
    printf("  Legal moves after play: %d\n", n);

    int dt_moves = 0;
    for (int i = 0; i < n; i++) {
        if (legal[i].type == MOVE_RESOLVE_GENERIC) {
            dt_moves++;
            Sym aid = legal[i].data.resolve_generic.action_id;
            Sym tid = legal[i].data.resolve_generic.target_id;
            printf("    resolve_generic: action_id=%s target_id=%s\n",
                   intern_str(aid) ? intern_str(aid) : "NULL",
                   intern_str(tid) ? intern_str(tid) : "NULL");
        }
    }
    if (dt_moves == 0) {
        printf("  FAIL: no resolve_generic moves\n");
        engine_destroy(gs);
        return 1;
    }

    /* Apply first resolve_generic move (should be site selection) */
    int applied = 0;
    for (int i = 0; i < n; i++) {
        if (legal[i].type == MOVE_RESOLVE_GENERIC) {
            Sym aid = legal[i].data.resolve_generic.action_id;
            if (aid != SYM_NULL) {
                printf("  Applying site selection: %s\n", intern_str(aid));
                tmp = engine_apply(gs, &legal[i]);
                if (tmp) {
                    engine_destroy(gs);
                    gs = tmp;
                    applied = 1;
                } else {
                    printf("  FAIL: engine_apply returned NULL for site selection\n");
                    engine_destroy(gs);
                    return 1;
                }
                break;
            }
        }
    }
    if (!applied) {
        printf("  FAIL: could not apply site selection\n");
        engine_destroy(gs);
        return 1;
    }

    printf("  After site selection, pending: %s\n",
           gs->pending_generic ? "yes" : "no");

    if (!gs->pending_generic) {
        printf("  FAIL: no pending after site selection\n");
        engine_destroy(gs);
        return 1;
    }

    p = gs->pending_generic;
    printf("  Next action index: %d\n", p->next_action_index);
    if (p->next_action_index < p->current_action_count) {
        const char *op = intern_str(p->current_actions[p->next_action_index].op);
        printf("  Next action op: %s\n", op ? op : "NULL");
    }

    /* Get assassinate moves */
    n = engine_legal_moves(gs, legal, 256);
    printf("  Legal moves after site selection: %d\n", n);
    for (int i = 0; i < n; i++) {
        if (legal[i].type == MOVE_RESOLVE_GENERIC) {
            Sym aid = legal[i].data.resolve_generic.action_id;
            Sym tid = legal[i].data.resolve_generic.target_id;
            printf("    move: action_id=%s target_id=%s\n",
                   aid == SYM_NULL ? "NULL(skip)" : (intern_str(aid) ? intern_str(aid) : "?"),
                   tid == SYM_NULL ? "NULL" : (intern_str(tid) ? intern_str(tid) : "?"));
        }
    }

    /* Apply first non-skip assassinate move */
    applied = 0;
    for (int i = 0; i < n; i++) {
        if (legal[i].type == MOVE_RESOLVE_GENERIC
            && legal[i].data.resolve_generic.action_id != SYM_NULL
            && legal[i].data.resolve_generic.target_id != SYM_NULL) {
            Sym aid = legal[i].data.resolve_generic.action_id;
            const char *ts = intern_str(legal[i].data.resolve_generic.target_id);
            printf("  Applying assassinate: node=%s slot=%s\n",
                   intern_str(aid), ts ? ts : "?");
            tmp = engine_apply(gs, &legal[i]);
            if (tmp) {
                engine_destroy(gs);
                gs = tmp;
                applied = 1;
                break;
            } else {
                printf("  FAIL: engine_apply returned NULL for assassinate\n");
                engine_destroy(gs);
                return 1;
            }
        }
    }
    if (!applied) {
        printf("  No assassinate moves to apply (may auto-resolve)\n");
    }

    /* Check result */
    bns = cow_node(gs, buy_id);
    printf("  Troops after: [%s, %s, %s]\n",
           bns->troop_slots[0] ? intern_str(bns->troop_slots[0]) : "None",
           bns->troop_slots[1] ? intern_str(bns->troop_slots[1]) : "None",
           bns->troop_slots[2] ? intern_str(bns->troop_slots[2]) : "None");
    printf("  Influence after: %d (was %d)\n", gs->resource_pool.influence, inf_before);

    /* Skip remaining or auto-resolve */
    while (gs->pending_generic) {
        n = engine_legal_moves(gs, legal, 256);
        if (n == 0) break;
        /* Apply skip moves */
        int skipped = 0;
        for (int i = 0; i < n; i++) {
            if (legal[i].type == MOVE_RESOLVE_GENERIC
                && legal[i].data.resolve_generic.action_id == SYM_NULL) {
                tmp = engine_apply(gs, &legal[i]);
                engine_destroy(gs);
                gs = tmp;
                skipped = 1;
                break;
            }
        }
        if (!skipped) break;
    }

    bns = cow_node(gs, buy_id);
    printf("  Final troops: [%s, %s, %s]\n",
           bns->troop_slots[0] ? intern_str(bns->troop_slots[0]) : "None",
           bns->troop_slots[1] ? intern_str(bns->troop_slots[1]) : "None",
           bns->troop_slots[2] ? intern_str(bns->troop_slots[2]) : "None");
    printf("  Final influence: %d (delta=%d)\n", gs->resource_pool.influence,
           gs->resource_pool.influence - inf_before);
    printf("  Pending generic: %s\n", gs->pending_generic ? "yes" : "no");

    engine_destroy(gs);
    printf("DONE\n");
    return 0;
}
