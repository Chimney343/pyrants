#include "pending.h"
#include "cJSON.h"
#include "intern.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_SELECTION 8

static const PendingPromotionState *promotion_array_c(const GameState *state,
                                                       PendingKind kind,
                                                       int *count) {
    if (!state) { if (count) *count = 0; return NULL; }
    if (kind == PENDING_IMMEDIATE) {
        if (count) *count = state->pending_immediate_count;
        return state->pending_immediate;
    }
    if (kind == PENDING_EOT) {
        if (count) *count = state->pending_eot_count;
        return state->pending_eot;
    }
    if (count) *count = 0;
    return NULL;
}

static PendingPromotionState *promotion_array_mut(GameState *state,
                                                   PendingKind kind,
                                                   int *count) {
    if (!state) { if (count) *count = 0; return NULL; }
    if (kind == PENDING_IMMEDIATE) {
        if (count) *count = state->pending_immediate_count;
        return state->pending_immediate;
    }
    if (kind == PENDING_EOT) {
        if (count) *count = state->pending_eot_count;
        return state->pending_eot;
    }
    if (count) *count = 0;
    return NULL;
}

static void set_promotion_count(GameState *state, PendingKind kind, int count) {
    if (!state) return;
    if (kind == PENDING_IMMEDIATE) state->pending_immediate_count = count;
    else if (kind == PENDING_EOT) state->pending_eot_count = count;
}

int pending_priority(PendingKind kind) {
    switch (kind) {
        case PENDING_IMMEDIATE: return 40;
        case PENDING_GENERIC: return 30;
        case PENDING_ABILITY: return 20;
        case PENDING_EOT: return 10;
        default: return 0;
    }
}

const char *pending_kind_name(PendingKind kind) {
    switch (kind) {
        case PENDING_ABILITY: return "ability";
        case PENDING_IMMEDIATE: return "immediate";
        case PENDING_EOT: return "end_of_turn";
        case PENDING_GENERIC: return "generic";
        case PENDING_CHANCE: return "chance";
        default: return "none";
    }
}

PendingDecision pending_peek(const GameState *state) {
    PendingDecision d = {PENDING_NONE, 0, 0};
    if (!state) return d;

    if (state->phase == PHASE_END_OF_TURN) {
        if (state->pending_eot_count > 0) {
            d.kind = PENDING_EOT;
            d.count = state->pending_eot_count;
        }
    } else if (state->pending_immediate_count > 0) {
        d.kind = PENDING_IMMEDIATE;
        d.count = state->pending_immediate_count;
    } else if (state->pending_generic) {
        d.kind = PENDING_GENERIC;
        d.count = 1;
    } else if (state->pending_ability) {
        d.kind = PENDING_ABILITY;
        d.count = 1;
    }
    d.priority = pending_priority(d.kind);
    return d;
}

int pending_promotion_count(const GameState *state, PendingKind kind) {
    int count = 0;
    promotion_array_c(state, kind, &count);
    return count;
}

const PendingPromotionState *pending_promotion_at(const GameState *state,
                                                   PendingKind kind, int index) {
    int count = 0;
    const PendingPromotionState *array = promotion_array_c(state, kind, &count);
    if (!array || index < 0 || index >= count) return NULL;
    return &array[index];
}

PendingPromotionState *pending_promotion_mut(GameState *state,
                                              PendingKind kind, int index) {
    int count = 0;
    PendingPromotionState *array = promotion_array_mut(state, kind, &count);
    if (!array || index < 0 || index >= count) return NULL;
    return &array[index];
}

int pending_promotion_push(GameState *state, PendingKind kind,
                           const PendingPromotionState *promotion) {
    if (!state || !promotion) return 0;
    int count = 0;
    PendingPromotionState *array = promotion_array_mut(state, kind, &count);
    if (!array || count >= MAX_PENDING_PROMO) return 0;
    array[count] = *promotion;
    set_promotion_count(state, kind, count + 1);
    return 1;
}

