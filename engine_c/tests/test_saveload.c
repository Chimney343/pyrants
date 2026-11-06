#include "saveload.h"
#include "engine.h"
#include "loader.h"
#include "intern.h"
#include "arena.h"
#include "catalog_dir.h"
#include "pending.h"
#include <stdio.h>
#include <assert.h>
#include <string.h>

static void test_serialize_basic(void) {
    intern_init(4096);
    Arena *arena = arena_create(2 * 1024 * 1024);
    assert(arena);

    GameDefinition *def = test_load_definition(arena);
    assert(def);

    const char *player_ids[] = {"p1", "p2"};
    GameState *gs = engine_create_game_definition(def, player_ids, 2, 42);
    assert(gs);

    char json[128 * 1024];
    int needed = engine_serialize_state(gs, "data/cards",
                                         "data/boards/tyrants_of_the_underdark.json",
                                         "data/decks/base_setup.json",
                                         0, 0, json, sizeof(json));
    assert(needed > 0);
    assert(needed < (int)sizeof(json));
    assert(strstr(json, "\"scenario_id\"") != NULL);
    assert(strstr(json, "\"move_count\"") != NULL);
    assert(strstr(json, "\"state\"") != NULL);
    printf("serialize needed=%d, starts: %.80s...\n", needed, json);

    engine_destroy(gs);
    arena_destroy(arena);
    intern_destroy();
}

static void test_deserialize_round_trip(void) {
    intern_init(4096);
    Arena *arena = arena_create(2 * 1024 * 1024);
    assert(arena);

    GameDefinition *def = test_load_definition(arena);
    assert(def);

    const char *player_ids[] = {"p1", "p2"};
    GameState *gs = engine_create_game_definition(def, player_ids, 2, 42);
    assert(gs);

    const char *board_path, *setup_path;
    test_board_setup_paths(&board_path, &setup_path);

    char json[128 * 1024];
    int needed = engine_serialize_state(gs, "data/cards", board_path, setup_path,
                                         0, 0, json, sizeof(json));
    assert(needed > 0);

    Arena *arena2 = arena_create(2 * 1024 * 1024);
    assert(arena2);
    char *catalog_json = test_load_catalog_json_both();
    assert(catalog_json);
    int restored_move_count = -1;
    GameState *restored = engine_deserialize_state(json, catalog_json, arena2, &restored_move_count);
    free(catalog_json);
    assert(restored);
    assert(restored_move_count == 0);
    assert(restored->player_count == gs->player_count);
    assert(restored->round_number == gs->round_number);
    assert(restored->phase == gs->phase);
    assert(restored->node_count == gs->node_count);

    printf("PASS: deserialize_round_trip (move_count=%d, player_count=%d)\n",
           restored_move_count, restored->player_count);

    engine_destroy(restored);
    arena_destroy(arena2);
    engine_destroy(gs);
    arena_destroy(arena);
    intern_destroy();
}

static void test_serialize_needed_size(void) {
    intern_init(4096);
    Arena *arena = arena_create(2 * 1024 * 1024);
    assert(arena);

    GameDefinition *def = test_load_definition(arena);
    assert(def);

    const char *player_ids[] = {"p1", "p2"};
    GameState *gs = engine_create_game_definition(def, player_ids, 2, 42);
    assert(gs);

    int needed = engine_serialize_state(gs, "data/cards",
                                         "data/boards/tyrants_of_the_underdark.json",
                                         "data/decks/base_setup.json",
                                         0, 0, NULL, 0);
    assert(needed > 0);
    printf("needed buffer size: %d\n", needed);

    engine_destroy(gs);
    arena_destroy(arena);
    intern_destroy();
}

static const CardDefinition *find_card(const GameDefinition *def, const char *card_id) {
    Sym id = intern(card_id);
    for (int i = 0; i < def->catalog.card_count; i++)
        if (def->catalog.cards[i].card_id == id) return &def->catalog.cards[i];
    return NULL;
}

/* Serialize `gs`, reload it, and hand the restored state back. The caller
 * owns the restored state (engine_destroy) and the reload arena (*out_arena),
 * which must outlive the state: the restored state points into it. */
