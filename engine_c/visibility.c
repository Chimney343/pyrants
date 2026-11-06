#include "visibility.h"
#include "intern.h"
#include <stdio.h>
#include <string.h>

/* ---- The rule table ------------------------------------------------------
 *
 * Rows are zones; columns are the observer's relation to the zone's owner.
 *
 *   vis       VIS_CARDS: the observer sees which cards; VIS_COUNT: only how
 *             many.
 *   resample  engine_determinize reshuffles the zone. A player's resampled
 *             zones are pooled and shuffled together, because the observer
 *             knows what the pool holds but not how it splits; a shared zone
 *             shuffles alone. A VIS_CARDS zone is never resampled.
 *
 * This is the rule the engine had before the module existed (candidate 5
 * step 1 reproduces it byte for byte). An opponent's hand, deck and discard
 * are counts and pooled. Your own deck is a count but is not resampled, so
 * determinization keeps its order. The devour pile and the market discard are
 * counts whose cards never come back into play. */
static const VisRule RULES[VZ_ZONE_COUNT][2] = {
    /*                      self              opponent */
    /* VZ_HAND           */ {{VIS_CARDS, 0}, {VIS_COUNT, 1}},
    /* VZ_DECK           */ {{VIS_COUNT, 0}, {VIS_COUNT, 1}},
    /* VZ_DISCARD        */ {{VIS_CARDS, 0}, {VIS_COUNT, 1}},
    /* VZ_PLAYED         */ {{VIS_CARDS, 0}, {VIS_CARDS, 0}},
    /* VZ_INNER_CIRCLE   */ {{VIS_CARDS, 0}, {VIS_CARDS, 0}},
    /* VZ_TROPHY_HALL    */ {{VIS_CARDS, 0}, {VIS_CARDS, 0}},
    /* VZ_MARKET_ROW     */ {{VIS_CARDS, 0}, {VIS_CARDS, 0}},
    /* VZ_MARKET_DECK    */ {{VIS_COUNT, 1}, {VIS_COUNT, 1}},
    /* VZ_MARKET_DISCARD */ {{VIS_COUNT, 0}, {VIS_COUNT, 0}},
    /* VZ_DEVOUR         */ {{VIS_COUNT, 0}, {VIS_COUNT, 0}},
};

VisRule vis_rule(VisZone zone, VisRelation rel) {
    VisRule none = {VIS_COUNT, 0};
    if ((int)zone < 0 || zone >= VZ_ZONE_COUNT) return none;
    if (rel != VIS_SELF && rel != VIS_OPPONENT) return none;
    return RULES[zone][rel];
}

static int clamp_count(int n) {
    if (n < 0) return 0;
    return n > MAX_ZONE_SIZE ? MAX_ZONE_SIZE : n;
}

/* The cards of one zone. ps may be NULL for a shared zone. */
static int zone_cards(const GameState *s, const PlayerState *ps, VisZone z, const Sym **out) {
    switch (z) {
    case VZ_HAND:           *out = ps->hand;               return clamp_count(ps->hand_count);
    case VZ_DECK:           *out = ps->deck;               return clamp_count(ps->deck_count);
    case VZ_DISCARD:        *out = ps->discard_pile;       return clamp_count(ps->discard_pile_count);
    case VZ_PLAYED:         *out = ps->played_cards;       return clamp_count(ps->played_cards_count);
    case VZ_INNER_CIRCLE:   *out = ps->inner_circle;       return clamp_count(ps->inner_circle_count);
    case VZ_TROPHY_HALL:    *out = ps->trophy_hall;        return clamp_count(ps->trophy_hall_count);
    case VZ_MARKET_ROW:     *out = s->market.row;          return clamp_count(s->market.row_count);
    case VZ_MARKET_DECK:    *out = s->market.deck;         return clamp_count(s->market.deck_count);
    case VZ_MARKET_DISCARD: *out = s->market.discard_pile; return clamp_count(s->market.discard_pile_count);
    case VZ_DEVOUR:         *out = s->devour_pile;         return clamp_count(s->devour_pile_count);
    default:                *out = NULL;                   return 0;
    }
}