int pending_promotion_pop(GameState *state, PendingKind kind) {
    if (!state) return 0;
    int count = 0;
    PendingPromotionState *array = promotion_array_mut(state, kind, &count);
    if (!array || count <= 0) return 0;
    for (int i = 0; i < count - 1; i++) array[i] = array[i + 1];
    set_promotion_count(state, kind, count - 1);
    return 1;
}

void pending_promotion_set_count(GameState *state, PendingKind kind, int count) {
    if (!state) return;
    if (count < 0) count = 0;
    if (count > MAX_PENDING_PROMO) count = MAX_PENDING_PROMO;
    set_promotion_count(state, kind, count);
}

static PendingGenericChoiceState *clone_pending_generic(Arena *arena,
                                                         const PendingGenericChoiceState *src) {
    if (!src) return NULL;
    PendingGenericChoiceState *dst = arena_calloc(arena, 1, sizeof(*dst));
    if (!dst) return NULL;
    memcpy(dst, src, sizeof(*dst));

    if (src->option_ids && src->option_count > 0) {
        size_t sz = (size_t)src->option_count * sizeof(Sym);
        Sym *copy = arena_alloc(arena, sz);
        if (copy) { memcpy(copy, src->option_ids, sz); dst->option_ids = copy; }
    }
    if (src->selected_option_ids && src->selected_count > 0) {
        size_t sz = (size_t)src->selected_count * sizeof(Sym);
        Sym *copy = arena_alloc(arena, sz);
        if (copy) { memcpy(copy, src->selected_option_ids, sz); dst->selected_option_ids = copy; }
    }
    return dst;
}

void pending_clone(GameState *dst, const GameState *src, Arena *arena) {
    if (!dst || !src || !arena) return;

    if (src->pending_ability) {
        dst->pending_ability = arena_alloc(arena, sizeof(PendingAbilityState));
        if (dst->pending_ability)
            memcpy(dst->pending_ability, src->pending_ability, sizeof(PendingAbilityState));
    }

    if (src->pending_generic) {
        dst->pending_generic = clone_pending_generic(arena, src->pending_generic);
        if (dst->pending_generic) {
            PendingGenericChoiceState *src_parent = src->pending_generic->parent;
            PendingGenericChoiceState **dst_parent = &dst->pending_generic->parent;
            int depth = 0;
            while (src_parent && depth < 16) {
                PendingGenericChoiceState *copy = clone_pending_generic(arena, src_parent);
                if (!copy) break;
                *dst_parent = copy;
                dst_parent = &copy->parent;
                src_parent = src_parent->parent;
                depth++;
            }
            *dst_parent = NULL;
        }
    }
}

/* ---- hash / describe --------------------------------------------------- */

static uint64_t mix(uint64_t h, uint64_t value) {
    h ^= value;
    h *= 0x100000001b3ULL;
    return h;
}

static uint64_t mix_sym(uint64_t h, Sym sym) {
    return mix(h, (uint64_t)(uint32_t)sym);
}

