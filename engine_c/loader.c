#include "loader.h"
#include "cJSON.h"
#include "intern.h"
#include "arena.h"
#include "rng.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

static char *read_file(const char *path, size_t *out_len) {
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    if (fseek(f, 0, SEEK_END) != 0) { fclose(f); return NULL; }
    long ftell_result = ftell(f);
    if (ftell_result < 0) { fclose(f); return NULL; }
    size_t len = (size_t)ftell_result;
    if (fseek(f, 0, SEEK_SET) != 0) { fclose(f); return NULL; }
    char *buf = (char *)malloc(len + 1);
    if (!buf) { fclose(f); return NULL; }
    size_t total_read = 0;
    while (total_read < len) {
        size_t n = fread(buf + total_read, 1, len - total_read, f);
        if (n == 0) break;
        total_read += n;
    }
    fclose(f);
    buf[total_read] = '\0';
    *out_len = total_read;
    return buf;
}

static Sym json_string_sym(cJSON *obj, const char *key, Sym default_val) {
    cJSON *item = cJSON_GetObjectItem(obj, key);
    if (!item || !cJSON_IsString(item)) return default_val;
    return intern(cJSON_GetStringValue(item));
}

static int json_int(cJSON *obj, const char *key, int default_val) {
    cJSON *item = cJSON_GetObjectItem(obj, key);
    if (!item || !cJSON_IsNumber(item)) return default_val;
    return item->valueint;
}

static bool json_bool(cJSON *obj, const char *key, bool default_val) {
    cJSON *item = cJSON_GetObjectItem(obj, key);
    if (!item) return default_val;
    if (cJSON_IsTrue(item)) return true;
    if (cJSON_IsFalse(item)) return false;
    if (cJSON_IsNumber(item)) return item->valueint != 0;
    return default_val;
}

static Sym *json_sym_array(cJSON *obj, const char *key, int *out_count, Arena *arena) {
    cJSON *arr = cJSON_GetObjectItem(obj, key);
    if (!arr || !cJSON_IsArray(arr)) { *out_count = 0; return NULL; }
    int n = cJSON_GetArraySize(arr);
    if (n == 0) { *out_count = 0; return NULL; }
    Sym *result = arena_alloc(arena, (size_t)n * sizeof(Sym));
    for (int i = 0; i < n; i++) {
        cJSON *elem = cJSON_GetArrayItem(arr, i);
        if (elem && cJSON_IsString(elem))
            result[i] = intern(cJSON_GetStringValue(elem));
        else
            result[i] = SYM_NULL;
    }
    *out_count = n;
    return result;
}

static Sym *json_sym_or_null_array(cJSON *obj, const char *key, int *out_count, Arena *arena) {
    cJSON *arr = cJSON_GetObjectItem(obj, key);
    if (!arr || !cJSON_IsArray(arr)) { *out_count = 0; return NULL; }
    int n = cJSON_GetArraySize(arr);
    if (n == 0) { *out_count = 0; return NULL; }
    Sym *result = arena_alloc(arena, (size_t)n * sizeof(Sym));
    for (int i = 0; i < n; i++) {
        cJSON *elem = cJSON_GetArrayItem(arr, i);
        if (elem && cJSON_IsString(elem)) {
            const char *s = cJSON_GetStringValue(elem);
            if (strcmp(s, "white") == 0) result[i] = intern(s);
            else result[i] = SYM_NULL;
        } else {
            result[i] = SYM_NULL;
        }
    }
    *out_count = n;
    return result;
}

