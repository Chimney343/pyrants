#include "generic_runtime.h"
#include "intern.h"
#include "moves.h"
#include "selection.h"
#include "state.h"
#include "engine.h"
#include <stdio.h>
#include <assert.h>
#include <string.h>

static void test_action_requires_selection_force_discard_local(void) {
    intern_init(4096);
    CardAction a;
    memset(&a, 0, sizeof(a));
    a.op = intern("force_discard");
    a.target_scope = intern("opponent");
    a.source_fragment = intern("local_discard");

    int r = action_requires_selection(&a);
    assert(r == 0);
    printf("PASS: force_discard+local_discard → no selection\n");
    intern_destroy();
}

static void test_action_requires_selection_force_discard_targeted(void) {
    intern_init(4096);
    CardAction a;
    memset(&a, 0, sizeof(a));
    a.op = intern("force_discard");
    a.target_scope = intern("opponent");
    a.source_fragment = intern("targeted_discard");

    int r = action_requires_selection(&a);
    assert(r == 1);
    printf("PASS: force_discard+targeted_discard → requires selection\n");
    intern_destroy();
}

static void test_action_requires_selection_force_discard_default_scope(void) {
    intern_init(4096);
    CardAction a;
    memset(&a, 0, sizeof(a));
    a.op = intern("force_discard");
    /* target_scope is SYM_NULL (not "opponent"), source_fragment is SYM_NULL */

    int r = action_requires_selection(&a);
    assert(r == 1);
    printf("PASS: force_discard+default scope → requires selection\n");
    intern_destroy();
}

static void test_action_requires_selection_force_discard_hand_scope(void) {
    intern_init(4096);
    CardAction a;
    memset(&a, 0, sizeof(a));
    a.op = intern("force_discard");
    a.target_scope = intern("hand");   /* not "opponent" */
    a.source_fragment = intern("local_discard");

    int r = action_requires_selection(&a);
    assert(r == 1);
    printf("PASS: force_discard+hand scope → requires selection\n");
    intern_destroy();
}

static void test_action_requires_selection_deploy_troops(void) {
    intern_init(4096);
    CardAction a;
    memset(&a, 0, sizeof(a));
    a.op = intern("deploy_troops");

    int r = action_requires_selection(&a);
    assert(r == 1);
    printf("PASS: deploy_troops → requires selection\n");
    intern_destroy();
}

static void test_action_requires_selection_promote_end_of_turn(void) {
    intern_init(4096);
    CardAction a;
    memset(&a, 0, sizeof(a));
    a.op = intern("promote_card");
    a.timing = intern("end_of_turn");

    int r = action_requires_selection(&a);
    assert(r == 0);
    printf("PASS: promote_card+end_of_turn → no selection\n");
    intern_destroy();
}

static void test_action_requires_selection_promote_immediate(void) {
    intern_init(4096);
    CardAction a;
    memset(&a, 0, sizeof(a));
    a.op = intern("promote_card");
    a.timing = intern("immediate");
    a.source_fragment = SYM_NULL;  /* not threshold_self_promote or promote_top_of_deck */

    int r = action_requires_selection(&a);
    assert(r == 1);
    printf("PASS: promote_card+immediate → requires selection\n");
    intern_destroy();
}

static void test_action_requires_selection_custom_effect(void) {
    intern_init(4096);
    CardAction a;
    memset(&a, 0, sizeof(a));
    a.op = intern("custom_effect");
    /* no metadata → no effect_kind → not a selection */

    int r = action_requires_selection(&a);
    assert(r == 0);
    printf("PASS: custom_effect+no_effect_kind → no selection\n");
    intern_destroy();
}

static void test_action_requires_selection_custom_effect_give_insane_outcast_to_self(void) {
    intern_init(4096);
    CardAction a;
    memset(&a, 0, sizeof(a));
    a.op = intern("custom_effect");
    a.metadata[0].key = intern("effect_kind");
    a.metadata[0].value = intern("give_insane_outcast_to_self");
    a.metadata_count = 1;

    int r = action_requires_selection(&a);
    assert(r == 0);
    printf("PASS: custom_effect+give_insane_outcast_to_self → no selection\n");
    intern_destroy();
}