uint64_t pending_hash(const GameState *state) {
    uint64_t h = 0xcbf29ce484222325ULL;
    if (!state) return h;

    PendingDecision d = pending_peek(state);
    h = mix(h, (uint64_t)d.kind);
    h = mix(h, (uint64_t)(uint32_t)d.count);

    if (d.kind == PENDING_IMMEDIATE || d.kind == PENDING_EOT) {
        for (int i = 0; i < d.count; i++) {
            const PendingPromotionState *p = pending_promotion_at(state, d.kind, i);
            if (!p) continue;
            h = mix_sym(h, p->card_id);
            h = mix_sym(h, p->timing);
            h = mix(h, (uint64_t)p->optional);
            h = mix(h, (uint64_t)p->deferred_choice);
            h = mix_sym(h, p->source_card_id);
            h = mix(h, (uint64_t)p->requires_another_played_card);
            h = mix_sym(h, p->required_aspect);
            h = mix_sym(h, p->required_secondary_aspect);
            h = mix_sym(h, p->focus_aspect);
            h = mix(h, (uint64_t)p->repeat_while_targets);
            h = mix(h, (uint64_t)(uint32_t)p->promotions_remaining);
        }
    } else if (d.kind == PENDING_ABILITY && state->pending_ability) {
        h = mix_sym(h, state->pending_ability->card_id);
        h = mix_sym(h, state->pending_ability->ability_key);
        h = mix(h, (uint64_t)state->pending_ability->resolved);
    } else if (d.kind == PENDING_GENERIC) {
        const PendingGenericChoiceState *p = state->pending_generic;
        int depth = 0;
        while (p && depth < 16) {
            h = mix_sym(h, p->source_card_id);
            h = mix(h, (uint64_t)(uint32_t)p->exec_kind);
            h = mix(h, (uint64_t)(uint32_t)p->option_count);
            for (int i = 0; i < p->option_count && i < MAX_PENDING_ACTIONS; i++)
                h = mix_sym(h, p->option_ids[i]);
            h = mix(h, (uint64_t)(uint32_t)p->selected_count);
            for (int i = 0; i < p->selected_count && i < MAX_PENDING_ACTIONS; i++)
                h = mix_sym(h, p->selected_option_ids[i]);
            h = mix_sym(h, p->current_option_id);
            h = mix(h, (uint64_t)(uint32_t)p->next_action_index);
            h = mix(h, (uint64_t)p->awaiting_option);
            h = mix(h, (uint64_t)(uint32_t)p->remaining_repeats);
            h = mix(h, (uint64_t)p->allow_repeat);
            h = mix(h, (uint64_t)(uint32_t)p->last_selection_count);
            for (int i = 0; i < p->last_selection_count && i < MAX_SELECTION; i++) {
                h = mix_sym(h, p->last_selection_keys[i]);
                h = mix_sym(h, p->last_selection_values[i]);
            }
            h = mix(h, (uint64_t)(uint32_t)p->counter_count);
            for (int i = 0; i < p->counter_count && i < MAX_SELECTION; i++) {
                h = mix_sym(h, p->counter_keys[i]);
                h = mix(h, (uint64_t)(uint32_t)p->counter_values[i]);
            }
            h = mix(h, (uint64_t)(uint32_t)p->limit_count);
            for (int i = 0; i < p->limit_count && i < MAX_SELECTION; i++) {
                h = mix_sym(h, p->limit_keys[i]);
                h = mix(h, (uint64_t)(uint32_t)p->limit_values[i]);
            }
            h = mix(h, (uint64_t)(uint32_t)p->resolve_depth);
            h = mix_sym(h, p->last_played_card_id);
            p = p->parent;
            depth++;
        }
    }
    return h;
}

void pending_describe(const GameState *state, char *buf, size_t cap) {
    if (!buf || cap == 0) return;
    PendingDecision d = pending_peek(state);
    if (d.kind == PENDING_IMMEDIATE || d.kind == PENDING_EOT) {
        const PendingPromotionState *p = pending_promotion_at(state, d.kind, 0);
        snprintf(buf, cap, "%s promotion card=%s remaining=%d",
                 pending_kind_name(d.kind),
                 p ? intern_str(p->card_id) : "?",
                 p ? p->promotions_remaining : 0);
    } else if (d.kind == PENDING_ABILITY && state->pending_ability) {
        snprintf(buf, cap, "ability card=%s key=%s",
                 intern_str(state->pending_ability->card_id),
                 intern_str(state->pending_ability->ability_key));
    } else if (d.kind == PENDING_GENERIC && state->pending_generic) {
        snprintf(buf, cap, "generic card=%s option=%s action=%d",
                 intern_str(state->pending_generic->source_card_id),
                 intern_str(state->pending_generic->current_option_id),
                 state->pending_generic->next_action_index);
    } else {
        snprintf(buf, cap, "none");
    }
}

/* ---- serialization ----------------------------------------------------- */

static void add_string(cJSON *obj, const char *key, const char *val) {
    cJSON_AddStringToObject(obj, key, val ? val : "");
}

