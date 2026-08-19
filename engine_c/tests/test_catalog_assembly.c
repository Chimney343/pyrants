#include "engine.h"
#include "loader.h"
#include "intern.h"
#include "arena.h"
#include "catalog_dir.h"
#include "cJSON.h"
#include <stdio.h>
#include <assert.h>
#include <string.h>

#define EXPECTED_CARD_COUNT 125

static void test_assembled_json_contents(void) {
    char *json = test_load_catalog_json_both();
    assert(json != NULL);

    cJSON *root = cJSON_Parse(json);
    assert(root != NULL);

    cJSON *cid = cJSON_GetObjectItem(root, "catalog_id");
    assert(cid != NULL && cJSON_IsString(cid));
    assert(strcmp(cid->valuestring, "base_catalog") == 0);

    cJSON *cards = cJSON_GetObjectItem(root, "cards");
    assert(cards != NULL && cJSON_IsArray(cards));
    int n = cJSON_GetArraySize(cards);
    assert(n == EXPECTED_CARD_COUNT);

    const char *prev_id = NULL;
    for (int i = 0; i < n; i++) {
        cJSON *card = cJSON_GetArrayItem(cards, i);
        assert(card != NULL && cJSON_IsObject(card));
        cJSON *card_id = cJSON_GetObjectItem(card, "card_id");
        assert(card_id != NULL && cJSON_IsString(card_id));
        assert(card_id->valuestring != NULL && card_id->valuestring[0] != '\0');
        if (prev_id != NULL) {
            assert(strcmp(prev_id, card_id->valuestring) < 0);
        }
        prev_id = card_id->valuestring;
    }

    /* Truncation spot-checks: first and last card must be present. */
    cJSON *first = cJSON_GetArrayItem(cards, 0);
    cJSON *last = cJSON_GetArrayItem(cards, n - 1);
    cJSON *first_id = cJSON_GetObjectItem(first, "card_id");
    cJSON *last_id = cJSON_GetObjectItem(last, "card_id");
    assert(strcmp(first_id->valuestring, "aboleth") == 0);
    assert(strcmp(last_id->valuestring, "zuggtmoy") == 0);
    cJSON *first_name = cJSON_GetObjectItem(first, "name");
    cJSON *first_cost = cJSON_GetObjectItem(first, "cost");
    cJSON *first_aspect = cJSON_GetObjectItem(first, "aspect");
    assert(strcmp(first_name->valuestring, "Aboleth") == 0);
    assert(first_cost->valueint == 7);
    assert(strcmp(first_aspect->valuestring, "guile") == 0);

    cJSON_Delete(root);
    free(json);
    printf("PASS: assembled_json_contents (%d cards, sorted unique ids)\n", n);
}

static void test_engine_load(void) {
    intern_init(4096);
    Arena *arena = arena_create(16 * 1024 * 1024);
    assert(arena);

    char *json = test_load_catalog_json_both();
    assert(json != NULL);

    const char *board_path, *setup_path;
    test_board_setup_paths(&board_path, &setup_path);

    GameDefinition *def = engine_load_definition_json(json, board_path, setup_path, arena);
    assert(def != NULL);
    assert(def->catalog.card_count == EXPECTED_CARD_COUNT);

    for (int i = 0; i < def->catalog.card_count; i++) {
        assert(def->catalog.cards[i].card_id != SYM_NULL);
        assert(def->catalog.cards[i].name != SYM_NULL);
    }

    /* Spot-check the engine-resolved aboleth definition against the JSON. */
    Sym aboleth = intern("aboleth");
    int found = 0;
    for (int i = 0; i < def->catalog.card_count; i++) {
        if (def->catalog.cards[i].card_id == aboleth) {
            assert(strcmp(intern_str(def->catalog.cards[i].name), "Aboleth") == 0);
            assert(def->catalog.cards[i].cost == 7);
            found = 1;
            break;
        }
    }
    assert(found);

    int loaded_count = def->catalog.card_count;
    free(json);
    arena_destroy(arena);
    intern_destroy();
    printf("PASS: engine_load (all %d cards interned, aboleth resolved)\n",
           loaded_count);
}

static void test_missing_manifest_fails(void) {
    char *json = test_load_catalog_json("data/decks");
    assert(json == NULL);
    printf("PASS: missing manifest (data/decks) rejected\n");
}

int main(void) {
    test_assembled_json_contents();
    test_engine_load();
    test_missing_manifest_fails();
    printf("All catalog assembly tests passed.\n");
    return 0;
}
