#include "saveload.h"
#include "engine.h"
#include "loader.h"
#include "intern.h"
#include "cJSON.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

static void add_string(cJSON *obj, const char *key, const char *val) {
    cJSON_AddStringToObject(obj, key, val ? val : "");
}

static void add_sym(cJSON *obj, const char *key, Sym val) {
    if (val == SYM_NULL)
        cJSON_AddNullToObject(obj, key);
    else
        cJSON_AddStringToObject(obj, key, intern_str(val));
}

static void add_sym_array(cJSON *obj, const char *key, const Sym *vals, int count) {
    cJSON *arr = cJSON_AddArrayToObject(obj, key);
    for (int i = 0; i < count; i++) {
        if (vals[i] == SYM_NULL)
            cJSON_AddItemToArray(arr, cJSON_CreateNull());
        else
            cJSON_AddItemToArray(arr, cJSON_CreateString(intern_str(vals[i])));
    }
}

static void add_int_array(cJSON *obj, const char *key, const int *vals, int count) {
    cJSON *arr = cJSON_AddArrayToObject(obj, key);
    for (int i = 0; i < count; i++) {
        cJSON_AddItemToArray(arr, cJSON_CreateNumber((double)vals[i]));
    }
}

static Sym parse_sym(cJSON *item) {
    if (!item) return SYM_NULL;
    if (cJSON_IsNull(item)) return SYM_NULL;
    if (cJSON_IsString(item)) return intern(item->valuestring);
    return SYM_NULL;
}

static int parse_sym_array(cJSON *arr, Sym *out, int max_count) {
    if (!cJSON_IsArray(arr)) return 0;
    int count = 0;
    cJSON *item = arr->child;
    while (item && count < max_count) {
        out[count++] = parse_sym(item);
        item = item->next;
    }
    return count;
}

int engine_serialize_state(const GameState *state,
                           const char *catalog_path,
                           const char *board_path,
                           const char *setup_path,
                           int move_count, int is_terminal,
                           char *out_json, int out_cap) {
    if (state->pending_generic) return 0;

    cJSON *root = cJSON_CreateObject();

    add_string(root, "scenario_id", "auto_generated");
    add_string(root, "description", "");
    cJSON_AddItemToObject(root, "tags", cJSON_CreateArray());
    cJSON_AddNumberToObject(root, "move_count", (double)move_count);
    cJSON_AddBoolToObject(root, "is_terminal", is_terminal ? 1 : 0);

    cJSON *def_obj = cJSON_AddObjectToObject(root, "definition");
    add_string(def_obj, "catalog_path", catalog_path);
    add_string(def_obj, "board_path", board_path);
    add_string(def_obj, "setup_path", setup_path);

    cJSON *state_obj = cJSON_AddObjectToObject(root, "state");
    cJSON_AddNumberToObject(state_obj, "round_number", (double)state->round_number);
    cJSON_AddNumberToObject(state_obj, "phase", (double)state->phase);
    cJSON_AddNumberToObject(state_obj, "player_count", (double)state->player_count);

    add_sym(state_obj, "current_player_id", state->current_player_id);
    cJSON *pid_arr = cJSON_AddArrayToObject(state_obj, "player_ids");
    for (int i = 0; i < state->player_count; i++)
        cJSON_AddItemToArray(pid_arr, cJSON_CreateString(intern_str(state->player_ids[i])));

    cJSON *players_arr = cJSON_AddArrayToObject(state_obj, "players");
    for (int i = 0; i < state->player_count; i++) {
        const PlayerState *ps = &state->players[i];
        cJSON *p_obj = cJSON_CreateObject();
        add_sym(p_obj, "player_id", ps->player_id);
        cJSON_AddNumberToObject(p_obj, "barracks", (double)ps->barracks);
        cJSON_AddNumberToObject(p_obj, "spies_available", (double)ps->spies_available);
        cJSON_AddNumberToObject(p_obj, "vp_tokens", (double)ps->vp_tokens);
        cJSON_AddNumberToObject(p_obj, "score", (double)ps->score);
        add_sym_array(p_obj, "hand", ps->hand, ps->hand_count);
        add_sym_array(p_obj, "deck", ps->deck, ps->deck_count);
        add_sym_array(p_obj, "discard_pile", ps->discard_pile, ps->discard_pile_count);
        add_sym_array(p_obj, "played_cards", ps->played_cards, ps->played_cards_count);
        add_sym_array(p_obj, "inner_circle", ps->inner_circle, ps->inner_circle_count);
        add_sym_array(p_obj, "trophy_hall", ps->trophy_hall, ps->trophy_hall_count);
        cJSON_AddItemToArray(players_arr, p_obj);
    }

    cJSON *nodes_arr = cJSON_AddArrayToObject(state_obj, "nodes");
    for (int i = 0; i < state->node_count && i < MAX_NODES; i++) {
        const NodeState *ns = &state->nodes[i];
        cJSON *n_obj = cJSON_CreateObject();
        add_sym(n_obj, "node_id", ns->node_id);
        add_sym_array(n_obj, "troop_slots", ns->troop_slots, ns->troop_slot_count);
        add_sym_array(n_obj, "spies", ns->spies, ns->spy_count);
        cJSON_AddNumberToObject(n_obj, "vp_tokens", (double)ns->vp_tokens);
        cJSON_AddItemToArray(nodes_arr, n_obj);
    }

    cJSON *market_obj = cJSON_AddObjectToObject(state_obj, "market");
    add_sym_array(market_obj, "deck", state->market.deck, state->market.deck_count);
    add_sym_array(market_obj, "row", state->market.row, state->market.row_count);
    add_sym_array(market_obj, "discard_pile", state->market.discard_pile, state->market.discard_pile_count);

    cJSON *res_obj = cJSON_AddObjectToObject(state_obj, "resource_pool");
    cJSON_AddNumberToObject(res_obj, "power", (double)state->resource_pool.power);
    cJSON_AddNumberToObject(res_obj, "influence", (double)state->resource_pool.influence);

    add_sym_array(state_obj, "devour_pile", state->devour_pile, state->devour_pile_count);

    char *raw = cJSON_Print(root);
    cJSON_Delete(root);
    if (!raw) return 0;

    int needed = (int)strlen(raw) + 1;
    if (out_json && out_cap > 0) {
        int copy = needed < out_cap ? needed : out_cap;
        memcpy(out_json, raw, (size_t)copy);
        out_json[out_cap - 1] = '\0';
    }
    free(raw);
    return needed;
}