static void test_action_requires_selection_custom_effect_selected_player(void) {
    intern_init(4096);
    CardAction a;
    memset(&a, 0, sizeof(a));
    a.op = intern("custom_effect");
    a.metadata[0].key = intern("effect_kind");
    a.metadata[0].value = intern("give_insane_outcast_to_selected_player");
    a.metadata_count = 1;

    int r = action_requires_selection(&a);
    assert(r == 1);
    printf("PASS: custom_effect+selected_player → requires selection\n");
    intern_destroy();
}

static void test_action_requires_selection_custom_effect_presence_on_last_selected(void) {
    intern_init(4096);
    CardAction a;
    memset(&a, 0, sizeof(a));
    a.op = intern("custom_effect");
    a.metadata[0].key = intern("effect_kind");
    a.metadata[0].value = intern("give_insane_outcast_to_player_with_presence_on_last_selected_node");
    a.metadata_count = 1;

    int r = action_requires_selection(&a);
    assert(r == 1);
    printf("PASS: custom_effect+presence_on_last_selected → requires selection\n");
    intern_destroy();
}

static void test_devour_target_count_hand(void) {
    intern_init(4096);
    Sym p1 = intern("p1");
    CardAction a;
    memset(&a, 0, sizeof(a));
    a.metadata[0].key = intern("source_zone");
    a.metadata[0].value = intern("hand");
    a.metadata_count = 1;

    GameState s;
    memset(&s, 0, sizeof(s));
    s.player_count = 1;
    s.players[0].player_id = p1;
    s.players[0].hand_count = 2;

    assert(devour_target_count(&s, p1, &a, -1) == 2);
    assert(devour_target_count(&s, p1, &a, 0) == 1);
    assert(devour_target_count(&s, p1, &a, 5) == 2);
    printf("PASS: devour_target_count hand zone\n");
    intern_destroy();
}

static void test_devour_target_count_inner_circle(void) {
    intern_init(4096);
    Sym p1 = intern("p1");
    CardAction a;
    memset(&a, 0, sizeof(a));
    a.metadata[0].key = intern("source_zone");
    a.metadata[0].value = intern("inner_circle");
    a.metadata_count = 1;

    GameState s;
    memset(&s, 0, sizeof(s));
    s.player_count = 1;
    s.players[0].player_id = p1;
    s.players[0].inner_circle_count = 3;

    assert(devour_target_count(&s, p1, &a, -1) == 3);
    printf("PASS: devour_target_count inner_circle zone\n");
    intern_destroy();
}

static void test_devour_target_count_market(void) {
    intern_init(4096);
    Sym p1 = intern("p1");
    CardAction a;
    memset(&a, 0, sizeof(a));
    a.metadata[0].key = intern("source_zone");
    a.metadata[0].value = intern("market");
    a.metadata_count = 1;

    GameState s;
    memset(&s, 0, sizeof(s));
    s.player_count = 1;
    s.players[0].player_id = p1;
    s.market.row_count = 4;

    assert(devour_target_count(&s, p1, &a, -1) == 4);
    printf("PASS: devour_target_count market zone\n");
    intern_destroy();
}

static void test_devour_target_count_played_self(void) {
    intern_init(4096);
    Sym p1 = intern("p1");
    CardAction a;
    memset(&a, 0, sizeof(a));
    a.metadata[0].key = intern("source_zone");
    a.metadata[0].value = intern("played_self");
    a.metadata_count = 1;

    GameState s;
    memset(&s, 0, sizeof(s));
    s.player_count = 1;
    s.players[0].player_id = p1;

    assert(devour_target_count(&s, p1, &a, -1) == -1);
    printf("PASS: devour_target_count played_self zone\n");
    intern_destroy();
}

