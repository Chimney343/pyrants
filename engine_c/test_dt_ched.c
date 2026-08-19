#include "engine.h"
#include "moves.h"
#include "helpers.h"
#include "phases.h"
#include "rules.h"
#include "generic_runtime.h"
#include "tests/catalog_dir.h"
#include <stdio.h>
#include <assert.h>
#include <string.h>

static GameDefinition *g_def = NULL;

static void setup(void) {
    Arena *arena = arena_create(2 * 1024 * 1024);
    g_def = test_load_definition(arena);
    assert(g_def);
    register_default_effects();
}

int main(void) {
    setup();
    printf("Death Tyrant p4 Ched Nasad test\n");

    const char *pids[] = {"p1", "p2", "p3", "p4"};
    GameState *gs = engine_create_game_definition(g_def, pids, 4, 4);
    assert(gs);

    /* Advance past setup */
    Move legal[256]; int n; GameState *tmp;
    for (int i = 0; i < 200; i++) {
        n = engine_legal_moves(gs, legal, 256);
        if (n == 0) break;
        tmp = engine_apply(gs, &legal[0]); engine_destroy(gs); gs = tmp;
        if (gs->phase != PHASE_SETUP) break;
    }
    printf("  Phase: %d\n", gs->phase);

    /* Force to p4's turn */
    while (strcmp(intern_str(gs->current_player_id), "p4") != 0 || gs->phase != PHASE_MAIN) {
        n = engine_legal_moves(gs, legal, 256);
        int used = 0;
        for (int i = 0; i < n; i++) {
            if (legal[i].type == MOVE_END_MAIN_PHASE && strcmp(intern_str(gs->current_player_id), "p4") != 0) {
                tmp = engine_apply(gs, &legal[i]); engine_destroy(gs); gs = tmp; used=1; break;
            }
        }
        if (!used) {
            tmp = engine_apply(gs, &legal[0]); engine_destroy(gs); gs = tmp;
        }
    }
    printf("  Current: %s phase=%d\n", intern_str(gs->current_player_id), gs->phase);

    /* Setup Ched Nasad with 2 p4 + 2 p3 troops */
    Sym p4_id = intern("p4");
    Sym ched_id = intern("site_ched_nasad");

    // Give p4 death_tyrant in hand
    int p4i = -1;
    for (int i = 0; i < gs->player_count; i++)
        if (gs->players[i].player_id == p4_id) { p4i = i; break; }
    assert(p4i >= 0);
    PlayerState *ps = cow_player(gs, p4_id);
    ps->hand[0] = intern("death_tyrant");
    ps->hand_count = 1;
    ps->deck_count = 0;
    ps->discard_pile_count = 0;
    ps->played_cards_count = 0;

    // Set troops at Ched Nasad: [p4, p3, p4, p3]
    int ched_ni = -1;
    for (int i = 0; i < gs->node_count; i++)
        if (gs->nodes[i].node_id == ched_id) { ched_ni = i; break; }
    assert(ched_ni >= 0);
    NodeState *ns = cow_node(gs, ched_id);
    ns->troop_slots[0] = p4_id;
    ns->troop_slots[1] = intern("p3");
    ns->troop_slots[2] = p4_id;
    ns->troop_slots[3] = intern("p3");
    ns->troop_slot_count = 4;

    // Need p4 to have presence - add spy
    int has_spy = 0;
    for (int s = 0; s < ns->spy_count; s++)
        if (ns->spies[s] == p4_id) { has_spy = 1; break; }
    if (!has_spy && ns->spy_count < MAX_SPY_SLOTS)
        ns->spies[ns->spy_count++] = p4_id;

    printf("  Ched Nasad setup: ");
    for (int s = 0; s < ns->troop_slot_count; s++)
        printf("[%d]=%s ", s, ns->troop_slots[s] ? intern_str(ns->troop_slots[s]) : "None");
    printf("\n  Has presence p4: %d\n", has_presence(gs, p4_id, ched_id));

    int inf_before = gs->resource_pool.influence;

    /* Play Death Tyrant */
    Move pm = make_play_card_move(intern("death_tyrant"), 0);
    tmp = engine_apply(gs, &pm);
    if (!tmp) { printf("FAIL: play card\n"); engine_destroy(gs); return 1; }
    engine_destroy(gs); gs = tmp;

    /* Check pending */
    PendingGenericChoiceState *p = gs->pending_generic;
    printf("  Pending: %s, actions=%d\n", p ? "yes" : "no", p ? p->current_action_count : 0);

    /* Find and apply site selection */
    n = engine_legal_moves(gs, legal, 256);
    printf("  Legal after play: %d\n", n);
    int applied = 0;
    for (int i = 0; i < n; i++) {
        if (legal[i].type == MOVE_RESOLVE_GENERIC && legal[i].data.resolve_generic.action_id == ched_id) {
            printf("  Selecting site: %s\n", intern_str(ched_id));
            tmp = engine_apply(gs, &legal[i]);
            if (tmp) { engine_destroy(gs); gs = tmp; applied = 1; break; }
            else printf("  FAIL: site apply returned NULL\n");
        }
    }
    if (!applied) {
        printf("  Site selection not found. Available moves:\n");
        for (int i = 0; i < n; i++) {
            if (legal[i].type == MOVE_RESOLVE_GENERIC) {
                Sym aid = legal[i].data.resolve_generic.action_id;
                printf("    action_id=%s\n", aid ? intern_str(aid) : "NULL");
            }
        }
        engine_destroy(gs); return 1;
    }

    /* Check last_selection */
    p = gs->pending_generic;
    printf("  After site, pending: %s, index=%d\n", p ? "yes" : "no", p ? p->next_action_index : -1);
    if (p) {
        printf("  last_selection_count=%d\n", p->last_selection_count);
        for (int i = 0; i < p->last_selection_count; i++) {
            const char *k = intern_str(p->last_selection_keys[i]);
            const char *v = intern_str(p->last_selection_values[i]);
            printf("    [%d] %s = %s\n", i, k ? k : "NULL", v ? v : "NULL");
        }
    }

    /* Get assassinate moves */
    n = engine_legal_moves(gs, legal, 256);
    printf("  Assassinate moves: %d\n", n);
    for (int i = 0; i < n; i++) {
        if (legal[i].type == MOVE_RESOLVE_GENERIC) {
            Sym aid = legal[i].data.resolve_generic.action_id;
            Sym tid = legal[i].data.resolve_generic.target_id;
            printf("    [%d] node=%s slot=%s\n", i,
                   aid ? intern_str(aid) : "skip",
                   tid ? intern_str(tid) : "-");
        }
    }

    /* Try applying first non-skip assassinate (slot 1 = p3) */
    applied = 0;
    for (int i = 0; i < n; i++) {
        if (legal[i].type == MOVE_RESOLVE_GENERIC
            && legal[i].data.resolve_generic.action_id != SYM_NULL
            && legal[i].data.resolve_generic.target_id != SYM_NULL) {
            Sym tid = legal[i].data.resolve_generic.target_id;
            printf("  Trying assassinate at slot=%s\n", intern_str(tid));
            tmp = engine_apply(gs, &legal[i]);
            if (tmp) {
                engine_destroy(gs); gs = tmp;
                applied = 1;
                printf("  Applied! Troops after: ");
                NodeState *ns2 = cow_node(gs, ched_id);
                for (int s = 0; s < ns2->troop_slot_count; s++)
                    printf("[%d]=%s ", s, ns2->troop_slots[s] ? intern_str(ns2->troop_slots[s]) : "None");
                printf("\n");
                break;
            } else {
                printf("  FAIL: apply returned NULL\n");
            }
        }
    }
    if (!applied) printf("  No assassinate applied\n");

    /* Skip remaining */
    while (gs->pending_generic) {
        n = engine_legal_moves(gs, legal, 256);
        int skipped = 0;
        for (int i = 0; i < n; i++) {
            if (legal[i].type == MOVE_RESOLVE_GENERIC
                && legal[i].data.resolve_generic.action_id == SYM_NULL) {
                tmp = engine_apply(gs, &legal[i]);
                engine_destroy(gs); gs = tmp;
                skipped = 1; break;
            }
        }
        if (!skipped) break;
    }

    NodeState *nsf = cow_node(gs, ched_id);
    printf("  Final troops: ");
    for (int s = 0; s < nsf->troop_slot_count; s++)
        printf("[%d]=%s ", s, nsf->troop_slots[s] ? intern_str(nsf->troop_slots[s]) : "None");
    printf("\n  Influence: %d (was %d, delta=%d)\n",
           gs->resource_pool.influence, inf_before,
           gs->resource_pool.influence - inf_before);

    engine_destroy(gs);
    printf("DONE\n");
    return 0;
}