static CardAction parse_card_action(cJSON *ja) {
    CardAction a;
    memset(&a, 0, sizeof(a));
    a.action_id = json_string_sym(ja, "action_id", SYM_NULL);
    a.op = json_string_sym(ja, "op", SYM_NULL);
    a.target_scope = json_string_sym(ja, "target_scope", SYM_NULL);
    a.timing = json_string_sym(ja, "timing", intern("immediate"));
    a.optional = json_bool(ja, "optional", false);

    cJSON *q = cJSON_GetObjectItem(ja, "quantity");
    if (q) {
        Sym qkind = json_string_sym(q, "kind", intern("unspecified"));
        a.quantity_kind = (strcmp(intern_str(qkind), "fixed") == 0) ? QUANT_FIXED : QUANT_UNSPECIFIED;
        a.quantity_value = json_int(q, "value", 0);
    }

    cJSON *farr = cJSON_GetObjectItem(ja, "filters");
    if (farr && cJSON_IsArray(farr)) {
        int n = cJSON_GetArraySize(farr);
        for (int i = 0; i < n && i < MAX_FILTERS; i++) {
            cJSON *e = cJSON_GetArrayItem(farr, i);
            if (e && cJSON_IsString(e)) a.filters[a.filter_count++] = intern(cJSON_GetStringValue(e));
        }
    }

    a.source_fragment = json_string_sym(ja, "source_fragment", SYM_NULL);

    cJSON *meta = cJSON_GetObjectItem(ja, "metadata");
    if (meta && cJSON_IsObject(meta)) {
        cJSON *child = meta->child;
        while (child && a.metadata_count < MAX_METADATA) {
            if (cJSON_IsString(child) || cJSON_IsNumber(child)) {
                a.metadata[a.metadata_count].key = intern(child->string);
                if (cJSON_IsString(child))
                    a.metadata[a.metadata_count].value = intern(cJSON_GetStringValue(child));
                else {
                    char buf[32];
                    snprintf(buf, sizeof(buf), "%d", child->valueint);
                    a.metadata[a.metadata_count].value = intern(buf);
                }
                a.metadata_count++;
            } else if (cJSON_IsTrue(child)) {
                a.metadata[a.metadata_count].key = intern(child->string);
                a.metadata[a.metadata_count].value = intern("true");
                a.metadata_count++;
            } else if (cJSON_IsFalse(child)) {
                a.metadata[a.metadata_count].key = intern(child->string);
                a.metadata[a.metadata_count].value = intern("false");
                a.metadata_count++;
            }
            child = child->next;
        }
    }
    return a;
}

static CardAction *parse_actions_array(cJSON *arr, int *out_count, Arena *arena) {
    if (!arr || !cJSON_IsArray(arr)) { *out_count = 0; return NULL; }
    int n = cJSON_GetArraySize(arr);
    if (n == 0) { *out_count = 0; return NULL; }
    CardAction *actions = arena_alloc(arena, (size_t)n * sizeof(CardAction));
    for (int i = 0; i < n; i++) {
        cJSON *ja = cJSON_GetArrayItem(arr, i);
        actions[i] = parse_card_action(ja);
    }
    *out_count = n;
    return actions;
}

static CardOption *parse_options(cJSON *arr, int *out_count, Arena *arena) {
    if (!arr || !cJSON_IsArray(arr)) { *out_count = 0; return NULL; }
    int n = cJSON_GetArraySize(arr);
    if (n == 0) { *out_count = 0; return NULL; }
    CardOption *opts = arena_alloc(arena, (size_t)n * sizeof(CardOption));
    for (int i = 0; i < n; i++) {
        cJSON *jo = cJSON_GetArrayItem(arr, i);
        memset(&opts[i], 0, sizeof(CardOption));
        opts[i].option_id = json_string_sym(jo, "option_id", SYM_NULL);
        cJSON *act_arr = cJSON_GetObjectItem(jo, "actions");
        opts[i].actions = parse_actions_array(act_arr, &opts[i].action_count, arena);
    }
    *out_count = n;
    return opts;
}