static void test_devour_target_count_market_dependent(void) {
    intern_init(4096);
    Sym p1 = intern("p1");
    CardAction a;
    memset(&a, 0, sizeof(a));
    a.metadata[0].key = intern("source_zone");
    a.metadata[0].value = intern("market");
    a.metadata[1].key = intern("requires_last_selected_market_slot");
    a.metadata[1].value = intern("true");
    a.metadata_count = 2;

    GameState s;
    memset(&s, 0, sizeof(s));
    s.player_count = 1;
    s.players[0].player_id = p1;
    s.market.row_count = 0;

    assert(devour_target_count(&s, p1, &a, -1) == -1);
    printf("PASS: devour_target_count market dependent selection\n");
    intern_destroy();
}

static void test_devour_target_count_fallback_scope(void) {
    intern_init(4096);
    Sym p1 = intern("p1");
    CardAction a;
    memset(&a, 0, sizeof(a));
    a.target_scope = intern("inner_circle"); /* no source_zone metadata */

    GameState s;
    memset(&s, 0, sizeof(s));
    s.player_count = 1;
    s.players[0].player_id = p1;
    s.players[0].inner_circle_count = 2;

    assert(devour_target_count(&s, p1, &a, -1) == 2);
    printf("PASS: devour_target_count fallback to target_scope\n");
    intern_destroy();
}

static void test_card_play_devour_sequence_hand(void) {
    intern_init(4096);
    Sym p1 = intern("p1");
    CardAction acts[1];
    memset(acts, 0, sizeof(acts));
    acts[0].op = intern("devour_cost");
    acts[0].optional = false;
    acts[0].metadata[0].key = intern("source_zone");
    acts[0].metadata[0].value = intern("hand");
    acts[0].metadata_count = 1;

    CardDefinition cd;
    memset(&cd, 0, sizeof(cd));
    cd.execution.kind = EXEC_SEQUENCE;
    cd.execution.actions = acts;
    cd.execution.action_count = 1;

    GameState s;
    memset(&s, 0, sizeof(s));
    s.player_count = 1;
    s.players[0].player_id = p1;
    s.players[0].hand_count = 1;
    assert(card_play_devour_costs_payable(&s, p1, &cd, 0) == 0);

    s.players[0].hand_count = 2;
    assert(card_play_devour_costs_payable(&s, p1, &cd, 0) == 1);
    printf("PASS: card_play_devour_costs_payable sequence hand devour\n");
    intern_destroy();
}

static void test_card_play_devour_modal_all_blocked(void) {
    intern_init(4096);
    Sym p1 = intern("p1");
    CardAction o1[1], o2[1];
    memset(o1, 0, sizeof(o1));
    memset(o2, 0, sizeof(o2));
    o1[0].op = intern("devour_cost");
    o1[0].optional = false;
    o1[0].metadata[0].key = intern("source_zone");
    o1[0].metadata[0].value = intern("hand");
    o1[0].metadata_count = 1;
    o2[0] = o1[0];

    CardOption opts[2];
    memset(opts, 0, sizeof(opts));
    opts[0].option_id = intern("option_1");
    opts[0].actions = o1;
    opts[0].action_count = 1;
    opts[1].option_id = intern("option_2");
    opts[1].actions = o2;
    opts[1].action_count = 1;

    CardDefinition cd;
    memset(&cd, 0, sizeof(cd));
    cd.execution.kind = EXEC_MODAL;
    cd.execution.options = opts;
    cd.execution.option_count = 2;

    GameState s;
    memset(&s, 0, sizeof(s));
    s.player_count = 1;
    s.players[0].player_id = p1;
    s.players[0].hand_count = 1;
    assert(card_play_devour_costs_payable(&s, p1, &cd, 0) == 0);
    printf("PASS: card_play_devour_costs_payable modal all blocked\n");
    intern_destroy();
}

