#include "generic_runtime.h"
#include "intern.h"
#include "moves.h"
#include "ops/op.h"
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
    printf("PASS: force_discard+local_discard ??? no selection\n");
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
    printf("PASS: force_discard+targeted_discard ??? requires selection\n");
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
    printf("PASS: force_discard+default scope ??? requires selection\n");
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
    printf("PASS: force_discard+hand scope ??? requires selection\n");
    intern_destroy();
}

static void test_action_requires_selection_deploy_troops(void) {
    intern_init(4096);
    CardAction a;
    memset(&a, 0, sizeof(a));
    a.op = intern("deploy_troops");

    int r = action_requires_selection(&a);
    assert(r == 1);
    printf("PASS: deploy_troops ??? requires selection\n");
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
    printf("PASS: promote_card+end_of_turn ??? no selection\n");
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
    printf("PASS: promote_card+immediate ??? requires selection\n");
    intern_destroy();
}

static void test_action_requires_selection_custom_effect(void) {
    intern_init(4096);
    CardAction a;
    memset(&a, 0, sizeof(a));
    a.op = intern("custom_effect");
    /* no metadata ??? no effect_kind ??? not a selection */

    int r = action_requires_selection(&a);
    assert(r == 0);
    printf("PASS: custom_effect+no_effect_kind ??? no selection\n");
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
    printf("PASS: custom_effect+give_insane_outcast_to_self ??? no selection\n");
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
    printf("PASS: custom_effect+selected_player ??? requires selection\n");
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
    printf("PASS: custom_effect+presence_on_last_selected ??? requires selection\n");
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

    /* 1 decline + relocations: A???C and B???C. */
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

static void test_op_return_spy(void) {
    Sym p1 = intern("p1");
    Sym site_a = intern("site_a");
    Sym site_b = intern("site_b");
    Sym kind_site = intern("site");

    NodeDefinition board_nodes[2];
    memset(board_nodes, 0, sizeof(board_nodes));
    board_nodes[0].node_id = site_a;
    board_nodes[0].kind = kind_site;
    board_nodes[1].node_id = site_b;
    board_nodes[1].kind = kind_site;

    BoardDefinition board;
    memset(&board, 0, sizeof(board));
    board.nodes = board_nodes;
    board.node_count = 2;

    GameDefinition def;
    memset(&def, 0, sizeof(def));
    def.board = board;

    GameState s;
    memset(&s, 0, sizeof(s));
    s.definition = &def;
    s.player_count = 1;
    s.players[0].player_id = p1;
    s.players[0].spies_available = 0;
    s.node_count = 2;
    s.nodes[0].node_id = site_a;
    s.nodes[1].node_id = site_b;
    s.nodes[0].spies[0] = p1;
    s.nodes[0].spy_count = 1;

    CardAction action;
    memset(&action, 0, sizeof(action));
    action.op = intern("return_spy");
    action.metadata[0].key = intern("spy_owner");
    action.metadata[0].value = intern("self");
    action.metadata_count = 1;

    const CardOp *op = op_lookup(intern("return_spy"));
    assert(op != NULL);
    assert(op->needs_selection);
    assert(op->enumerate != NULL);
    assert(op->target_from_move != NULL);
    assert(op->apply != NULL);
    assert(op->describe != NULL);
    assert(action_requires_selection(&action) == 1);
    assert(op_lookup(intern("custom_effect")) == NULL);

    Move out[8];
    memset(out, 0, sizeof(out));
    int n = legal_generic_target_selection_moves(&s, p1, NULL, NULL, &action, out, 8);
    assert(n == 1);
    assert(out[0].type == MOVE_RESOLVE_GENERIC);
    assert(out[0].data.resolve_generic.action_id == site_a);
    assert(out[0].data.resolve_generic.target_id == SYM_NULL);

    OpTarget target;
    memset(&target, 0, sizeof(target));
    assert(op->target_from_move(&s, p1, &action, &out[0], &target));
    assert(target.kind == OP_TARGET_RETURN_SPY);
    assert(target.as.return_spy.node_id == site_a);
    assert(target.as.return_spy.spy_owner_id == p1);
    assert(target.as.return_spy.free_enemy_return == 0);

    char label[64];
    label[0] = '\0';
    op->describe(&s, &action, NULL, NULL, NULL, 0, label, sizeof(label));
    assert(strcmp(label, "Return a spy") == 0);

    assert(op->apply(&s, p1, NULL, &action, &target) == &s);
    assert(s.nodes[0].spy_count == 0);
    assert(s.players[0].spies_available == 1);

    printf("PASS: return_spy op owns selection/target/apply/describe\n");
}

static void test_op_place_spy(void) {
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
    s.players[0].spies_available = 0;
    s.node_count = 3;
    s.nodes[0].node_id = site_a;
    s.nodes[1].node_id = site_b;
    s.nodes[2].node_id = site_c;
    s.nodes[0].spies[0] = p1;
    s.nodes[0].spy_count = 1;
    s.nodes[1].spies[0] = p1;
    s.nodes[1].spy_count = 1;

    CardAction action;
    memset(&action, 0, sizeof(action));
    action.op = intern("place_spy");

    const CardOp *op = op_lookup(intern("place_spy"));
    assert(op != NULL);
    assert(op->needs_selection);
    assert(op->enumerate != NULL);
    assert(op->target_from_move != NULL);
    assert(op->apply != NULL);
    assert(op->describe != NULL);

    Move out[16];
    memset(out, 0, sizeof(out));
    int n = legal_generic_target_selection_moves(&s, p1, NULL, NULL, &action, out, 16);
    assert(n == 3);

    Move *relocation = NULL;
    for (int i = 0; i < n; i++) {
        if (out[i].data.resolve_generic.action_id == site_c) {
            relocation = &out[i];
            break;
        }
    }
    assert(relocation != NULL);
    assert(relocation->data.resolve_generic.target_id == site_a);

    OpTarget target;
    memset(&target, 0, sizeof(target));
    assert(op->target_from_move(&s, p1, &action, relocation, &target));
    assert(target.kind == OP_TARGET_PLACE_SPY);
    assert(target.as.place_spy.target_node_id == site_c);
    assert(target.as.place_spy.source_node_id == site_a);

    const char *ids[3] = {"site_a", "site_b", "site_c"};
    const char *labels[3] = {"A", "B", "C"};
    char label[96];
    label[0] = '\0';
    op->describe(&s, &action, &target, ids, labels, 3, label, sizeof(label));
    assert(strcmp(label, "Move your spy from A to C") == 0);

    assert(op->apply(&s, p1, NULL, &action, &target) == &s);
    assert(s.nodes[0].spy_count == 0);
    assert(s.nodes[2].spy_count == 1);
    assert(s.nodes[2].spies[0] == p1);

    printf("PASS: place_spy op owns relocation selection/target/apply/describe\n");
}

static void test_op_return_unit(void) {
    Sym p1 = intern("p1");
    Sym site_a = intern("site_a");
    Sym kind_site = intern("site");

    NodeDefinition board_nodes[1];
    memset(board_nodes, 0, sizeof(board_nodes));
    board_nodes[0].node_id = site_a;
    board_nodes[0].kind = kind_site;

    BoardDefinition board;
    memset(&board, 0, sizeof(board));
    board.nodes = board_nodes;
    board.node_count = 1;

    GameDefinition def;
    memset(&def, 0, sizeof(def));
    def.board = board;

    GameState s;
    memset(&s, 0, sizeof(s));
    s.definition = &def;
    s.player_count = 1;
    s.players[0].player_id = p1;
    s.node_count = 1;
    s.nodes[0].node_id = site_a;
    s.nodes[0].troop_slot_count = 1;
    s.nodes[0].troop_slots[0] = p1;

    CardAction action;
    memset(&action, 0, sizeof(action));
    action.op = intern("return_unit");
    action.target_scope = intern("self");

    const CardOp *op = op_lookup(intern("return_unit"));
    assert(op != NULL);
    assert(op->needs_selection);
    assert(op->enumerate != NULL);
    assert(op->target_from_move != NULL);
    assert(op->apply != NULL);
    assert(op->describe != NULL);

    Move out[8];
    memset(out, 0, sizeof(out));
    int n = legal_generic_target_selection_moves(&s, p1, NULL, NULL, &action, out, 8);
    assert(n == 1);
    assert(out[0].type == MOVE_RESOLVE_GENERIC);
    assert(out[0].data.resolve_generic.action_id == site_a);
    const char *target_str = intern_str(out[0].data.resolve_generic.target_id);
    assert(target_str && strcmp(target_str, "troop:0") == 0);

    OpTarget target;
    memset(&target, 0, sizeof(target));
    assert(op->target_from_move(&s, p1, &action, &out[0], &target));
    assert(target.kind == OP_TARGET_RETURN_UNIT);
    assert(target.as.return_unit.node_id == site_a);
    assert(target.as.return_unit.unit_type == intern("troop"));
    assert(target.as.return_unit.slot_index == 0);

    const char *ids[1] = {"site_a"};
    const char *labels[1] = {"A"};
    char label[96];
    label[0] = '\0';
    op->describe(&s, &action, &target, ids, labels, 1, label, sizeof(label));
    assert(strcmp(label, "Return Player 1's troop from A") == 0);

    assert(op->apply(&s, p1, NULL, &action, &target) == &s);
    assert(s.nodes[0].troop_slots[0] == SYM_NULL);
    assert(s.players[0].barracks == 1);

    printf("PASS: return_unit op owns troop selection/target/apply/describe\n");
}

static void test_op_deploy_troops(void) {
    Sym p1 = intern("p1");
    Sym site_a = intern("site_a");
    Sym kind_site = intern("site");

    NodeDefinition board_nodes[1];
    memset(board_nodes, 0, sizeof(board_nodes));
    board_nodes[0].node_id = site_a;
    board_nodes[0].kind = kind_site;

    BoardDefinition board;
    memset(&board, 0, sizeof(board));
    board.nodes = board_nodes;
    board.node_count = 1;

    GameDefinition def;
    memset(&def, 0, sizeof(def));
    def.board = board;

    GameState s;
    memset(&s, 0, sizeof(s));
    s.definition = &def;
    s.player_count = 1;
    s.players[0].player_id = p1;
    s.players[0].barracks = 1;
    s.node_count = 1;
    s.nodes[0].node_id = site_a;
    s.nodes[0].troop_slot_count = 1;

    CardAction action;
    memset(&action, 0, sizeof(action));
    action.op = intern("deploy_troops");

    const CardOp *op = op_lookup(intern("deploy_troops"));
    assert(op != NULL);
    assert(op->needs_selection);
    assert(op->enumerate != NULL);
    assert(op->target_from_move != NULL);
    assert(op->apply != NULL);
    assert(op->describe != NULL);

    Move out[8];
    memset(out, 0, sizeof(out));
    int n = legal_generic_target_selection_moves(&s, p1, NULL, NULL, &action, out, 8);
    assert(n == 1);
    assert(out[0].data.resolve_generic.action_id == site_a);

    OpTarget target;
    memset(&target, 0, sizeof(target));
    assert(op->target_from_move(&s, p1, &action, &out[0], &target));
    assert(target.kind == OP_TARGET_DEPLOY_TROOPS);
    assert(target.as.deploy_troops.node_id == site_a);

    const char *ids[1] = {"site_a"};
    const char *labels[1] = {"A"};
    char label[96];
    label[0] = '\0';
    op->describe(&s, &action, &target, ids, labels, 1, label, sizeof(label));
    assert(strcmp(label, "Deploy a troop to A") == 0);

    assert(op->apply(&s, p1, NULL, &action, &target) == &s);
    assert(s.nodes[0].troop_slots[0] == p1);
    assert(s.players[0].barracks == 0);

    /* Empty barracks: the decline sentinel grants one VP and places nothing. */
    s.players[0].barracks = 0;
    s.nodes[0].troop_slots[0] = SYM_NULL;
    n = legal_generic_target_selection_moves(&s, p1, NULL, NULL, &action, out, 8);
    assert(n == 1);
    assert(out[0].data.resolve_generic.action_id == SYM_NULL);
    assert(op->target_from_move(&s, p1, &action, &out[0], &target));
    assert(target.as.deploy_troops.node_id == SYM_NULL);
    assert(op->apply(&s, p1, NULL, &action, &target) == &s);
    assert(s.players[0].vp_tokens == 1);
    assert(s.nodes[0].troop_slots[0] == SYM_NULL);

    printf("PASS: deploy_troops op owns node/decline target, apply and describe\n");
}

static void test_op_move_troop(void) {
    Sym p1 = intern("p1");
    Sym p2 = intern("p2");
    Sym site_a = intern("site_a");
    Sym site_b = intern("site_b");
    Sym kind_site = intern("site");

    NodeDefinition board_nodes[2];
    memset(board_nodes, 0, sizeof(board_nodes));
    board_nodes[0].node_id = site_a;
    board_nodes[0].kind = kind_site;
    board_nodes[1].node_id = site_b;
    board_nodes[1].kind = kind_site;

    BoardDefinition board;
    memset(&board, 0, sizeof(board));
    board.nodes = board_nodes;
    board.node_count = 2;

    GameDefinition def;
    memset(&def, 0, sizeof(def));
    def.board = board;

    GameState s;
    memset(&s, 0, sizeof(s));
    s.definition = &def;
    s.player_count = 2;
    s.players[0].player_id = p1;
    s.players[1].player_id = p2;
    s.node_count = 2;
    s.nodes[0].node_id = site_a;
    s.nodes[1].node_id = site_b;
    s.nodes[0].troop_slot_count = 1;
    s.nodes[1].troop_slot_count = 1;
    s.nodes[0].troop_slots[0] = p2;
    s.nodes[0].spies[0] = p1;
    s.nodes[0].spy_count = 1;

    CardAction action;
    memset(&action, 0, sizeof(action));
    action.op = intern("move_troop");

    const CardOp *op = op_lookup(intern("move_troop"));
    assert(op != NULL);
    assert(op->needs_selection);
    assert(op->enumerate != NULL);
    assert(op->target_from_move != NULL);
    assert(op->apply != NULL);
    assert(op->describe != NULL);

    Move out[8];
    memset(out, 0, sizeof(out));
    int n = legal_generic_target_selection_moves(&s, p1, NULL, NULL, &action, out, 8);
    assert(n == 1);
    assert(out[0].data.resolve_generic.action_id == site_a);
    const char *tid = intern_str(out[0].data.resolve_generic.target_id);
    assert(tid && strcmp(tid, "0:site_b:0") == 0);

    OpTarget target;
    memset(&target, 0, sizeof(target));
    assert(op->target_from_move(&s, p1, &action, &out[0], &target));
    assert(target.kind == OP_TARGET_MOVE_TROOP);
    assert(target.as.move_troop.source_node_id == site_a);
    assert(target.as.move_troop.source_slot_index == 0);
    assert(target.as.move_troop.target_node_id == site_b);
    assert(target.as.move_troop.target_slot_index == 0);

    const char *ids[2] = {"site_a", "site_b"};
    const char *labels[2] = {"A", "B"};
    char label[96];
    label[0] = '\0';
    op->describe(&s, &action, &target, ids, labels, 2, label, sizeof(label));
    assert(strcmp(label, "Move Player 2 troop from A to B") == 0);

    assert(op->apply(&s, p1, NULL, &action, &target) == &s);
    assert(s.nodes[0].troop_slots[0] == SYM_NULL);
    assert(s.nodes[1].troop_slots[0] == p2);

    printf("PASS: move_troop op owns source/destination target, apply and describe\n");
}

static void test_op_assassinate_troop(void) {
    Sym p1 = intern("p1");
    Sym p2 = intern("p2");
    Sym site_a = intern("site_a");
    Sym kind_site = intern("site");

    NodeDefinition board_nodes[1];
    memset(board_nodes, 0, sizeof(board_nodes));
    board_nodes[0].node_id = site_a;
    board_nodes[0].kind = kind_site;

    BoardDefinition board;
    memset(&board, 0, sizeof(board));
    board.nodes = board_nodes;
    board.node_count = 1;

    GameDefinition def;
    memset(&def, 0, sizeof(def));
    def.board = board;

    GameState s;
    memset(&s, 0, sizeof(s));
    s.definition = &def;
    s.player_count = 2;
    s.players[0].player_id = p1;
    s.players[1].player_id = p2;
    s.node_count = 1;
    s.nodes[0].node_id = site_a;
    s.nodes[0].troop_slot_count = 1;
    s.nodes[0].troop_slots[0] = p2;
    s.nodes[0].spies[0] = p1;
    s.nodes[0].spy_count = 1;

    CardAction action;
    memset(&action, 0, sizeof(action));
    action.op = intern("assassinate_troop");

    const CardOp *op = op_lookup(intern("assassinate_troop"));
    assert(op != NULL);
    assert(op->needs_selection);
    assert(op->enumerate != NULL);
    assert(op->target_from_move != NULL);
    assert(op->apply != NULL);
    assert(op->describe != NULL);

    Move out[8];
    memset(out, 0, sizeof(out));
    int n = legal_generic_target_selection_moves(&s, p1, NULL, NULL, &action, out, 8);
    assert(n == 1);
    assert(out[0].data.resolve_generic.action_id == site_a);
    const char *tid = intern_str(out[0].data.resolve_generic.target_id);
    assert(tid && strcmp(tid, "0") == 0);

    OpTarget target;
    memset(&target, 0, sizeof(target));
    assert(op->target_from_move(&s, p1, &action, &out[0], &target));
    assert(target.kind == OP_TARGET_TROOP_SLOT);
    assert(target.as.troop_slot.node_id == site_a);
    assert(target.as.troop_slot.slot_index == 0);

    const char *ids[1] = {"site_a"};
    const char *labels[1] = {"A"};
    char label[96];
    label[0] = '\0';
    op->describe(&s, &action, &target, ids, labels, 1, label, sizeof(label));
    assert(strcmp(label, "Assassinate Player 2 troop at A") == 0);

    assert(op->apply(&s, p1, NULL, &action, &target) == &s);
    assert(s.nodes[0].troop_slots[0] == SYM_NULL);
    assert(s.players[0].trophy_hall_count == 1);
    assert(s.players[0].trophy_hall[0] == p2);

    printf("PASS: assassinate_troop op owns node/slot target, apply and describe\n");
}

static void test_op_supplant_troop(void) {
    Sym p1 = intern("p1");
    Sym p2 = intern("p2");
    Sym site_a = intern("site_a");
    Sym kind_site = intern("site");

    NodeDefinition board_nodes[1];
    memset(board_nodes, 0, sizeof(board_nodes));
    board_nodes[0].node_id = site_a;
    board_nodes[0].kind = kind_site;

    BoardDefinition board;
    memset(&board, 0, sizeof(board));
    board.nodes = board_nodes;
    board.node_count = 1;

    GameDefinition def;
    memset(&def, 0, sizeof(def));
    def.board = board;

    GameState s;
    memset(&s, 0, sizeof(s));
    s.definition = &def;
    s.player_count = 2;
    s.players[0].player_id = p1;
    s.players[1].player_id = p2;
    s.node_count = 1;
    s.nodes[0].node_id = site_a;
    s.nodes[0].troop_slot_count = 1;
    s.nodes[0].troop_slots[0] = p2;
    s.nodes[0].spies[0] = p1;
    s.nodes[0].spy_count = 1;

    CardAction action;
    memset(&action, 0, sizeof(action));
    action.op = intern("supplant_troop");

    const CardOp *op = op_lookup(intern("supplant_troop"));
    assert(op != NULL);
    assert(op->needs_selection);
    assert(op->enumerate != NULL);
    assert(op->target_from_move != NULL);
    assert(op->apply != NULL);
    assert(op->describe != NULL);

    Move out[8];
    memset(out, 0, sizeof(out));
    int n = legal_generic_target_selection_moves(&s, p1, NULL, NULL, &action, out, 8);
    assert(n == 1);
    assert(out[0].data.resolve_generic.action_id == site_a);
    const char *tid = intern_str(out[0].data.resolve_generic.target_id);
    assert(tid && strcmp(tid, "0") == 0);

    OpTarget target;
    memset(&target, 0, sizeof(target));
    assert(op->target_from_move(&s, p1, &action, &out[0], &target));
    assert(target.kind == OP_TARGET_TROOP_SLOT);
    assert(target.as.troop_slot.node_id == site_a);
    assert(target.as.troop_slot.slot_index == 0);

    const char *ids[1] = {"site_a"};
    const char *labels[1] = {"A"};
    char label[96];
    label[0] = '\0';
    op->describe(&s, &action, &target, ids, labels, 1, label, sizeof(label));
    assert(strcmp(label, "Supplant Player 2 troop at A") == 0);

    assert(op->apply(&s, p1, NULL, &action, &target) == &s);
    assert(s.nodes[0].troop_slots[0] == SYM_NULL);
    assert(s.players[0].trophy_hall_count == 1);
    assert(s.players[0].trophy_hall[0] == p2);
    assert(s.players[0].score == 1);

    printf("PASS: supplant_troop op owns node/slot target, apply and describe\n");
}

static void test_op_force_discard(void) {
    Sym p1 = intern("p1");
    Sym p2 = intern("p2");

    CardCatalog catalog;
    memset(&catalog, 0, sizeof(catalog));
    GameDefinition def;
    memset(&def, 0, sizeof(def));
    def.catalog = catalog;

    GameState s;
    memset(&s, 0, sizeof(s));
    s.definition = &def;
    s.player_count = 2;
    s.players[0].player_id = p1;
    s.players[1].player_id = p2;
    s.players[1].hand_count = 3;
    s.players[1].hand[0] = intern("card_a");
    s.players[1].hand[1] = intern("card_b");
    s.players[1].hand[2] = intern("card_c");
    s.shuffle_seed = 0;
    s.shuffle_counter = 0;

    CardAction action;
    memset(&action, 0, sizeof(action));
    action.op = intern("force_discard");
    action.source_fragment = intern("targeted_discard");

    const CardOp *op = op_lookup(intern("force_discard"));
    assert(op != NULL);
    assert(op->needs_selection);
    assert(op->enumerate != NULL);
    assert(op->target_from_move != NULL);
    assert(op->apply != NULL);
    assert(op->describe != NULL);
    assert(action_requires_selection(&action) == 1);

    Move out[8];
    memset(out, 0, sizeof(out));
    int n = legal_generic_target_selection_moves(&s, p1, NULL, NULL, &action, out, 8);
    assert(n == 1);
    assert(out[0].data.resolve_generic.action_id == p2);

    OpTarget target;
    memset(&target, 0, sizeof(target));
    assert(op->target_from_move(&s, p1, &action, &out[0], &target));
    assert(target.kind == OP_TARGET_FORCE_DISCARD);
    assert(target.as.force_discard.target_player_id == p2);
    assert(target.as.force_discard.target_card_id == SYM_NULL);

    char label[96];
    label[0] = '\0';
    op->describe(&s, &action, &target, NULL, NULL, 0, label, sizeof(label));
    assert(strcmp(label, "Force Player 2 to discard") == 0);

    assert(op->apply(&s, p1, NULL, &action, &target) == &s);
    assert(s.players[1].hand_count == 2);
    assert(s.players[1].discard_pile_count == 1);

    printf("PASS: force_discard op owns player target, RNG discard and describe\n");
}

static void test_op_recruit_card(void) {
    Sym p1 = intern("p1");
    Sym card_a = intern("card_a");

    CardDefinition card;
    memset(&card, 0, sizeof(card));
    card.card_id = card_a;
    card.name = intern("Test Card");
    card.cost = 1;

    CardCatalog catalog;
    memset(&catalog, 0, sizeof(catalog));
    catalog.cards = &card;
    catalog.card_count = 1;

    GameDefinition def;
    memset(&def, 0, sizeof(def));
    def.catalog = catalog;

    GameState s;
    memset(&s, 0, sizeof(s));
    s.definition = &def;
    s.player_count = 1;
    s.players[0].player_id = p1;
    s.market.row_count = 1;
    s.market.row[0] = card_a;
    s.resource_pool.influence = 1;

    CardAction action;
    memset(&action, 0, sizeof(action));
    action.op = intern("recruit_card");

    const CardOp *op = op_lookup(intern("recruit_card"));
    assert(op != NULL);
    assert(op->needs_selection);
    assert(op->enumerate != NULL);
    assert(op->target_from_move != NULL);
    assert(op->apply != NULL);
    assert(op->describe != NULL);

    Move out[8];
    memset(out, 0, sizeof(out));
    int n = legal_generic_target_selection_moves(&s, p1, NULL, NULL, &action, out, 8);
    assert(n == 1);
    assert(out[0].data.resolve_generic.action_id == card_a);

    OpTarget target;
    memset(&target, 0, sizeof(target));
    assert(op->target_from_move(&s, p1, &action, &out[0], &target));
    assert(target.kind == OP_TARGET_RECRUIT_CARD);
    assert(target.as.recruit_card.target_card_id == card_a);

    char label[96];
    label[0] = '\0';
    op->describe(&s, &action, &target, NULL, NULL, 0, label, sizeof(label));
    assert(strcmp(label, "Recruit Test Card") == 0);

    assert(op->apply(&s, p1, NULL, &action, &target) == &s);
    assert(s.players[0].discard_pile_count == 1);
    assert(s.players[0].discard_pile[0] == card_a);
    assert(s.resource_pool.influence == 0);
    assert(s.market.row_count == 0);

    printf("PASS: recruit_card op owns market target, apply and describe\n");
}

static void test_op_devour(void) {
    Sym p1 = intern("p1");
    Sym card_a = intern("card_a");

    CardDefinition card;
    memset(&card, 0, sizeof(card));
    card.card_id = card_a;
    card.name = intern("Test Card");

    CardCatalog catalog;
    memset(&catalog, 0, sizeof(catalog));
    catalog.cards = &card;
    catalog.card_count = 1;

    GameDefinition def;
    memset(&def, 0, sizeof(def));
    def.catalog = catalog;

    GameState s;
    memset(&s, 0, sizeof(s));
    s.definition = &def;
    s.player_count = 1;
    s.players[0].player_id = p1;
    s.players[0].hand_count = 1;
    s.players[0].hand[0] = card_a;

    CardAction action;
    memset(&action, 0, sizeof(action));
    action.op = intern("devour");
    action.target_scope = intern("hand");

    const CardOp *op = op_lookup(intern("devour"));
    assert(op != NULL);
    assert(op->needs_selection);
    assert(op->enumerate != NULL);
    assert(op->target_from_move != NULL);
    assert(op->apply != NULL);
    assert(op->describe != NULL);
    const CardOp *cost_op = op_lookup(intern("devour_cost"));
    assert(cost_op != NULL);
    assert(cost_op->needs_selection);
    assert(cost_op->enumerate != NULL);
    assert(cost_op->target_from_move != NULL);
    assert(cost_op->apply != NULL);
    assert(cost_op->describe != NULL);

    Move out[8];
    memset(out, 0, sizeof(out));
    int n = legal_generic_target_selection_moves(&s, p1, NULL, NULL, &action, out, 8);
    assert(n == 1);
    assert(out[0].data.resolve_generic.action_id == card_a);

    OpTarget target;
    memset(&target, 0, sizeof(target));
    assert(op->target_from_move(&s, p1, &action, &out[0], &target));
    assert(target.kind == OP_TARGET_DEVOUR);
    assert(target.as.devour.target_card_id == card_a);

    char label[96];
    label[0] = '\0';
    op->describe(&s, &action, &target, NULL, NULL, 0, label, sizeof(label));
    assert(strcmp(label, "Devour Test Card") == 0);

    assert(op->apply(&s, p1, NULL, &action, &target) == &s);
    assert(s.players[0].hand_count == 0);
    assert(s.devour_pile_count == 1);
    assert(s.devour_pile[0] == card_a);

    printf("PASS: devour op owns hand target, apply and describe\n");
}

static void test_op_play_card(void) {
    Sym p1 = intern("p1");
    Sym card_a = intern("card_a");

    CardDefinition card;
    memset(&card, 0, sizeof(card));
    card.card_id = card_a;
    card.name = intern("Test Card");
    card.effect_key = intern("generic_card");

    CardCatalog catalog;
    memset(&catalog, 0, sizeof(catalog));
    catalog.cards = &card;
    catalog.card_count = 1;

    GameDefinition def;
    memset(&def, 0, sizeof(def));
    def.catalog = catalog;

    GameState s;
    memset(&s, 0, sizeof(s));
    s.definition = &def;
    s.player_count = 1;
    s.players[0].player_id = p1;
    s.players[0].inner_circle_count = 1;
    s.players[0].inner_circle[0] = card_a;

    CardAction action;
    memset(&action, 0, sizeof(action));
    action.op = intern("play_card");
    action.source_fragment = intern("play_from_inner_circle_without_removal");

    const CardOp *op = op_lookup(intern("play_card"));
    assert(op != NULL);
    assert(op->needs_selection);
    assert(op->enumerate != NULL);
    assert(op->target_from_move != NULL);
    assert(op->apply != NULL);
    assert(op->describe != NULL);
    assert(action_requires_selection(&action) == 1);

    Move out[8];
    memset(out, 0, sizeof(out));
    int n = legal_generic_target_selection_moves(&s, p1, NULL, NULL, &action, out, 8);
    assert(n == 1);
    assert(out[0].data.resolve_generic.action_id == card_a);

    OpTarget target;
    memset(&target, 0, sizeof(target));
    assert(op->target_from_move(&s, p1, &action, &out[0], &target));
    assert(target.kind == OP_TARGET_PLAY_CARD);
    assert(target.as.play_card.from_inner_circle == 1);
    assert(target.as.play_card.inner_circle_index == 0);
    assert(target.as.play_card.target_card_id == card_a);

    char label[96];
    label[0] = '\0';
    op->describe(&s, &action, &target, NULL, NULL, 0, label, sizeof(label));
    assert(strcmp(label, "Play Test Card") == 0);

    GameState *result = op->apply(&s, p1, NULL, &action, &target);
    assert(result != NULL);

    printf("PASS: play_card op owns inner/market target, apply and describe\n");
}

static void test_op_promote_card(void) {
    Sym p1 = intern("p1");
    Sym card_a = intern("card_a");

    CardDefinition card;
    memset(&card, 0, sizeof(card));
    card.card_id = card_a;
    card.name = intern("Test Card");

    CardCatalog catalog;
    memset(&catalog, 0, sizeof(catalog));
    catalog.cards = &card;
    catalog.card_count = 1;

    GameDefinition def;
    memset(&def, 0, sizeof(def));
    def.catalog = catalog;

    GameState s;
    memset(&s, 0, sizeof(s));
    s.definition = &def;
    s.player_count = 1;
    s.players[0].player_id = p1;
    s.players[0].discard_pile_count = 1;
    s.players[0].discard_pile[0] = card_a;

    CardAction action;
    memset(&action, 0, sizeof(action));
    action.op = intern("promote_card");
    action.source_fragment = intern("promote_from_discard");

    const CardOp *op = op_lookup(intern("promote_card"));
    assert(op != NULL);
    assert(op->needs_selection);
    assert(op->enumerate != NULL);
    assert(op->target_from_move != NULL);
    assert(op->apply != NULL);
    assert(op->describe != NULL);
    assert(action_requires_selection(&action) == 1);

    Move out[8];
    memset(out, 0, sizeof(out));
    int n = legal_generic_target_selection_moves(&s, p1, NULL, NULL, &action, out, 8);
    assert(n == 1);
    assert(out[0].data.resolve_generic.action_id == card_a);

    OpTarget target;
    memset(&target, 0, sizeof(target));
    assert(op->target_from_move(&s, p1, &action, &out[0], &target));
    assert(target.kind == OP_TARGET_PROMOTE_CARD);
    assert(target.as.promote_card.target_card_id == card_a);

    char label[96];
    label[0] = '\0';
    op->describe(&s, &action, &target, NULL, NULL, 0, label, sizeof(label));
    assert(strcmp(label, "Promote Test Card") == 0);

    assert(op->apply(&s, p1, NULL, &action, &target) == &s);
    assert(s.players[0].discard_pile_count == 0);
    assert(s.players[0].inner_circle_count == 1);
    assert(s.players[0].inner_circle[0] == card_a);

    printf("PASS: promote_card op owns discard target, apply and describe\n");
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
    test_op_return_spy();
    test_op_place_spy();
    test_op_return_unit();
    test_op_deploy_troops();
    test_op_move_troop();
    test_op_assassinate_troop();
    test_op_supplant_troop();
    test_op_force_discard();
    test_op_recruit_card();
    test_op_devour();
    test_op_play_card();
    test_op_promote_card();
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