GameState *engine_deserialize_state(const char *json,
                                    const char *catalog_json,
                                    Arena *arena,
                                    int *out_move_count) {
    cJSON *root = cJSON_Parse(json);
    if (!root) return NULL;

    cJSON *def_obj = cJSON_GetObjectItem(root, "definition");
    const char *brd_path = NULL;
    const char *stp_path = NULL;
    if (def_obj) {
        brd_path = cJSON_GetObjectItem(def_obj, "board_path") ?
            cJSON_GetObjectItem(def_obj, "board_path")->valuestring : NULL;
        stp_path = cJSON_GetObjectItem(def_obj, "setup_path") ?
            cJSON_GetObjectItem(def_obj, "setup_path")->valuestring : NULL;
    }

    cJSON *move_count_item = cJSON_GetObjectItem(root, "move_count");
    int move_count = move_count_item ? (int)move_count_item->valuedouble : 0;
    if (out_move_count) *out_move_count = move_count;

    cJSON *state_obj = cJSON_GetObjectItem(root, "state");
    if (!state_obj) {
        cJSON_Delete(root);
        return NULL;
    }

    cJSON *pid_arr = cJSON_GetObjectItem(state_obj, "player_ids");
    if (!pid_arr || !cJSON_IsArray(pid_arr) || cJSON_GetArraySize(pid_arr) == 0) {
        cJSON_Delete(root);
        return NULL;
    }

    int player_count = cJSON_GetArraySize(pid_arr);
    const char **player_ids_buf = (const char **)malloc((size_t)player_count * sizeof(char *));
    if (!player_ids_buf) { cJSON_Delete(root); return NULL; }
    for (int i = 0; i < player_count; i++) {
        cJSON *item = cJSON_GetArrayItem(pid_arr, i);
        player_ids_buf[i] = item && item->valuestring ? item->valuestring : "unknown";
    }

    GameDefinition *def = NULL;
    if (catalog_json && brd_path && stp_path) {
        def = engine_load_definition_json(catalog_json, brd_path, stp_path, arena);
    }

    GameState *gs;
    if (def && def->catalog.card_count > 0) {
        gs = engine_create_game_definition(def, player_ids_buf, player_count, 42);
    } else {
        gs = engine_create_game(NULL, player_ids_buf, player_count, 42);
    }
    free(player_ids_buf);

    if (!gs) { cJSON_Delete(root); return NULL; }

    cJSON *rn = cJSON_GetObjectItem(state_obj, "round_number");
    if (rn) gs->round_number = (int)rn->valuedouble;

    cJSON *ph = cJSON_GetObjectItem(state_obj, "phase");
    if (ph) gs->phase = (TurnPhase)((int)ph->valuedouble);

    cJSON *cpid = cJSON_GetObjectItem(state_obj, "current_player_id");
    if (cpid && cpid->valuestring) gs->current_player_id = intern(cpid->valuestring);

    cJSON *players_arr = cJSON_GetObjectItem(state_obj, "players");
    if (players_arr && cJSON_IsArray(players_arr)) {
        int pc = cJSON_GetArraySize(players_arr);
        if (pc > gs->player_count) pc = gs->player_count;
        for (int i = 0; i < pc; i++) {
            cJSON *p_obj = cJSON_GetArrayItem(players_arr, i);
            if (!p_obj) continue;
            PlayerState *ps = &gs->players[i];

            ps->hand_count = parse_sym_array(cJSON_GetObjectItem(p_obj, "hand"), ps->hand, MAX_ZONE_SIZE);
            ps->deck_count = parse_sym_array(cJSON_GetObjectItem(p_obj, "deck"), ps->deck, MAX_ZONE_SIZE);
            ps->discard_pile_count = parse_sym_array(
                cJSON_GetObjectItem(p_obj, "discard_pile"), ps->discard_pile, MAX_ZONE_SIZE);
            ps->played_cards_count = parse_sym_array(
                cJSON_GetObjectItem(p_obj, "played_cards"), ps->played_cards, MAX_ZONE_SIZE);
            ps->inner_circle_count = parse_sym_array(
                cJSON_GetObjectItem(p_obj, "inner_circle"), ps->inner_circle, MAX_ZONE_SIZE);
            ps->trophy_hall_count = parse_sym_array(
                cJSON_GetObjectItem(p_obj, "trophy_hall"), ps->trophy_hall, MAX_ZONE_SIZE);

            cJSON *b = cJSON_GetObjectItem(p_obj, "barracks");
            if (b) ps->barracks = (int)b->valuedouble;
            cJSON *sa = cJSON_GetObjectItem(p_obj, "spies_available");
            if (sa) ps->spies_available = (int)sa->valuedouble;
            cJSON *vt = cJSON_GetObjectItem(p_obj, "vp_tokens");
            if (vt) ps->vp_tokens = (int)vt->valuedouble;
            cJSON *sc = cJSON_GetObjectItem(p_obj, "score");
            if (sc) ps->score = (int)sc->valuedouble;
        }
    }

    cJSON *nodes_arr = cJSON_GetObjectItem(state_obj, "nodes");
    if (nodes_arr && cJSON_IsArray(nodes_arr)) {
        int nc = cJSON_GetArraySize(nodes_arr);
        if (nc > gs->node_count) nc = gs->node_count;
        for (int i = 0; i < nc; i++) {
            cJSON *n_obj = cJSON_GetArrayItem(nodes_arr, i);
            if (!n_obj) continue;
            NodeState *ns = &gs->nodes[i];

            ns->troop_slot_count = parse_sym_array(
                cJSON_GetObjectItem(n_obj, "troop_slots"), ns->troop_slots, MAX_TROOP_SLOTS);
            ns->spy_count = parse_sym_array(
                cJSON_GetObjectItem(n_obj, "spies"), ns->spies, MAX_SPY_SLOTS);
            cJSON *vp = cJSON_GetObjectItem(n_obj, "vp_tokens");
            if (vp) ns->vp_tokens = (int)vp->valuedouble;
        }
    }

    cJSON *market_obj = cJSON_GetObjectItem(state_obj, "market");
    if (market_obj) {
        gs->market.deck_count = parse_sym_array(
            cJSON_GetObjectItem(market_obj, "deck"), gs->market.deck, MAX_ZONE_SIZE);
        gs->market.row_count = parse_sym_array(
            cJSON_GetObjectItem(market_obj, "row"), gs->market.row, MAX_ZONE_SIZE);
        gs->market.discard_pile_count = parse_sym_array(
            cJSON_GetObjectItem(market_obj, "discard_pile"), gs->market.discard_pile, MAX_ZONE_SIZE);
    }

    cJSON *res_obj = cJSON_GetObjectItem(state_obj, "resource_pool");
    if (res_obj) {
        cJSON *pw = cJSON_GetObjectItem(res_obj, "power");
        if (pw) gs->resource_pool.power = (int)pw->valuedouble;
        cJSON *infl = cJSON_GetObjectItem(res_obj, "influence");
        if (infl) gs->resource_pool.influence = (int)infl->valuedouble;
    }

    gs->devour_pile_count = parse_sym_array(
        cJSON_GetObjectItem(state_obj, "devour_pile"), gs->devour_pile, MAX_ZONE_SIZE);

    cJSON_Delete(root);
    return gs;
}