static void test_card_play_devour_modal_partially_blocked(void) {
    intern_init(4096);
    Sym p1 = intern("p1");
    CardAction o1[1], o2[1];
    memset(o1, 0, sizeof(o1));
    memset(o2, 0, sizeof(o2));
    o1[0].op = intern("gain_resource");
    o1[0].optional = false;
    o2[0].op = intern("devour_cost");
    o2[0].optional = false;
    o2[0].metadata[0].key = intern("source_zone");
    o2[0].metadata[0].value = intern("hand");
    o2[0].metadata_count = 1;

    CardOption opts[2];
    memset(opts, 0, sizeof(opts));
    opts[0].option_id = intern("option_1");
    opts[0].actions = o1;
    opts[0].action_count = 1;
    opts[1].option_id = intern("option_2");
    opts[1].actions = o2;
    opts[1].action_count = 1;

    CardDefinition cd;
    memset(&cd, 0, sizeof(cd));
    cd.execution.kind = EXEC_MODAL;
    cd.execution.options = opts;
    cd.execution.option_count = 2;

    GameState s;
    memset(&s, 0, sizeof(s));
    s.player_count = 1;
    s.players[0].player_id = p1;
    s.players[0].hand_count = 1;
    assert(card_play_devour_costs_payable(&s, p1, &cd, 0) == 1);
    printf("PASS: card_play_devour_costs_payable modal partially blocked\n");
    intern_destroy();
}

static void test_card_play_devour_optional_ignored(void) {
    intern_init(4096);
    Sym p1 = intern("p1");
    CardAction acts[1];
    memset(acts, 0, sizeof(acts));
    acts[0].op = intern("devour_cost");
    acts[0].optional = true;
    acts[0].metadata[0].key = intern("source_zone");
    acts[0].metadata[0].value = intern("market");
    acts[0].metadata_count = 1;

    CardDefinition cd;
    memset(&cd, 0, sizeof(cd));
    cd.execution.kind = EXEC_SEQUENCE;
    cd.execution.actions = acts;
    cd.execution.action_count = 1;

    GameState s;
    memset(&s, 0, sizeof(s));
    s.player_count = 1;
    s.players[0].player_id = p1;
    s.market.row_count = 0;

    assert(card_play_devour_costs_payable(&s, p1, &cd, -1) == 1);
    printf("PASS: card_play_devour_costs_payable optional devour ignored\n");
    intern_destroy();
}

static void test_card_play_devour_unknown_kind(void) {
    intern_init(4096);
    Sym p1 = intern("p1");
    CardDefinition cd;
    memset(&cd, 0, sizeof(cd));
    cd.execution.kind = 99;

    GameState s;
    memset(&s, 0, sizeof(s));
    s.player_count = 1;
    s.players[0].player_id = p1;

    assert(card_play_devour_costs_payable(&s, p1, &cd, 0) == 1);
    printf("PASS: card_play_devour_costs_payable unknown execution kind\n");
    intern_destroy();
}

static void test_card_play_modal_options_all_dead(void) {
    /* Runs inside main()'s first intern table so the selection dispatch
     * registered by register_selection_handlers() resolves. */
    Sym p1 = intern("p1");
    CardAction o1[1], o2[1];
    memset(o1, 0, sizeof(o1));
    memset(o2, 0, sizeof(o2));
    o1[0].op = intern("supplant_troop");
    o1[0].optional = false;
    o2[0].op = intern("promote_card");
    o2[0].optional = false;
    o2[0].source_fragment = intern("promote_from_discard");

    CardOption opts[2];
    memset(opts, 0, sizeof(opts));
    opts[0].option_id = intern("option_1");
    opts[0].actions = o1;
    opts[0].action_count = 1;
    opts[1].option_id = intern("option_2");
    opts[1].actions = o2;
    opts[1].action_count = 1;

    CardDefinition cd;
    memset(&cd, 0, sizeof(cd));
    cd.card_id = intern("vampire");
    cd.execution.kind = EXEC_MODAL;
    cd.execution.options = opts;
    cd.execution.option_count = 2;

    GameState s;
    memset(&s, 0, sizeof(s));
    s.player_count = 1;
    s.players[0].player_id = p1;
    s.players[0].discard_pile_count = 0;

    /* No board (no supplant targets) + empty discard: both options dead. */
    assert(card_play_modal_options_viable(&s, p1, &cd) == 0);

    /* A discard card makes option_2 viable again. */
    s.players[0].discard_pile_count = 1;
    assert(card_play_modal_options_viable(&s, p1, &cd) == 1);

    /* Sequence cards are never blocked. */
    cd.execution.kind = EXEC_SEQUENCE;
    assert(card_play_modal_options_viable(&s, p1, &cd) == 1);
    printf("PASS: card_play_modal_options_viable all-dead and recovery\n");
}