/* The raw size field, unclamped, as the view has always reported it. */
static int zone_size(const GameState *s, const PlayerState *ps, VisZone z) {
    switch (z) {
    case VZ_HAND:           return ps->hand_count;
    case VZ_DECK:           return ps->deck_count;
    case VZ_DISCARD:        return ps->discard_pile_count;
    case VZ_PLAYED:         return ps->played_cards_count;
    case VZ_INNER_CIRCLE:   return ps->inner_circle_count;
    case VZ_TROPHY_HALL:    return ps->trophy_hall_count;
    case VZ_MARKET_ROW:     return s->market.row_count;
    case VZ_MARKET_DECK:    return s->market.deck_count;
    case VZ_MARKET_DISCARD: return s->market.discard_pile_count;
    case VZ_DEVOUR:         return s->devour_pile_count;
    default:                return 0;
    }
}

/* ---- The view's shape ----------------------------------------------------
 *
 * Each object is a list of fields in sorted key order, as
 * json.dumps(sort_keys=True) emits them. A F_CARDS field is written only when
 * the rule shows the cards to the record's relation, so changing the table
 * changes the view without touching the walk. */
typedef enum {
    F_PLAYER_SCALAR, /* arg: PlayerScalar */
    F_STATE_SCALAR,  /* arg: StateScalar */
    F_SIZE,          /* arg: VisZone */
    F_CARDS,         /* arg: VisZone */
    F_PUBLIC,
    F_BOARD,
    F_CURRENT_PLAYER,
    F_PHASE,
    F_SUMMARIES,
    F_TURN_ORDER
} FieldKind;

typedef enum { PS_BARRACKS, PS_SPIES_AVAILABLE, PS_VP_TOKENS, PS_SCORE } PlayerScalar;
typedef enum { SS_ROUND_NUMBER, SS_RESOURCE_POWER, SS_RESOURCE_INFLUENCE } StateScalar;

typedef struct {
    const char *key;
    FieldKind kind;
    int arg;
} Field;

/* The observer's own record: the top level of the view. Relation: self. */
static const Field OBSERVER_FIELDS[] = {
    {"barracks", F_PLAYER_SCALAR, PS_BARRACKS},
    {"deck", F_CARDS, VZ_DECK},
    {"deck_size", F_SIZE, VZ_DECK},
    {"devour_size", F_SIZE, VZ_DEVOUR},
    {"discard", F_CARDS, VZ_DISCARD},
    {"discard_size", F_SIZE, VZ_DISCARD},
    {"hand", F_CARDS, VZ_HAND},
    {"inner_circle", F_CARDS, VZ_INNER_CIRCLE},
    {"played_cards", F_CARDS, VZ_PLAYED},
    {"public", F_PUBLIC, 0},
    {"score", F_PLAYER_SCALAR, PS_SCORE},
    {"spies_available", F_PLAYER_SCALAR, PS_SPIES_AVAILABLE},
    {"trophy_hall", F_CARDS, VZ_TROPHY_HALL},
    {"vp_tokens", F_PLAYER_SCALAR, PS_VP_TOKENS},
};

/* What every player sees: the public block. Relation: opponent. */
static const Field PUBLIC_FIELDS[] = {
    {"board_nodes", F_BOARD, 0},
    {"current_player_id", F_CURRENT_PLAYER, 0},
    {"devour_pile", F_CARDS, VZ_DEVOUR},
    {"market_deck", F_CARDS, VZ_MARKET_DECK},
    {"market_deck_size", F_SIZE, VZ_MARKET_DECK},
    {"market_discard", F_CARDS, VZ_MARKET_DISCARD},
    {"market_discard_size", F_SIZE, VZ_MARKET_DISCARD},
    {"market_row", F_CARDS, VZ_MARKET_ROW},
    {"phase", F_PHASE, 0},
    {"public_player_summaries", F_SUMMARIES, 0},
    {"resource_influence", F_STATE_SCALAR, SS_RESOURCE_INFLUENCE},
    {"resource_power", F_STATE_SCALAR, SS_RESOURCE_POWER},
    {"round_number", F_STATE_SCALAR, SS_ROUND_NUMBER},
    {"turn_order", F_TURN_ORDER, 0},
};