static void add_sym(cJSON *obj, const char *key, Sym sym) {
    const char *text = intern_str(sym);
    if (text) cJSON_AddStringToObject(obj, key, text);
    else cJSON_AddNullToObject(obj, key);
}

static Sym read_sym(const cJSON *obj, const char *key) {
    const cJSON *item = cJSON_GetObjectItem(obj, key);
    if (!item || !cJSON_IsString(item) || !item->valuestring) return SYM_NULL;
    return intern(item->valuestring);
}

static void add_sym_array(cJSON *obj, const char *key, const Sym *values, int count) {
    cJSON *array = cJSON_AddArrayToObject(obj, key);
    for (int i = 0; i < count; i++) {
        const char *text = intern_str(values[i]);
        cJSON_AddItemToArray(array, text ? cJSON_CreateString(text) : cJSON_CreateNull());
    }
}

static int read_sym_array(const cJSON *obj, const char *key, Sym *out, int max) {
    const cJSON *array = cJSON_GetObjectItem(obj, key);
    if (!array || !cJSON_IsArray(array)) return 0;
    int count = cJSON_GetArraySize(array);
    if (count > max) count = max;
    for (int i = 0; i < count; i++) {
        const cJSON *item = cJSON_GetArrayItem(array, i);
        out[i] = (item && cJSON_IsString(item) && item->valuestring)
            ? intern(item->valuestring) : SYM_NULL;
    }
    return count;
}

static Sym *read_sym_ptr_array(const cJSON *obj, const char *key,
                               int *out_count, Arena *arena, int max) {
    *out_count = 0;
    const cJSON *array = cJSON_GetObjectItem(obj, key);
    if (!array || !cJSON_IsArray(array)) return NULL;
    int count = cJSON_GetArraySize(array);
    if (count > max) count = max;
    if (count <= 0) return NULL;
    Sym *values = arena_alloc(arena, (size_t)count * sizeof(Sym));
    if (!values) return NULL;
    for (int i = 0; i < count; i++) {
        const cJSON *item = cJSON_GetArrayItem(array, i);
        values[i] = (item && cJSON_IsString(item) && item->valuestring)
            ? intern(item->valuestring) : SYM_NULL;
    }
    *out_count = count;
    return values;
}

static void add_int_array(cJSON *obj, const char *key, const int *values, int count) {
    cJSON *array = cJSON_AddArrayToObject(obj, key);
    for (int i = 0; i < count; i++)
        cJSON_AddItemToArray(array, cJSON_CreateNumber((double)values[i]));
}

static int read_int_array(const cJSON *obj, const char *key, int *out, int max) {
    const cJSON *array = cJSON_GetObjectItem(obj, key);
    if (!array || !cJSON_IsArray(array)) return 0;
    int count = cJSON_GetArraySize(array);
    if (count > max) count = max;
    for (int i = 0; i < count; i++) {
        const cJSON *item = cJSON_GetArrayItem(array, i);
        out[i] = item ? (int)item->valuedouble : 0;
    }
    return count;
}

static int read_bool(const cJSON *obj, const char *key) {
    const cJSON *item = cJSON_GetObjectItem(obj, key);
    return item ? cJSON_IsTrue(item) : 0;
}

static int read_int(const cJSON *obj, const char *key, int fallback) {
    const cJSON *item = cJSON_GetObjectItem(obj, key);
    if (!item) return fallback;
    if (cJSON_IsString(item) && item->valuestring) return atoi(item->valuestring);
    return (int)item->valuedouble;
}