static void test_sel_place_spy_relocation(void) {
    Sym p1 = intern("p1");
    Sym site_a = intern("site_a");
    Sym site_b = intern("site_b");
    Sym site_c = intern("site_c");
    Sym kind_site = intern("site");

    NodeDefinition board_nodes[3];
    memset(board_nodes, 0, sizeof(board_nodes));
    board_nodes[0].node_id = site_a;
    board_nodes[0].kind = kind_site;
    board_nodes[1].node_id = site_b;
    board_nodes[1].kind = kind_site;
    board_nodes[2].node_id = site_c;
    board_nodes[2].kind = kind_site;

    BoardDefinition board;
    memset(&board, 0, sizeof(board));
    board.nodes = board_nodes;
    board.node_count = 3;

    GameDefinition def;
    memset(&def, 0, sizeof(def));
    def.board = board;

    GameState s;
    memset(&s, 0, sizeof(s));
    s.definition = &def;
    s.player_count = 1;
    s.players[0].player_id = p1;
    s.players[0].spies_available = 0;   /* all spies placed */
    s.node_count = 3;
    s.nodes[0].node_id = site_a;
    s.nodes[1].node_id = site_b;
    s.nodes[2].node_id = site_c;
    s.nodes[0].spies[0] = p1; s.nodes[0].spy_count = 1;  /* own spy at A */
    s.nodes[1].spies[0] = p1; s.nodes[1].spy_count = 1;  /* own spy at B */

    CardAction action;
    memset(&action, 0, sizeof(action));
    action.op = intern("place_spy");

    Move out[64];
    memset(out, 0, sizeof(out));
    int n = legal_generic_target_selection_moves(&s, p1, NULL, NULL, &action, out, 64);

    /* 1 decline + relocations: A→C and B→C. */
    assert(n == 3);
    int decline = 0, reloc = 0;
    for (int i = 0; i < n; i++) {
        assert(out[i].type == MOVE_RESOLVE_GENERIC);
        Sym aid = out[i].data.resolve_generic.action_id;
        Sym tid = out[i].data.resolve_generic.target_id;
        if (aid == SYM_NULL && tid == SYM_NULL) {
            decline++;
            continue;
        }
        reloc++;
        assert(tid == site_a || tid == site_b);          /* source holds own spy */
        assert(aid == site_c);                            /* destination is spy-free */
        assert(aid != tid);                               /* no self-move */
    }
    assert(decline == 1);
    assert(reloc == 2);
    printf("PASS: sel_place_spy relocation emits decline + (source,destination) pairs\n");
}

static void test_sel_place_spy_supply_regression(void) {
    Sym p1 = intern("p1");
    Sym site_a = intern("site_a");
    Sym site_b = intern("site_b");
    Sym site_c = intern("site_c");
    Sym kind_site = intern("site");

    NodeDefinition board_nodes[3];
    memset(board_nodes, 0, sizeof(board_nodes));
    board_nodes[0].node_id = site_a;
    board_nodes[0].kind = kind_site;
    board_nodes[1].node_id = site_b;
    board_nodes[1].kind = kind_site;
    board_nodes[2].node_id = site_c;
    board_nodes[2].kind = kind_site;

    BoardDefinition board;
    memset(&board, 0, sizeof(board));
    board.nodes = board_nodes;
    board.node_count = 3;

    GameDefinition def;
    memset(&def, 0, sizeof(def));
    def.board = board;

    GameState s;
    memset(&s, 0, sizeof(s));
    s.definition = &def;
    s.player_count = 1;
    s.players[0].player_id = p1;
    s.players[0].spies_available = 5;   /* supply available */
    s.node_count = 3;
    s.nodes[0].node_id = site_a;
    s.nodes[1].node_id = site_b;
    s.nodes[2].node_id = site_c;

    CardAction action;
    memset(&action, 0, sizeof(action));
    action.op = intern("place_spy");

    Move out[64];
    memset(out, 0, sizeof(out));
    int n = legal_generic_target_selection_moves(&s, p1, NULL, NULL, &action, out, 64);

    assert(n == 3);
    for (int i = 0; i < n; i++) {
        assert(out[i].type == MOVE_RESOLVE_GENERIC);
        assert(out[i].data.resolve_generic.action_id != SYM_NULL);
        assert(out[i].data.resolve_generic.target_id == SYM_NULL);  /* no source */
    }
    printf("PASS: sel_place_spy supply placement unchanged (no decline, no source)\n");
}