static GameState *round_trip(GameState *gs, const char *catalog_json,
                             char *out_json, int out_cap, Arena **out_arena) {
    const char *board_path, *setup_path;
    test_board_setup_paths(&board_path, &setup_path);

    int needed = engine_serialize_state(gs, "data/cards", board_path, setup_path,
                                         0, 0, out_json, out_cap);
    assert(needed > 0);
    assert(needed < out_cap);

    Arena *arena2 = arena_create(2 * 1024 * 1024);
    assert(arena2);
    int restored_move_count = -1;
    GameState *restored = engine_deserialize_state(out_json, catalog_json, arena2,
                                                    &restored_move_count);
    assert(restored);
    *out_arena = arena2;
    return restored;
}

static void test_schema_v2_markers(void) {
    intern_init(4096);
    Arena *arena = arena_create(2 * 1024 * 1024);
    assert(arena);

    GameDefinition *def = test_load_definition(arena);
    assert(def);

    const char *player_ids[] = {"p1", "p2"};
    GameState *gs = engine_create_game_definition(def, player_ids, 2, 42);
    assert(gs);

    char json[128 * 1024];
    int needed = engine_serialize_state(gs, "data/cards",
                                         "data/boards/tyrants_of_the_underdraft.json",
                                         "data/decks/base_setup.json",
                                         0, 0, json, sizeof(json));
    assert(needed > 0);

    cJSON *root = cJSON_Parse(json);
    assert(root);

    const cJSON *version = cJSON_GetObjectItem(root, "schema_version");
    assert(version);
    assert((int)version->valuedouble == 2);

    const cJSON *state_obj = cJSON_GetObjectItem(root, "state");
    assert(state_obj);

    const cJSON *pending = cJSON_GetObjectItem(state_obj, "pending");
    assert(pending);
    const cJSON *kind = cJSON_GetObjectItem(pending, "kind");
    assert(kind);
    assert(strcmp(kind->valuestring, "none") == 0);

    assert(cJSON_GetObjectItem(state_obj, "shuffle_seed"));
    assert(cJSON_GetObjectItem(state_obj, "shuffle_counter"));

    cJSON_Delete(root);
    printf("PASS: schema_v2_markers\n");

    engine_destroy(gs);
    arena_destroy(arena);
    intern_destroy();
}

static void test_pending_immediate_round_trip(void) {
    intern_init(4096);
    Arena *arena = arena_create(2 * 1024 * 1024);
    assert(arena);

    GameDefinition *def = test_load_definition(arena);
    assert(def);

    const char *player_ids[] = {"p1", "p2"};
    GameState *gs = engine_create_game_definition(def, player_ids, 2, 42);
    assert(gs);

    PendingPromotionState promo;
    memset(&promo, 0, sizeof(promo));
    promo.card_id = intern("noble");
    promo.timing = intern("immediate");
    promo.optional = 1;
    promo.source_card_id = intern("noble");
    assert(pending_promotion_push(gs, PENDING_IMMEDIATE, &promo) == 1);
    gs->phase = PHASE_MAIN;

    PendingDecision decision = pending_peek(gs);
    assert(decision.kind == PENDING_IMMEDIATE);
    assert(decision.count == 1);

    char *catalog_json = test_load_catalog_json_both();
    assert(catalog_json);
    char json[128 * 1024];
    Arena *reload_arena = NULL;
    GameState *restored = round_trip(gs, catalog_json, json, sizeof(json), &reload_arena);
    free(catalog_json);

    assert(pending_promotion_count(restored, PENDING_IMMEDIATE) == 1);
    const PendingPromotionState *rp = pending_promotion_at(restored, PENDING_IMMEDIATE, 0);
    assert(rp);
    assert(rp->card_id == intern("noble"));
    assert(rp->timing == intern("immediate"));
    assert(rp->optional == 1);
    assert(rp->deferred_choice == 0);
    assert(rp->source_card_id == intern("noble"));
    assert(pending_peek(restored).kind == PENDING_IMMEDIATE);
    printf("PASS: pending_immediate_round_trip\n");

    engine_destroy(restored);
    arena_destroy(reload_arena);
    engine_destroy(gs);
    arena_destroy(arena);
    intern_destroy();
}