static cJSON *promotion_to_json(const PendingPromotionState *p) {
    cJSON *obj = cJSON_CreateObject();
    add_sym(obj, "card_id", p->card_id);
    add_sym(obj, "timing", p->timing);
    cJSON_AddBoolToObject(obj, "optional", p->optional);
    cJSON_AddBoolToObject(obj, "deferred_choice", p->deferred_choice);
    add_sym(obj, "source_card_id", p->source_card_id);
    cJSON_AddBoolToObject(obj, "requires_another_played_card",
                          p->requires_another_played_card);
    add_sym(obj, "required_aspect", p->required_aspect);
    add_sym(obj, "required_secondary_aspect", p->required_secondary_aspect);
    add_sym(obj, "focus_aspect", p->focus_aspect);
    cJSON_AddBoolToObject(obj, "repeat_while_targets", p->repeat_while_targets);
    cJSON_AddNumberToObject(obj, "promotions_remaining", (double)p->promotions_remaining);
    return obj;
}

static void promotion_from_json(const cJSON *obj, PendingPromotionState *p) {
    memset(p, 0, sizeof(*p));
    p->card_id = read_sym(obj, "card_id");
    p->timing = read_sym(obj, "timing");
    p->optional = read_bool(obj, "optional");
    p->deferred_choice = read_bool(obj, "deferred_choice");
    p->source_card_id = read_sym(obj, "source_card_id");
    p->requires_another_played_card = read_bool(obj, "requires_another_played_card");
    p->required_aspect = read_sym(obj, "required_aspect");
    p->required_secondary_aspect = read_sym(obj, "required_secondary_aspect");
    p->focus_aspect = read_sym(obj, "focus_aspect");
    p->repeat_while_targets = read_bool(obj, "repeat_while_targets");
    p->promotions_remaining = read_int(obj, "promotions_remaining", 0);
}

static cJSON *ability_to_json(const PendingAbilityState *p) {
    cJSON *obj = cJSON_CreateObject();
    add_sym(obj, "card_id", p->card_id);
    add_sym(obj, "ability_key", p->ability_key);
    cJSON_AddBoolToObject(obj, "resolved", p->resolved);
    return obj;
}

static void ability_from_json(const cJSON *obj, PendingAbilityState *p) {
    memset(p, 0, sizeof(*p));
    p->card_id = read_sym(obj, "card_id");
    p->ability_key = read_sym(obj, "ability_key");
    p->resolved = read_bool(obj, "resolved");
}

static cJSON *generic_to_json(const PendingGenericChoiceState *p, int depth) {
    if (!p || depth > 16) return NULL;
    int last_count = p->last_selection_count < MAX_SELECTION ? p->last_selection_count : MAX_SELECTION;
    int counter_count = p->counter_count < MAX_SELECTION ? p->counter_count : MAX_SELECTION;
    int limit_count = p->limit_count < MAX_SELECTION ? p->limit_count : MAX_SELECTION;
    cJSON *obj = cJSON_CreateObject();
    add_sym(obj, "source_card_id", p->source_card_id);
    cJSON_AddNumberToObject(obj, "exec_kind", (double)p->exec_kind);
    add_sym_array(obj, "option_ids", p->option_ids, p->option_count);
    cJSON_AddNumberToObject(obj, "option_count", (double)p->option_count);
    add_sym_array(obj, "selected_option_ids", p->selected_option_ids, p->selected_count);
    cJSON_AddNumberToObject(obj, "selected_count", (double)p->selected_count);
    add_sym(obj, "current_option_id", p->current_option_id);
    cJSON_AddNumberToObject(obj, "next_action_index", (double)p->next_action_index);
    cJSON_AddBoolToObject(obj, "awaiting_option", p->awaiting_option);
    cJSON_AddNumberToObject(obj, "remaining_repeats", (double)p->remaining_repeats);
    cJSON_AddBoolToObject(obj, "allow_repeat", p->allow_repeat);
    add_sym_array(obj, "last_selection_keys", p->last_selection_keys, last_count);
    add_sym_array(obj, "last_selection_values", p->last_selection_values, last_count);
    cJSON_AddNumberToObject(obj, "last_selection_count", (double)last_count);
    add_sym_array(obj, "counter_keys", p->counter_keys, counter_count);
    add_int_array(obj, "counter_values", p->counter_values, counter_count);
    cJSON_AddNumberToObject(obj, "counter_count", (double)counter_count);
    add_sym_array(obj, "limit_keys", p->limit_keys, limit_count);
    add_int_array(obj, "limit_values", p->limit_values, limit_count);
    cJSON_AddNumberToObject(obj, "limit_count", (double)limit_count);
    cJSON_AddNumberToObject(obj, "resolve_depth", (double)p->resolve_depth);
    add_sym(obj, "last_played_card_id", p->last_played_card_id);
    cJSON_AddItemToObject(obj, "parent", generic_to_json(p->parent, depth + 1));
    return obj;
}