static void test_sel_deploy_empty_barracks(void) {
    Sym p1 = intern("p1");
    Sym site_a = intern("site_a");

    GameState s;
    memset(&s, 0, sizeof(s));
    s.player_count = 1;
    s.players[0].player_id = p1;
    s.players[0].barracks = 0;
    s.node_count = 1;
    s.nodes[0].node_id = site_a;
    s.nodes[0].troop_slot_count = 3;

    CardAction action;
    memset(&action, 0, sizeof(action));
    action.op = intern("deploy_troops");

    Move out[64];
    memset(out, 0, sizeof(out));
    int n = legal_generic_target_selection_moves(&s, p1, NULL, NULL, &action, out, 64);

    assert(n == 1);
    assert(out[0].type == MOVE_RESOLVE_GENERIC);
    assert(out[0].data.resolve_generic.action_id == SYM_NULL);
    printf("PASS: sel_deploy empty barracks emits single VP sentinel move\n");
}

static void test_sel_deploy_with_troops(void) {
    Sym p1 = intern("p1");
    Sym site_a = intern("site_a");

    GameState s;
    memset(&s, 0, sizeof(s));
    s.player_count = 1;
    s.players[0].player_id = p1;
    s.players[0].barracks = 3;
    s.node_count = 1;
    s.nodes[0].node_id = site_a;
    s.nodes[0].troop_slot_count = 3;

    CardAction action;
    memset(&action, 0, sizeof(action));
    action.op = intern("deploy_troops");

    Move out[64];
    memset(out, 0, sizeof(out));
    int n = legal_generic_target_selection_moves(&s, p1, NULL, NULL, &action, out, 64);

    assert(n == 1);
    assert(out[0].type == MOVE_RESOLVE_GENERIC);
    assert(out[0].data.resolve_generic.action_id == site_a);
    printf("PASS: sel_deploy with troops emits per-node target move\n");
}

int main(void) {
    intern_init(4096);
    register_selection_handlers();
    test_sel_place_spy_relocation();
    test_sel_place_spy_supply_regression();
    test_sel_deploy_empty_barracks();
    test_sel_deploy_with_troops();
    test_card_play_modal_options_all_dead();
    intern_destroy();
    test_action_requires_selection_force_discard_local();
    test_action_requires_selection_force_discard_targeted();
    test_action_requires_selection_force_discard_default_scope();
    test_action_requires_selection_force_discard_hand_scope();
    test_action_requires_selection_deploy_troops();
    test_action_requires_selection_promote_end_of_turn();
    test_action_requires_selection_promote_immediate();
    test_action_requires_selection_custom_effect();
    test_action_requires_selection_custom_effect_give_insane_outcast_to_self();
    test_action_requires_selection_custom_effect_selected_player();
    test_action_requires_selection_custom_effect_presence_on_last_selected();
    test_devour_target_count_hand();
    test_devour_target_count_inner_circle();
    test_devour_target_count_market();
    test_devour_target_count_played_self();
    test_devour_target_count_market_dependent();
    test_devour_target_count_fallback_scope();
    test_card_play_devour_sequence_hand();
    test_card_play_devour_modal_all_blocked();
    test_card_play_devour_modal_partially_blocked();
    test_card_play_devour_optional_ignored();
    test_card_play_devour_unknown_kind();
    printf("All generic action tests passed.\n");
    return 0;
}