static ExecutionModel parse_execution_model(cJSON *jem, Arena *arena) {
    ExecutionModel em;
    memset(&em, 0, sizeof(em));
    if (!jem) return em;

    Sym kind = json_string_sym(jem, "kind", SYM_NULL);
    const char *ks = intern_str(kind);
    if (ks && strcmp(ks, "sequence") == 0) {
        em.kind = EXEC_SEQUENCE;
        cJSON *arr = cJSON_GetObjectItem(jem, "actions");
        em.actions = parse_actions_array(arr, &em.action_count, arena);
    } else if (ks && strcmp(ks, "modal_choice") == 0) {
        em.kind = EXEC_MODAL;
        em.selection = json_string_sym(jem, "selection", intern("exactly_one"));
        cJSON *arr = cJSON_GetObjectItem(jem, "options");
        em.options = parse_options(arr, &em.option_count, arena);
    } else if (ks && strcmp(ks, "repeat_choice") == 0) {
        em.kind = EXEC_REPEAT;
        em.repeat_count = json_int(jem, "repeat_count", 1);
        em.allow_repeat = json_bool(jem, "allow_repeat", false);
        cJSON *arr = cJSON_GetObjectItem(jem, "options");
        em.options = parse_options(arr, &em.option_count, arena);
    }
    return em;
}

static GlobalCondition *parse_global_conditions(cJSON *arr, int *out_count, Arena *arena) {
    if (!arr || !cJSON_IsArray(arr)) { *out_count = 0; return NULL; }
    int n = cJSON_GetArraySize(arr);
    if (n == 0) { *out_count = 0; return NULL; }
    GlobalCondition *conds = arena_alloc(arena, (size_t)n * sizeof(GlobalCondition));
    for (int i = 0; i < n; i++) {
        cJSON *gc = cJSON_GetArrayItem(arr, i);
        conds[i].condition_type = json_string_sym(gc, "condition_type", SYM_NULL);
        conds[i].description = json_string_sym(gc, "description", SYM_NULL);
    }
    *out_count = n;
    return conds;
}

static StateContract parse_state_contract(cJSON *jsc, Arena *arena) {
    StateContract sc;
    memset(&sc, 0, sizeof(sc));
    if (!jsc) return sc;
    sc.reads = json_sym_array(jsc, "reads", &sc.read_count, arena);
    sc.writes = json_sym_array(jsc, "writes", &sc.write_count, arena);
    return sc;
}

static MetaEntry *parse_effect_payload(cJSON *jep, int *out_count, Arena *arena) {
    if (!jep || !cJSON_IsObject(jep)) { *out_count = 0; return NULL; }
    cJSON *child = jep->child;
    if (!child) { *out_count = 0; return NULL; }
    int n = 0;
    for (cJSON *c = child; c; c = c->next) n++;
    MetaEntry *entries = arena_alloc(arena, (size_t)n * sizeof(MetaEntry));
    int i = 0;
    for (cJSON *c = child; c; c = c->next) {
        entries[i].key = intern(c->string);
        if (cJSON_IsString(c))
            entries[i].value = intern(cJSON_GetStringValue(c));
        else
            entries[i].value = SYM_NULL;
        i++;
    }
    *out_count = n;
    return entries;
}

/* Parse the nested effect_payload["paid_ability"] sub-object into a PaidAbility.
 * Mirrors Python: ability_key = paid_ability.get("ability_key", paid_ability.get("effect_key", ""));
 *                 effect_key  = paid_ability.get("effect_key", ability_key).
 * Reads numeric cost fields (power/influence/discard_count) via atoi on interned strings. */