static void test_pending_eot_round_trip(void) {
    intern_init(4096);
    Arena *arena = arena_create(2 * 1024 * 1024);
    assert(arena);

    GameDefinition *def = test_load_definition(arena);
    assert(def);

    const char *player_ids[] = {"p1", "p2"};
    GameState *gs = engine_create_game_definition(def, player_ids, 2, 42);
    assert(gs);

    PendingPromotionState promo;
    memset(&promo, 0, sizeof(promo));
    promo.card_id = intern("noble");
    promo.timing = intern("end_of_turn");
    promo.optional = 1;
    promo.deferred_choice = 1;
    promo.source_card_id = intern("noble");
    promo.requires_another_played_card = 1;
    promo.required_aspect = intern("guile");
    promo.required_secondary_aspect = intern("arcane");
    promo.focus_aspect = intern("might");
    promo.repeat_while_targets = 1;
    promo.promotions_remaining = 3;
    assert(pending_promotion_push(gs, PENDING_EOT, &promo) == 1);
    gs->phase = PHASE_END_OF_TURN;

    char *catalog_json = test_load_catalog_json_both();
    assert(catalog_json);
    char json[128 * 1024];
    Arena *reload_arena = NULL;
    GameState *restored = round_trip(gs, catalog_json, json, sizeof(json), &reload_arena);
    free(catalog_json);

    assert(pending_promotion_count(restored, PENDING_EOT) == 1);
    const PendingPromotionState *rp = pending_promotion_at(restored, PENDING_EOT, 0);
    assert(rp);
    assert(rp->card_id == intern("noble"));
    assert(rp->timing == intern("end_of_turn"));
    assert(rp->optional == 1);
    assert(rp->deferred_choice == 1);
    assert(rp->source_card_id == intern("noble"));
    assert(rp->requires_another_played_card == 1);
    assert(rp->required_aspect == intern("guile"));
    assert(rp->required_secondary_aspect == intern("arcane"));
    assert(rp->focus_aspect == intern("might"));
    assert(rp->repeat_while_targets == 1);
    assert(rp->promotions_remaining == 3);
    printf("PASS: pending_eot_round_trip\n");

    engine_destroy(restored);
    arena_destroy(reload_arena);
    engine_destroy(gs);
    arena_destroy(arena);
    intern_destroy();
}

static void test_pending_ability_round_trip(void) {
    intern_init(4096);
    Arena *arena = arena_create(2 * 1024 * 1024);
    assert(arena);

    GameDefinition *def = test_load_definition(arena);
    assert(def);

    const char *player_ids[] = {"p1", "p2"};
    GameState *gs = engine_create_game_definition(def, player_ids, 2, 42);
    assert(gs);

    PendingAbilityState *ability = arena_calloc((Arena *)gs->arena, 1,
                                                sizeof(PendingAbilityState));
    assert(ability);
    ability->card_id = intern("noble");
    ability->ability_key = intern("ability_1");
    ability->resolved = 0;
    gs->pending_ability = ability;
    gs->phase = PHASE_MAIN;

    char *catalog_json = test_load_catalog_json_both();
    assert(catalog_json);
    char json[128 * 1024];
    Arena *reload_arena = NULL;
    GameState *restored = round_trip(gs, catalog_json, json, sizeof(json), &reload_arena);
    free(catalog_json);

    assert(restored->pending_ability);
    assert(restored->pending_ability->card_id == intern("noble"));
    assert(restored->pending_ability->ability_key == intern("ability_1"));
    assert(restored->pending_ability->resolved == 0);
    printf("PASS: pending_ability_round_trip\n");

    engine_destroy(restored);
    arena_destroy(reload_arena);
    engine_destroy(gs);
    arena_destroy(arena);
    intern_destroy();
}