/* What every player sees about one player. Relation: opponent, so a card list
 * appears only when the rule shows it to the owner's opponents. */
static const Field SUMMARY_FIELDS[] = {
    {"barracks", F_PLAYER_SCALAR, PS_BARRACKS},
    {"deck", F_CARDS, VZ_DECK},
    {"deck_size", F_SIZE, VZ_DECK},
    {"devour_size", F_SIZE, VZ_DEVOUR},
    {"discard", F_CARDS, VZ_DISCARD},
    {"discard_size", F_SIZE, VZ_DISCARD},
    {"hand", F_CARDS, VZ_HAND},
    {"hand_size", F_SIZE, VZ_HAND},
    {"inner_circle", F_CARDS, VZ_INNER_CIRCLE},
    {"inner_circle_size", F_SIZE, VZ_INNER_CIRCLE},
    {"played_cards", F_CARDS, VZ_PLAYED},
    {"played_size", F_SIZE, VZ_PLAYED},
    {"score", F_PLAYER_SCALAR, PS_SCORE},
    {"spies_available", F_PLAYER_SCALAR, PS_SPIES_AVAILABLE},
    {"trophy_hall", F_CARDS, VZ_TROPHY_HALL},
    {"trophy_hall_size", F_SIZE, VZ_TROPHY_HALL},
    {"vp_tokens", F_PLAYER_SCALAR, PS_VP_TOKENS},
};

#define FIELD_COUNT(a) ((int)(sizeof(a) / sizeof((a)[0])))

static const char *const PHASE_NAMES[] = {
    "setup", "draw", "main", "end_of_turn", "cleanup", "game_over",
};

/* ---- The walk ------------------------------------------------------------
 *
 * One traversal produces the view. A sink consumes it: the JSON writer below
 * renders text. Ids go through sym() so a sink can work on interned ids
 * without decoding them; text() carries the few strings that are not ids. */
typedef struct {
    void (*obj_begin)(void *ctx);
    void (*obj_end)(void *ctx);
    void (*key)(void *ctx, const char *key);
    void (*list_begin)(void *ctx, int n);
    void (*list_end)(void *ctx);
    void (*sym)(void *ctx, Sym id); /* an id the view shows as null when unknown */
    void (*num)(void *ctx, long long v);
    void (*text)(void *ctx, const char *s);
} VisSink;

typedef struct {
    const GameState *s;
    const VisSink *k;
    void *ctx;
} Walk;

/* The id's text, or NULL when the view shows it as null (SYM_NULL, an unknown
 * id, or the empty string). */
static const char *id_text(Sym id) {
    if (id == SYM_NULL) return NULL;
    const char *t = intern_str(id);
    return (t && t[0]) ? t : NULL;
}

static int find_player(const GameState *s, Sym id) {
    for (int i = 0; i < s->player_count && i < MAX_PLAYERS; i++)
        if (s->players[i].player_id == id) return i;
    return -1;
}

static void walk_cards(const Walk *w, const Sym *cards, int n) {
    w->k->list_begin(w->ctx, n);
    for (int i = 0; i < n; i++) w->k->sym(w->ctx, cards[i]);
    w->k->list_end(w->ctx);
}

static int cmp_id_text(Sym a, Sym b) {
    const char *ta = id_text(a), *tb = id_text(b);
    return strcmp(ta ? ta : "", tb ? tb : "");
}