static PendingGenericChoiceState *generic_from_json(const cJSON *obj, Arena *arena,
                                                    int depth);

static void pending_restore_one_actions(GameState *state, PendingGenericChoiceState *p) {
    p->current_actions = NULL;
    p->current_action_count = 0;
    if (!state || !state->definition || p->awaiting_option) return;

    const CardDefinition *card = NULL;
    for (int i = 0; i < state->definition->catalog.card_count; i++) {
        if (state->definition->catalog.cards[i].card_id == p->source_card_id) {
            card = &state->definition->catalog.cards[i];
            break;
        }
    }
    if (!card) return;

    if (p->current_option_id != SYM_NULL) {
        for (int i = 0; i < card->execution.option_count; i++) {
            if (card->execution.options[i].option_id == p->current_option_id) {
                p->current_actions = card->execution.options[i].actions;
                p->current_action_count = card->execution.options[i].action_count;
                return;
            }
        }
        return;
    }
    p->current_actions = card->execution.actions;
    p->current_action_count = card->execution.action_count;
}

static void pending_restore_actions(GameState *state) {
    if (!state) return;
    PendingGenericChoiceState *p = state->pending_generic;
    int depth = 0;
    while (p && depth < 16) {
        pending_restore_one_actions(state, p);
        p = p->parent;
        depth++;
    }
}

static PendingGenericChoiceState *generic_from_json(const cJSON *obj, Arena *arena,
                                                    int depth) {
    if (!obj || depth > 16) return NULL;
    PendingGenericChoiceState *p = arena_calloc(arena, 1, sizeof(*p));
    if (!p) return NULL;

    p->source_card_id = read_sym(obj, "source_card_id");
    p->exec_kind = read_int(obj, "exec_kind", 0);
    p->option_ids = read_sym_ptr_array(obj, "option_ids", &p->option_count, arena,
                                       MAX_PENDING_ACTIONS);
    p->selected_option_ids = read_sym_ptr_array(obj, "selected_option_ids",
                                                 &p->selected_count, arena,
                                                 MAX_PENDING_ACTIONS);
    p->current_option_id = read_sym(obj, "current_option_id");
    p->next_action_index = read_int(obj, "next_action_index", 0);
    p->awaiting_option = read_bool(obj, "awaiting_option");
    p->remaining_repeats = read_int(obj, "remaining_repeats", 0);
    p->allow_repeat = read_bool(obj, "allow_repeat");
    p->last_selection_count = read_sym_array(obj, "last_selection_keys",
                                             p->last_selection_keys, MAX_SELECTION);
    read_sym_array(obj, "last_selection_values", p->last_selection_values, MAX_SELECTION);
    p->last_selection_count = read_int(obj, "last_selection_count",
                                        p->last_selection_count);
    if (p->last_selection_count > MAX_SELECTION) p->last_selection_count = MAX_SELECTION;
    p->counter_count = read_sym_array(obj, "counter_keys", p->counter_keys, MAX_SELECTION);
    read_int_array(obj, "counter_values", p->counter_values, MAX_SELECTION);
    p->counter_count = read_int(obj, "counter_count", p->counter_count);
    if (p->counter_count > MAX_SELECTION) p->counter_count = MAX_SELECTION;
    p->limit_count = read_sym_array(obj, "limit_keys", p->limit_keys, MAX_SELECTION);
    read_int_array(obj, "limit_values", p->limit_values, MAX_SELECTION);
    p->limit_count = read_int(obj, "limit_count", p->limit_count);
    if (p->limit_count > MAX_SELECTION) p->limit_count = MAX_SELECTION;
    p->resolve_depth = read_int(obj, "resolve_depth", 0);
    p->last_played_card_id = read_sym(obj, "last_played_card_id");

    const cJSON *parent = cJSON_GetObjectItem(obj, "parent");
    p->parent = generic_from_json(parent, arena, depth + 1);
    return p;
}