static void test_pending_generic_round_trip(void) {
    intern_init(4096);
    Arena *arena = arena_create(2 * 1024 * 1024);
    assert(arena);

    GameDefinition *def = test_load_definition(arena);
    assert(def);

    const CardDefinition *noble = find_card(def, "noble");
    assert(noble);
    assert(noble->execution.action_count > 0);

    const char *player_ids[] = {"p1", "p2"};
    GameState *gs = engine_create_game_definition(def, player_ids, 2, 42);
    assert(gs);

    Arena *state_arena = (Arena *)gs->arena;
    PendingGenericChoiceState *parent = arena_calloc(state_arena, 1,
                                                     sizeof(PendingGenericChoiceState));
    assert(parent);
    parent->source_card_id = intern("noble");
    parent->exec_kind = EXEC_SEQUENCE;
    parent->current_actions = noble->execution.actions;
    parent->current_action_count = noble->execution.action_count;
    parent->next_action_index = 0;

    PendingGenericChoiceState *pg = arena_calloc(state_arena, 1,
                                                  sizeof(PendingGenericChoiceState));
    assert(pg);
    pg->source_card_id = intern("noble");
    pg->exec_kind = EXEC_SEQUENCE;
    pg->current_actions = noble->execution.actions;
    pg->current_action_count = noble->execution.action_count;
    pg->next_action_index = 2;
    pg->parent = parent;
    pg->last_played_card_id = intern("noble");
    gs->pending_generic = pg;
    gs->phase = PHASE_MAIN;

    char *catalog_json = test_load_catalog_json_both();
    assert(catalog_json);
    char json[128 * 1024];
    Arena *reload_arena = NULL;
    GameState *restored = round_trip(gs, catalog_json, json, sizeof(json), &reload_arena);
    free(catalog_json);

    assert(restored->pending_generic);
    assert(restored->pending_generic->source_card_id == intern("noble"));
    assert(restored->pending_generic->next_action_index == 2);
    assert(restored->pending_generic->last_played_card_id == intern("noble"));
    assert(restored->pending_generic->current_actions);
    assert(restored->pending_generic->current_action_count == noble->execution.action_count);
    assert(restored->pending_generic->parent);
    assert(restored->pending_generic->parent->source_card_id == intern("noble"));
    assert(restored->pending_generic->parent->current_actions);
    assert(restored->pending_generic->parent->current_action_count ==
           noble->execution.action_count);
    printf("PASS: pending_generic_round_trip\n");

    engine_destroy(restored);
    arena_destroy(reload_arena);
    engine_destroy(gs);
    arena_destroy(arena);
    intern_destroy();
}

static void test_shuffle_stream_round_trip(void) {
    intern_init(4096);
    Arena *arena = arena_create(2 * 1024 * 1024);
    assert(arena);

    GameDefinition *def = test_load_definition(arena);
    assert(def);

    const char *player_ids[] = {"p1", "p2"};
    GameState *gs = engine_create_game_definition(def, player_ids, 2, 4242);
    assert(gs);
    gs->shuffle_seed = 9876543210123ULL;
    gs->shuffle_counter = 17;

    char *catalog_json = test_load_catalog_json_both();
    assert(catalog_json);
    char json[128 * 1024];
    Arena *reload_arena = NULL;
    GameState *restored = round_trip(gs, catalog_json, json, sizeof(json), &reload_arena);
    free(catalog_json);

    assert(restored->shuffle_seed == 9876543210123ULL);
    assert(restored->shuffle_counter == 17);
    printf("PASS: shuffle_stream_round_trip\n");

    engine_destroy(restored);
    arena_destroy(reload_arena);
    engine_destroy(gs);
    arena_destroy(arena);
    intern_destroy();
}