static void walk_board(const Walk *w) {
    const GameState *s = w->s;
    const BoardDefinition *board = &s->definition->board;
    int n = s->node_count < 0 ? 0 : (s->node_count > MAX_NODES ? MAX_NODES : s->node_count);
    w->k->list_begin(w->ctx, n);
    for (int i = 0; i < n; i++) {
        const NodeState *ns = &s->nodes[i];
        const NodeDefinition *nd = &board->nodes[i];

        /* Spies: the shown ids, sorted by text. */
        Sym spies[MAX_SPY_SLOTS];
        int sc = 0;
        for (int j = 0; j < ns->spy_count && j < MAX_SPY_SLOTS; j++)
            if (id_text(ns->spies[j])) spies[sc++] = ns->spies[j];
        for (int a = 1; a < sc; a++) {
            Sym key = spies[a];
            int b = a - 1;
            while (b >= 0 && cmp_id_text(spies[b], key) > 0) { spies[b + 1] = spies[b]; b--; }
            spies[b + 1] = key;
        }

        int slots = ns->troop_slot_count < 0 ? 0
                  : (ns->troop_slot_count > MAX_TROOP_SLOTS ? MAX_TROOP_SLOTS : ns->troop_slot_count);

        w->k->obj_begin(w->ctx);
        w->k->key(w->ctx, "control_vp");
        w->k->num(w->ctx, nd->control_vp);
        w->k->key(w->ctx, "node_id");
        if (id_text(ns->node_id)) {
            w->k->sym(w->ctx, ns->node_id);
        } else {
            char fallback[32];
            snprintf(fallback, sizeof(fallback), "node_%d", i);
            w->k->text(w->ctx, fallback);
        }
        w->k->key(w->ctx, "spies");
        walk_cards(w, spies, sc);
        w->k->key(w->ctx, "total_control_vp_per_turn");
        w->k->num(w->ctx, nd->total_control_vp_per_turn);
        w->k->key(w->ctx, "troop_slots");
        walk_cards(w, ns->troop_slots, slots);
        w->k->key(w->ctx, "vp_tokens");
        w->k->num(w->ctx, ns->vp_tokens);
        w->k->obj_end(w->ctx);
    }
    w->k->list_end(w->ctx);
}

static void walk_fields(const Walk *w, const Field *fields, int count,
                        const PlayerState *ps, VisRelation rel);

static void walk_summaries(const Walk *w) {
    const GameState *s = w->s;
    int n = s->player_count < 0 ? 0 : (s->player_count > MAX_PLAYERS ? MAX_PLAYERS : s->player_count);

    /* Players in key order. */
    int order[MAX_PLAYERS];
    for (int i = 0; i < n; i++) order[i] = i;
    for (int a = 1; a < n; a++) {
        int key = order[a];
        int b = a - 1;
        while (b >= 0 && cmp_id_text(s->players[order[b]].player_id, s->players[key].player_id) > 0) {
            order[b + 1] = order[b];
            b--;
        }
        order[b + 1] = key;
    }

    w->k->obj_begin(w->ctx);
    for (int i = 0; i < n; i++) {
        const PlayerState *ps = &s->players[order[i]];
        const char *pid = id_text(ps->player_id);
        w->k->key(w->ctx, pid ? pid : "");
        w->k->obj_begin(w->ctx);
        walk_fields(w, SUMMARY_FIELDS, FIELD_COUNT(SUMMARY_FIELDS), ps, VIS_OPPONENT);
        w->k->obj_end(w->ctx);
    }
    w->k->obj_end(w->ctx);
}