int pending_save_json(struct cJSON *state_obj, const GameState *state) {
    if (!state_obj || !state) return 0;

    PendingDecision decision = pending_peek(state);

    cJSON *pending = cJSON_AddObjectToObject(state_obj, "pending");
    add_string(pending, "kind", pending_kind_name(decision.kind));
    cJSON_AddNumberToObject(pending, "priority", (double)decision.priority);
    cJSON_AddNumberToObject(pending, "count", (double)decision.count);

    cJSON *immediate = cJSON_AddArrayToObject(pending, "immediate");
    for (int i = 0; i < state->pending_immediate_count; i++)
        cJSON_AddItemToArray(immediate, promotion_to_json(&state->pending_immediate[i]));

    cJSON *eot = cJSON_AddArrayToObject(pending, "end_of_turn");
    for (int i = 0; i < state->pending_eot_count; i++)
        cJSON_AddItemToArray(eot, promotion_to_json(&state->pending_eot[i]));

    if (state->pending_ability)
        cJSON_AddItemToObject(pending, "ability", ability_to_json(state->pending_ability));
    else
        cJSON_AddNullToObject(pending, "ability");

    if (state->pending_generic)
        cJSON_AddItemToObject(pending, "generic", generic_to_json(state->pending_generic, 0));
    else
        cJSON_AddNullToObject(pending, "generic");

    return 1;
}

int pending_load_json(const struct cJSON *state_obj, GameState *state) {
    if (!state_obj || !state) return 0;

    state->pending_immediate_count = 0;
    state->pending_eot_count = 0;
    state->pending_ability = NULL;
    state->pending_generic = NULL;

    const cJSON *pending = cJSON_GetObjectItem(state_obj, "pending");
    if (!pending || !cJSON_IsObject(pending)) return 1;

    Arena *arena = (Arena *)state->arena;
    if (!arena) return 0;

    const cJSON *immediate = cJSON_GetObjectItem(pending, "immediate");
    if (immediate && cJSON_IsArray(immediate)) {
        int count = cJSON_GetArraySize(immediate);
        if (count > MAX_PENDING_PROMO) count = MAX_PENDING_PROMO;
        for (int i = 0; i < count; i++)
            promotion_from_json(cJSON_GetArrayItem(immediate, i),
                                &state->pending_immediate[i]);
        state->pending_immediate_count = count;
    }

    const cJSON *eot = cJSON_GetObjectItem(pending, "end_of_turn");
    if (eot && cJSON_IsArray(eot)) {
        int count = cJSON_GetArraySize(eot);
        if (count > MAX_PENDING_PROMO) count = MAX_PENDING_PROMO;
        for (int i = 0; i < count; i++)
            promotion_from_json(cJSON_GetArrayItem(eot, i), &state->pending_eot[i]);
        state->pending_eot_count = count;
    }

    const cJSON *ability = cJSON_GetObjectItem(pending, "ability");
    if (ability && ability->type != cJSON_NULL) {
        PendingAbilityState *p = arena_alloc(arena, sizeof(PendingAbilityState));
        if (p) {
            ability_from_json(ability, p);
            state->pending_ability = p;
        }
    }

    const cJSON *generic = cJSON_GetObjectItem(pending, "generic");
    if (generic && generic->type != cJSON_NULL) {
        PendingGenericChoiceState *p = generic_from_json(generic, arena, 0);
        if (p) state->pending_generic = p;
    }

    if (state->pending_generic)
        pending_restore_actions(state);
    return 1;
}
