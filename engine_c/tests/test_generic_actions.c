#include "generic_runtime.h"
#include "intern.h"
#include "moves.h"
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

int main(void) {
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
    printf("All generic action tests passed.\n");
    return 0;
}