static PaidAbility parse_paid_ability(cJSON *jpa, Arena *arena) {
    PaidAbility pa;
    memset(&pa, 0, sizeof(pa));
    if (!jpa || !cJSON_IsObject(jpa)) return pa;

    Sym ability_key_raw = json_string_sym(jpa, "ability_key", SYM_NULL);
    Sym effect_key_raw  = json_string_sym(jpa, "effect_key", SYM_NULL);
    pa.ability_key = (ability_key_raw != SYM_NULL) ? ability_key_raw : effect_key_raw;
    pa.effect_key  = (effect_key_raw  != SYM_NULL) ? effect_key_raw  : pa.ability_key;

    cJSON *jep = cJSON_GetObjectItem(jpa, "effect_payload");
    pa.effect_payload = parse_effect_payload(jep, &pa.effect_payload_count, arena);

    cJSON *jcost = cJSON_GetObjectItem(jpa, "cost");
    if (jcost && cJSON_IsObject(jcost)) {
        cJSON *cp = cJSON_GetObjectItem(jcost, "power");
        if (cp) pa.cost_power = cJSON_IsNumber(cp) ? cp->valueint : atoi(cJSON_GetStringValue(cp));
        cJSON *ci = cJSON_GetObjectItem(jcost, "influence");
        if (ci) pa.cost_influence = cJSON_IsNumber(ci) ? ci->valueint : atoi(cJSON_GetStringValue(ci));
        cJSON *cd = cJSON_GetObjectItem(jcost, "discard_count");
        if (cd) pa.cost_discard = cJSON_IsNumber(cd) ? cd->valueint : atoi(cJSON_GetStringValue(cd));
    }

    pa.present = (pa.ability_key != SYM_NULL);
    return pa;
}

static CardDefinition parse_card_definition(cJSON *jcard, Arena *arena) {
    CardDefinition cd;
    memset(&cd, 0, sizeof(cd));
    cd.card_id = json_string_sym(jcard, "card_id", SYM_NULL);
    cd.name = json_string_sym(jcard, "name", SYM_NULL);
    cd.cost = json_int(jcard, "cost", 0);
    cd.aspect = json_string_sym(jcard, "aspect", SYM_NULL);
    cd.secondary_aspects = json_sym_array(jcard, "secondary_aspects", &cd.secondary_aspect_count, arena);
    cd.deck_vp = json_int(jcard, "deck_vp", 0);
    cd.inner_circle_vp = json_int(jcard, "inner_circle_vp", 0);
    cd.rules_text = json_string_sym(jcard, "rules_text", SYM_NULL);
    cd.notes = json_string_sym(jcard, "notes", SYM_NULL);

    cJSON *jem = cJSON_GetObjectItem(jcard, "execution_model");
    cd.execution = parse_execution_model(jem, arena);

    cJSON *jact = cJSON_GetObjectItem(jcard, "actions");
    cd.actions = parse_actions_array(jact, &cd.action_count, arena);

    cJSON *jgc = cJSON_GetObjectItem(jcard, "global_conditions");
    cd.global_conditions = parse_global_conditions(jgc, &cd.global_condition_count, arena);

    cJSON *jsc = cJSON_GetObjectItem(jcard, "state_contract");
    cd.state_contract = parse_state_contract(jsc, arena);

    cd.effect_key = json_string_sym(jcard, "effect_key", SYM_NULL);

    cJSON *jep = cJSON_GetObjectItem(jcard, "effect_payload");
    cd.effect_payload = parse_effect_payload(jep, &cd.effect_payload_count, arena);

    cJSON *jpa = (jep && cJSON_IsObject(jep)) ? cJSON_GetObjectItem(jep, "paid_ability") : NULL;
    cd.paid_ability = parse_paid_ability(jpa, arena);

    return cd;
}

static CardCatalog parse_catalog(const char *json_str, Arena *arena) {
    CardCatalog cat;
    memset(&cat, 0, sizeof(cat));
    cJSON *root = cJSON_Parse(json_str);
    if (!root) return cat;

    cat.catalog_id = json_string_sym(root, "catalog_id", SYM_NULL);
    cat.version = json_string_sym(root, "version", SYM_NULL);

    cJSON *jcards = cJSON_GetObjectItem(root, "cards");
    if (jcards && cJSON_IsArray(jcards)) {
        int n = cJSON_GetArraySize(jcards);
        cat.cards = arena_alloc(arena, (size_t)n * sizeof(CardDefinition));
        for (int i = 0; i < n; i++) {
            cJSON *jcard = cJSON_GetArrayItem(jcards, i);
            cat.cards[i] = parse_card_definition(jcard, arena);
        }
        cat.card_count = n;
    }
    cJSON_Delete(root);
    return cat;
}