static void walk_fields(const Walk *w, const Field *fields, int count,
                        const PlayerState *ps, VisRelation rel) {
    const GameState *s = w->s;
    for (int f = 0; f < count; f++) {
        const Field *fd = &fields[f];
        if (fd->kind == F_CARDS && vis_rule((VisZone)fd->arg, rel).vis != VIS_CARDS)
            continue;
        w->k->key(w->ctx, fd->key);
        switch (fd->kind) {
        case F_PLAYER_SCALAR: {
            int v = 0;
            switch ((PlayerScalar)fd->arg) {
            case PS_BARRACKS:        v = ps->barracks; break;
            case PS_SPIES_AVAILABLE: v = ps->spies_available; break;
            case PS_VP_TOKENS:       v = ps->vp_tokens; break;
            case PS_SCORE:           v = ps->score; break;
            }
            w->k->num(w->ctx, v);
            break;
        }
        case F_STATE_SCALAR: {
            int v = 0;
            switch ((StateScalar)fd->arg) {
            case SS_ROUND_NUMBER:       v = s->round_number; break;
            case SS_RESOURCE_POWER:     v = s->resource_pool.power; break;
            case SS_RESOURCE_INFLUENCE: v = s->resource_pool.influence; break;
            }
            w->k->num(w->ctx, v);
            break;
        }
        case F_SIZE:
            w->k->num(w->ctx, zone_size(s, ps, (VisZone)fd->arg));
            break;
        case F_CARDS: {
            const Sym *cards;
            int n = zone_cards(s, ps, (VisZone)fd->arg, &cards);
            walk_cards(w, cards, n);
            break;
        }
        case F_PUBLIC:
            w->k->obj_begin(w->ctx);
            walk_fields(w, PUBLIC_FIELDS, FIELD_COUNT(PUBLIC_FIELDS), NULL, VIS_OPPONENT);
            w->k->obj_end(w->ctx);
            break;
        case F_BOARD:
            walk_board(w);
            break;
        case F_CURRENT_PLAYER:
            if (id_text(s->current_player_id)) w->k->sym(w->ctx, s->current_player_id);
            else w->k->text(w->ctx, "");
            break;
        case F_PHASE: {
            int ph = (int)s->phase;
            int known = ph >= 0 && ph < (int)(sizeof(PHASE_NAMES) / sizeof(PHASE_NAMES[0]));
            w->k->text(w->ctx, known ? PHASE_NAMES[ph] : "unknown");
            break;
        }
        case F_SUMMARIES:
            walk_summaries(w);
            break;
        case F_TURN_ORDER: {
            int n = s->player_count < 0 ? 0 : (s->player_count > MAX_PLAYERS ? MAX_PLAYERS : s->player_count);
            walk_cards(w, s->player_ids, n);
            break;
        }
        }
    }
}

/* Walk observer's view of s. Returns 0 when observer is not a player. */
static int walk_view(const GameState *s, Sym observer, const VisSink *k, void *ctx) {
    int me = find_player(s, observer);
    if (me < 0) return 0;
    Walk w = {s, k, ctx};
    k->obj_begin(ctx);
    walk_fields(&w, OBSERVER_FIELDS, FIELD_COUNT(OBSERVER_FIELDS), &s->players[me], VIS_SELF);
    k->obj_end(ctx);
    return 1;
}

/* ---- JSON sink -----------------------------------------------------------
 *
 * Renders exactly what Python's json.dumps(sort_keys=True) rendered for the
 * same view: ", " and ": " separators, ASCII-only output with \uXXXX escapes,
 * null for unknown ids. */
#define JSON_MAX_DEPTH 16

typedef struct {
    char *buf;
    size_t cap;
    size_t len; /* bytes the full view needs; may exceed cap */
    int depth;
    unsigned char first[JSON_MAX_DEPTH];
    int after_key;
} JsonOut;

static void jo_put(JsonOut *o, const char *s, size_t n) {
    if (o->buf && o->len < o->cap) {
        size_t room = o->cap - o->len;
        memcpy(o->buf + o->len, s, n < room ? n : room);
    }
    o->len += n;
}

static void jo_putc(JsonOut *o, char c) { jo_put(o, &c, 1); }

/* Separator before a value: none right after a key, ", " between list items. */
static void jo_value_prefix(JsonOut *o) {
    if (o->after_key) { o->after_key = 0; return; }
    if (o->depth > 0) {
        if (!o->first[o->depth]) jo_put(o, ", ", 2);
        o->first[o->depth] = 0;
    }
}

static void jo_hex4(JsonOut *o, unsigned v) {
    static const char hex[] = "0123456789abcdef";
    char b[6] = {'\\', 'u', hex[(v >> 12) & 0xF], hex[(v >> 8) & 0xF], hex[(v >> 4) & 0xF], hex[v & 0xF]};
    jo_put(o, b, 6);
}