static void test_schema_v1_loads_without_pending(void) {
    intern_init(4096);
    Arena *arena = arena_create(2 * 1024 * 1024);
    assert(arena);

    GameDefinition *def = test_load_definition(arena);
    assert(def);

    const char *player_ids[] = {"p1", "p2"};
    GameState *gs = engine_create_game_definition(def, player_ids, 2, 42);
    assert(gs);

    PendingPromotionState promo;
    memset(&promo, 0, sizeof(promo));
    promo.card_id = intern("noble");
    promo.timing = intern("immediate");
    promo.optional = 1;
    assert(pending_promotion_push(gs, PENDING_IMMEDIATE, &promo) == 1);

    const char *board_path, *setup_path;
    test_board_setup_paths(&board_path, &setup_path);
    char json[128 * 1024];
    int needed = engine_serialize_state(gs, "data/cards", board_path, setup_path,
                                         0, 0, json, sizeof(json));
    assert(needed > 0);

    /* Strip the v2 additions to reproduce a schema-v1 document. */
    cJSON *root = cJSON_Parse(json);
    assert(root);
    cJSON *state_obj = cJSON_GetObjectItem(root, "state");
    assert(state_obj);
    cJSON_DeleteItemFromObject(state_obj, "pending");
    cJSON_DeleteItemFromObject(state_obj, "shuffle_seed");
    cJSON_DeleteItemFromObject(state_obj, "shuffle_counter");
    char *legacy = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);
    assert(legacy);

    char *catalog_json = test_load_catalog_json_both();
    assert(catalog_json);
    Arena *arena2 = arena_create(2 * 1024 * 1024);
    assert(arena2);
    int restored_move_count = -1;
    GameState *restored = engine_deserialize_state(legacy, catalog_json, arena2,
                                                    &restored_move_count);
    free(catalog_json);
    free(legacy);
    assert(restored);
    assert(restored->player_count == gs->player_count);

    assert(pending_promotion_count(restored, PENDING_IMMEDIATE) == 0);
    assert(pending_promotion_count(restored, PENDING_EOT) == 0);
    assert(restored->pending_ability == NULL);
    assert(restored->pending_generic == NULL);
    assert(pending_peek(restored).kind == PENDING_NONE);
    printf("PASS: schema_v1_loads_without_pending\n");

    engine_destroy(restored);
    arena_destroy(arena2);
    engine_destroy(gs);
    arena_destroy(arena);
    intern_destroy();
}

static void test_pending_hash_and_describe(void) {
    intern_init(4096);
    Arena *arena = arena_create(2 * 1024 * 1024);
    assert(arena);

    GameDefinition *def = test_load_definition(arena);
    assert(def);

    const char *player_ids[] = {"p1", "p2"};
    GameState *gs = engine_create_game_definition(def, player_ids, 2, 42);
    assert(gs);

    PendingPromotionState promo;
    memset(&promo, 0, sizeof(promo));
    promo.card_id = intern("noble");
    promo.timing = intern("immediate");
    promo.optional = 1;
    assert(pending_promotion_push(gs, PENDING_IMMEDIATE, &promo) == 1);
    gs->phase = PHASE_MAIN;

    uint64_t original = pending_hash(gs);

    GameState *clone = engine_clone(gs);
    assert(clone);
    assert(pending_hash(clone) == original);

    char *catalog_json = test_load_catalog_json_both();
    assert(catalog_json);
    char json[128 * 1024];
    Arena *reload_arena = NULL;
    GameState *restored = round_trip(gs, catalog_json, json, sizeof(json), &reload_arena);
    free(catalog_json);
    assert(pending_hash(restored) == original);

    char description[128];
    pending_describe(gs, description, sizeof(description));
    assert(strstr(description, "immediate") != NULL);
    assert(strstr(description, "noble") != NULL);
    printf("PASS: pending_hash_and_describe (%s)\n", description);

    engine_destroy(restored);
    arena_destroy(reload_arena);
    engine_destroy(clone);
    engine_destroy(gs);
    arena_destroy(arena);
    intern_destroy();
}

int main(void) {
    test_serialize_basic();
    test_deserialize_round_trip();
    test_serialize_needed_size();
    test_schema_v2_markers();
    test_pending_immediate_round_trip();
    test_pending_eot_round_trip();
    test_pending_ability_round_trip();
    test_pending_generic_round_trip();
    test_shuffle_stream_round_trip();
    test_schema_v1_loads_without_pending();
    test_pending_hash_and_describe();
    printf("All saveload tests passed.\n");
    return 0;
}