static NodeDefinition parse_node_definition(cJSON *jnode, Arena *arena) {
    NodeDefinition nd;
    memset(&nd, 0, sizeof(nd));
    nd.node_id = json_string_sym(jnode, "node_id", SYM_NULL);
    nd.kind = json_string_sym(jnode, "kind", intern("site"));
    nd.adjacent_to = json_sym_array(jnode, "adjacent_to", &nd.adjacent_count, arena);
    nd.troop_capacity = json_int(jnode, "troop_capacity", 1);
    nd.control_vp = json_int(jnode, "control_vp", 0);
    nd.total_control_vp_per_turn = json_int(jnode, "total_control_vp_per_turn", 0);
    nd.influence_income = json_int(jnode, "influence_income", 0);
    nd.initial_troop_slots = json_sym_or_null_array(jnode, "initial_troop_slots", &nd.initial_troop_slot_count, arena);
    nd.initial_vp_tokens = json_int(jnode, "initial_vp_tokens", 0);
    return nd;
}

static BoardDefinition parse_board(const char *json_str, Arena *arena) {
    BoardDefinition bd;
    memset(&bd, 0, sizeof(bd));
    cJSON *root = cJSON_Parse(json_str);
    if (!root) return bd;

    bd.board_id = json_string_sym(root, "board_id", SYM_NULL);
    cJSON *jnodes = cJSON_GetObjectItem(root, "nodes");
    if (jnodes && cJSON_IsArray(jnodes)) {
        int n = cJSON_GetArraySize(jnodes);
        bd.nodes = arena_alloc(arena, (size_t)n * sizeof(NodeDefinition));
        for (int i = 0; i < n; i++) {
            cJSON *jnode = cJSON_GetArrayItem(jnodes, i);
            bd.nodes[i] = parse_node_definition(jnode, arena);
        }
        bd.node_count = n;
    }
    cJSON_Delete(root);
    return bd;
}

static DeckEntry *parse_deck_entries(cJSON *arr, int *out_count, Arena *arena) {
    if (!arr || !cJSON_IsArray(arr)) { *out_count = 0; return NULL; }
    int n = cJSON_GetArraySize(arr);
    if (n == 0) { *out_count = 0; return NULL; }
    DeckEntry *entries = arena_alloc(arena, (size_t)n * sizeof(DeckEntry));
    for (int i = 0; i < n; i++) {
        cJSON *je = cJSON_GetArrayItem(arr, i);
        entries[i].card_id = json_string_sym(je, "card_id", SYM_NULL);
        entries[i].count = json_int(je, "count", 0);
    }
    *out_count = n;
    return entries;
}

static DeckDefinition parse_deck(const char *json_str, Arena *arena) {
    DeckDefinition dd;
    memset(&dd, 0, sizeof(dd));
    cJSON *root = cJSON_Parse(json_str);
    if (!root) return dd;

    dd.deck_id = json_string_sym(root, "deck_id", SYM_NULL);
    dd.name = json_string_sym(root, "name", SYM_NULL);
    dd.kind = json_string_sym(root, "kind", SYM_NULL);
    dd.total_cards = json_int(root, "total_cards", 0);
    dd.per_player = json_bool(root, "per_player", false);

    cJSON *jentries = cJSON_GetObjectItem(root, "entries");
    dd.entries = parse_deck_entries(jentries, &dd.entry_count, arena);

    cJSON_Delete(root);
    return dd;
}