/* A quoted string, escaped as json.dumps(ensure_ascii=True) escapes it. */
static void jo_string(JsonOut *o, const char *s) {
    jo_putc(o, '"');
    const unsigned char *p = (const unsigned char *)s;
    while (*p) {
        unsigned c = *p;
        if (c == '"') { jo_put(o, "\\\"", 2); p++; continue; }
        if (c == '\\') { jo_put(o, "\\\\", 2); p++; continue; }
        if (c >= 0x20 && c < 0x7F) { jo_putc(o, (char)c); p++; continue; }
        if (c == '\n') { jo_put(o, "\\n", 2); p++; continue; }
        if (c == '\r') { jo_put(o, "\\r", 2); p++; continue; }
        if (c == '\t') { jo_put(o, "\\t", 2); p++; continue; }
        if (c == '\b') { jo_put(o, "\\b", 2); p++; continue; }
        if (c == '\f') { jo_put(o, "\\f", 2); p++; continue; }
        if (c < 0x80) { jo_hex4(o, c); p++; continue; }
        /* Decode one UTF-8 sequence to a code point. */
        unsigned cp;
        int extra;
        if ((c & 0xE0) == 0xC0) { cp = c & 0x1F; extra = 1; }
        else if ((c & 0xF0) == 0xE0) { cp = c & 0x0F; extra = 2; }
        else if ((c & 0xF8) == 0xF0) { cp = c & 0x07; extra = 3; }
        else { jo_hex4(o, 0xFFFD); p++; continue; }
        p++;
        for (int i = 0; i < extra; i++) {
            if ((*p & 0xC0) != 0x80) { cp = 0xFFFD; break; }
            cp = (cp << 6) | (*p & 0x3F);
            p++;
        }
        if (cp >= 0x10000) {
            cp -= 0x10000;
            jo_hex4(o, 0xD800 | (cp >> 10));
            jo_hex4(o, 0xDC00 | (cp & 0x3FF));
        } else {
            jo_hex4(o, cp);
        }
    }
    jo_putc(o, '"');
}

static void jo_open(JsonOut *o, char c) {
    jo_value_prefix(o);
    jo_putc(o, c);
    if (o->depth + 1 < JSON_MAX_DEPTH) o->depth++;
    o->first[o->depth] = 1;
}

static void jo_close(JsonOut *o, char c) {
    jo_putc(o, c);
    if (o->depth > 0) o->depth--;
}

static void json_obj_begin(void *ctx) { jo_open((JsonOut *)ctx, '{'); }
static void json_obj_end(void *ctx) { jo_close((JsonOut *)ctx, '}'); }
static void json_list_begin(void *ctx, int n) { (void)n; jo_open((JsonOut *)ctx, '['); }
static void json_list_end(void *ctx) { jo_close((JsonOut *)ctx, ']'); }

static void json_key(void *ctx, const char *key) {
    JsonOut *o = (JsonOut *)ctx;
    if (!o->first[o->depth]) jo_put(o, ", ", 2);
    o->first[o->depth] = 0;
    jo_string(o, key);
    jo_put(o, ": ", 2);
    o->after_key = 1;
}

static void json_sym(void *ctx, Sym id) {
    JsonOut *o = (JsonOut *)ctx;
    jo_value_prefix(o);
    const char *t = id_text(id);
    if (t) jo_string(o, t);
    else jo_put(o, "null", 4);
}

static void json_num(void *ctx, long long v) {
    JsonOut *o = (JsonOut *)ctx;
    jo_value_prefix(o);
    char b[32];
    int n = snprintf(b, sizeof(b), "%lld", v);
    if (n > 0) jo_put(o, b, (size_t)n);
}

static void json_text(void *ctx, const char *s) {
    JsonOut *o = (JsonOut *)ctx;
    jo_value_prefix(o);
    jo_string(o, s);
}

static const VisSink JSON_SINK = {
    json_obj_begin, json_obj_end, json_key, json_list_begin, json_list_end,
    json_sym, json_num, json_text,
};

size_t engine_player_view_json(const GameState *state, Sym player_id, char *buf, size_t cap) {
    JsonOut o;
    memset(&o, 0, sizeof(o));
    o.buf = buf;
    o.cap = cap;
    if (!state || !walk_view(state, player_id, &JSON_SINK, &o)) o.len = 0;
    if (buf && cap > 0) buf[o.len < cap ? o.len : cap - 1] = '\0';
    return o.len;
}