static SetupDefinition parse_setup(const char *json_str, Arena *arena) {
    SetupDefinition sd;
    memset(&sd, 0, sizeof(sd));
    cJSON *root = cJSON_Parse(json_str);
    if (!root) return sd;

    sd.setup_id = json_string_sym(root, "setup_id", SYM_NULL);
    sd.market_row_size = json_int(root, "market_row_size", 6);

    cJSON *jstarter = cJSON_GetObjectItem(root, "starter_deck");
    if (jstarter) {
        sd.starter_deck.deck_id = json_string_sym(jstarter, "deck_id", SYM_NULL);
        cJSON *jents = cJSON_GetObjectItem(jstarter, "entries");
        sd.starter_deck.entries = parse_deck_entries(jents, &sd.starter_deck.entry_count, arena);
    }

    cJSON *jmarket = cJSON_GetObjectItem(root, "market_deck");
    if (jmarket) {
        sd.market_deck.deck_id = json_string_sym(jmarket, "deck_id", SYM_NULL);
        cJSON *jents = cJSON_GetObjectItem(jmarket, "entries");
        sd.market_deck.entries = parse_deck_entries(jents, &sd.market_deck.entry_count, arena);
    }

    cJSON *jstacks = cJSON_GetObjectItem(root, "special_stacks");
    if (!jstacks) {
        /* Legacy fallback (D2): setups predating the JSON-driven stack table
         * get the historical 15/15/30 defaults. This is the only place those
         * literals remain. */
        sd.special_stacks[0].card_id = intern("house_guard");
        sd.special_stacks[0].market_slot = 100;
        sd.special_stacks[0].stack_total = 15;
        sd.special_stacks[1].card_id = intern("priestess_of_lolth");
        sd.special_stacks[1].market_slot = 101;
        sd.special_stacks[1].stack_total = 15;
        sd.special_stacks[2].card_id = intern("insane_outcast");
        sd.special_stacks[2].market_slot = 102;
        sd.special_stacks[2].stack_total = 30;
        sd.special_stack_count = 3;
    } else if (cJSON_IsArray(jstacks)) {
        int n = cJSON_GetArraySize(jstacks);
        for (int i = 0; i < n && sd.special_stack_count < MAX_SPECIAL_STACKS; i++) {
            cJSON *js = cJSON_GetArrayItem(jstacks, i);
            Sym card_id = json_string_sym(js, "card_id", SYM_NULL);
            int slot = json_int(js, "market_slot", 0);
            int total = json_int(js, "stack_total", 0);
            if (card_id == SYM_NULL || total <= 0) continue;
            int dup = 0;
            for (int k = 0; k < sd.special_stack_count; k++) {
                if (sd.special_stacks[k].market_slot == slot) { dup = 1; break; }
            }
            if (dup) continue;
            sd.special_stacks[sd.special_stack_count].card_id = card_id;
            sd.special_stacks[sd.special_stack_count].market_slot = slot;
            sd.special_stacks[sd.special_stack_count].stack_total = total;
            sd.special_stack_count++;
        }
    }

    cJSON_Delete(root);
    return sd;
}

GameDefinition *engine_load_definition_json(const char *catalog_json, const char *board_path,
                                            const char *setup_path, Arena *arena) {
    GameDefinition *def = arena_calloc(arena, 1, sizeof(GameDefinition));
    if (!def) return NULL;

    size_t len;
    char *json;

    if (catalog_json) {
        def->catalog = parse_catalog(catalog_json, arena);
    }

    json = read_file(board_path, &len);
    if (json) {
        def->board = parse_board(json, arena);
        free(json);
    }

    json = read_file(setup_path, &len);
    if (json) {
        def->setup = parse_setup(json, arena);
        free(json);
    }

    def->definition_id = intern("game_definition");
    def->default_player_troops = 40;
    def->default_player_spies = 5;

    return def;
}

int engine_apply_setup_json(GameDefinition *def, const char *setup_json, Arena *arena) {
    if (!def || !setup_json || !arena) return -1;
    def->setup = parse_setup(setup_json, arena);
    return 0;
}
