#include "visibility.h"
#include "engine.h"
#include "intern.h"
#include "rng.h"
#include <stdio.h>
#include <string.h>

/* ---- The rule table ------------------------------------------------------
 *
 * Rows are zones; columns are the observer's relation to the zone's owner.
 *
 *   vis       VIS_CARDS: the observer sees which cards; VIS_COUNT: only how
 *             many.
 *   resample  engine_determinize reshuffles the zone. A player's resampled
 *             zones are pooled, sorted by card id, and shuffled together,
 *             because the observer knows what the pool holds but not how it
 *             splits; a shared zone is sorted and shuffled alone. A VIS_CARDS
 *             zone is never resampled. The sort is what makes a sampled world
 *             depend only on the observer's knowledge and the seed.
 *
 * Every deck is hidden from every player, its owner included, so the owner's
 * deck is a count that determinization reshuffles. Step 1 reproduced the old
 * engine, which wrongly kept the observer's own deck in order; step 2 (A1)
 * corrects that row. Every player's discard pile is public and the devour pile
 * is public (step 2, A2), so neither is resampled. The market discard is a
 * count whose cards never come back into play. */
static const VisRule RULES[VZ_ZONE_COUNT][2] = {
    /*                      self              opponent */
    /* VZ_HAND           */ {{VIS_CARDS, 0}, {VIS_COUNT, 1}},
    /* VZ_DECK           */ {{VIS_COUNT, 1}, {VIS_COUNT, 1}},
    /* VZ_DISCARD        */ {{VIS_CARDS, 0}, {VIS_CARDS, 0}},
    /* VZ_PLAYED         */ {{VIS_CARDS, 0}, {VIS_CARDS, 0}},
    /* VZ_INNER_CIRCLE   */ {{VIS_CARDS, 0}, {VIS_CARDS, 0}},
    /* VZ_TROPHY_HALL    */ {{VIS_CARDS, 0}, {VIS_CARDS, 0}},
    /* VZ_MARKET_ROW     */ {{VIS_CARDS, 0}, {VIS_CARDS, 0}},
    /* VZ_MARKET_DECK    */ {{VIS_COUNT, 1}, {VIS_COUNT, 1}},
    /* VZ_MARKET_DISCARD */ {{VIS_COUNT, 0}, {VIS_COUNT, 0}},
    /* VZ_DEVOUR         */ {{VIS_CARDS, 0}, {VIS_CARDS, 0}},
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

/* ---- Sinks ---------------------------------------------------------------
 *
 * The walk below produces the view once; a sink consumes it. The JSON sink
 * renders text. The hash sink folds the same values into the tree key. The
 * walk dispatches with a predictable branch on inline helpers rather than
 * through function pointers, because the hash runs on the IS-MCTS hot path. */

/* The id's text, or NULL when the view shows it as null (SYM_NULL, an unknown
 * id, or the empty string). */
static const char *id_text(Sym id) {
    if (id == SYM_NULL) return NULL;
    const char *t = intern_str(id);
    return (t && t[0]) ? t : NULL;
}

/* JSON sink: renders exactly what Python's json.dumps(sort_keys=True)
 * rendered for the same view: ", " and ": " separators, ASCII-only output
 * with \uXXXX escapes, null for unknown ids. */
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

static void jo_key(JsonOut *o, const char *key) {
    if (!o->first[o->depth]) jo_put(o, ", ", 2);
    o->first[o->depth] = 0;
    jo_string(o, key);
    jo_put(o, ": ", 2);
    o->after_key = 1;
}

static void jo_sym(JsonOut *o, Sym id) {
    jo_value_prefix(o);
    const char *t = id_text(id);
    if (t) jo_string(o, t);
    else jo_put(o, "null", 4);
}

static void jo_num(JsonOut *o, long long v) {
    jo_value_prefix(o);
    char b[32];
    int n = snprintf(b, sizeof(b), "%lld", v);
    if (n > 0) jo_put(o, b, (size_t)n);
}

static void jo_text(JsonOut *o, const char *s) {
    jo_value_prefix(o);
    jo_string(o, s);
}

/* Hash sink: the IS-MCTS tree key, a 128-bit fingerprint of the same walk
 * built from fixed-width words instead of text. Two independent 64-bit
 * FNV-1a-style streams over one word sequence. Keys are skipped because the
 * walk's shape is fixed for a build (it depends only on the rule table); list
 * lengths are hashed, so lists are self-delimiting. Ids are hashed as raw
 * interned Syms, which are stable inside one process and one-to-one with
 * their text; the hash is only compared inside one run. So equal views give
 * equal keys, and different views different keys (up to collisions). One
 * corner splits without merging: an id interned as the empty string shows as
 * null in the JSON, like SYM_NULL, but hashes as itself. Decoding every id to
 * close that corner would double the hash's cost on the IS-MCTS hot path. */
typedef struct {
    uint64_t h0, h1;
} HashOut;

/* The walk's per-value helpers are tiny and run hundreds of times per hash;
 * force them inline so each sink's branch folds away. */
#if defined(_MSC_VER)
#define VIS_INLINE static __forceinline
#else
#define VIS_INLINE static inline __attribute__((always_inline))
#endif

VIS_INLINE void ih_word(HashOut *h, uint64_t x) {
    h->h0 ^= x;
    h->h0 *= 0x00000100000001b3ULL; /* FNV-1a 64 prime */
    h->h1 ^= x + 0x9e3779b97f4a7c15ULL;
    h->h1 *= 0xff51afd7ed558ccdULL; /* murmur3 finalizer constant */
}

static uint64_t text_word(const char *s) {
    uint64_t f = 0xcbf29ce484222325ULL;
    for (const unsigned char *p = (const unsigned char *)s; *p; p++) {
        f ^= *p;
        f *= 0x00000100000001b3ULL;
    }
    return f;
}

/* ---- The walk ------------------------------------------------------------
 *
 * Exactly one of hash and json is set. Ids go through w_sym so the hash can
 * use interned ids without decoding them; w_text carries the few strings that
 * are not ids. */
typedef struct {
    const GameState *s;
    HashOut *hash;
    JsonOut *json;
} Walk;

VIS_INLINE void w_obj_begin(const Walk *w) { if (w->json) jo_open(w->json, '{'); }
VIS_INLINE void w_obj_end(const Walk *w) { if (w->json) jo_close(w->json, '}'); }
VIS_INLINE void w_key(const Walk *w, const char *key) { if (w->json) jo_key(w->json, key); }
VIS_INLINE void w_list_end(const Walk *w) { if (w->json) jo_close(w->json, ']'); }

VIS_INLINE void w_list_begin(const Walk *w, int n) {
    if (w->hash) ih_word(w->hash, (uint64_t)(uint32_t)n);
    else jo_open(w->json, '[');
}

VIS_INLINE void w_sym(const Walk *w, Sym id) {
    if (w->hash) ih_word(w->hash, (uint64_t)id);
    else jo_sym(w->json, id);
}

VIS_INLINE void w_num(const Walk *w, long long v) {
    if (w->hash) ih_word(w->hash, (uint64_t)v);
    else jo_num(w->json, v);
}

VIS_INLINE void w_text(const Walk *w, const char *s) {
    if (w->hash) ih_word(w->hash, text_word(s));
    else jo_text(w->json, s);
}

static int find_player(const GameState *s, Sym id) {
    for (int i = 0; i < s->player_count && i < MAX_PLAYERS; i++)
        if (s->players[i].player_id == id) return i;
    return -1;
}

/* A card list. The hash folds the whole list in local variables, so its
 * running state stays in registers instead of round-tripping through memory
 * for every card. */
VIS_INLINE void walk_cards(const Walk *w, const Sym *cards, int n) {
    if (w->hash) {
        HashOut h = *w->hash;
        ih_word(&h, (uint64_t)(uint32_t)n);
        for (int i = 0; i < n; i++) ih_word(&h, (uint64_t)cards[i]);
        *w->hash = h;
        return;
    }
    jo_open(w->json, '[');
    for (int i = 0; i < n; i++) jo_sym(w->json, cards[i]);
    jo_close(w->json, ']');
}

static int cmp_id_text(Sym a, Sym b) {
    const char *ta = id_text(a), *tb = id_text(b);
    return strcmp(ta ? ta : "", tb ? tb : "");
}

/* One board node as the view shows it. The board is about 90% of a view, so
 * the walk gathers each node once and each sink writes it whole: the hash
 * folds the whole board in local variables, one memory round trip in all. */
typedef struct {
    int index;
    Sym node_id;
    long long control_vp;
    long long total_control_vp_per_turn;
    long long vp_tokens;
    Sym spies[MAX_SPY_SLOTS]; /* the shown ids, sorted by text */
    int spy_count;
    const Sym *troops;
    int troop_count;
} NodeRecord;

VIS_INLINE void gather_node(const GameState *s, int i, NodeRecord *r) {
    const NodeState *ns = &s->nodes[i];
    const NodeDefinition *nd = &s->definition->board.nodes[i];
    r->index = i;
    r->node_id = ns->node_id;
    r->control_vp = nd->control_vp;
    r->total_control_vp_per_turn = nd->total_control_vp_per_turn;
    r->vp_tokens = ns->vp_tokens;
    r->spy_count = 0;
    for (int j = 0; j < ns->spy_count && j < MAX_SPY_SLOTS; j++)
        if (id_text(ns->spies[j])) r->spies[r->spy_count++] = ns->spies[j];
    for (int a = 1; a < r->spy_count; a++) {
        Sym key = r->spies[a];
        int b = a - 1;
        while (b >= 0 && cmp_id_text(r->spies[b], key) > 0) { r->spies[b + 1] = r->spies[b]; b--; }
        r->spies[b + 1] = key;
    }
    r->troops = ns->troop_slots;
    r->troop_count = ns->troop_slot_count < 0 ? 0
                   : (ns->troop_slot_count > MAX_TROOP_SLOTS ? MAX_TROOP_SLOTS : ns->troop_slot_count);
}

/* The node's values in the JSON's key order. The node id is hashed raw, like
 * every id the hash sees; the JSON's node_<i> fallback is positional, so it
 * carries nothing the position does not. */
VIS_INLINE void hash_node(HashOut *h, const NodeRecord *r) {
    ih_word(h, (uint64_t)r->control_vp);
    ih_word(h, (uint64_t)r->node_id);
    ih_word(h, (uint64_t)(uint32_t)r->spy_count);
    for (int j = 0; j < r->spy_count; j++) ih_word(h, (uint64_t)r->spies[j]);
    ih_word(h, (uint64_t)r->total_control_vp_per_turn);
    ih_word(h, (uint64_t)(uint32_t)r->troop_count);
    for (int j = 0; j < r->troop_count; j++) ih_word(h, (uint64_t)r->troops[j]);
    ih_word(h, (uint64_t)r->vp_tokens);
}

static void json_node(JsonOut *o, const NodeRecord *r) {
    jo_open(o, '{');
    jo_key(o, "control_vp");
    jo_num(o, r->control_vp);
    jo_key(o, "node_id");
    if (id_text(r->node_id)) {
        jo_sym(o, r->node_id);
    } else {
        char fallback[32];
        snprintf(fallback, sizeof(fallback), "node_%d", r->index);
        jo_text(o, fallback);
    }
    jo_key(o, "spies");
    jo_open(o, '[');
    for (int j = 0; j < r->spy_count; j++) jo_sym(o, r->spies[j]);
    jo_close(o, ']');
    jo_key(o, "total_control_vp_per_turn");
    jo_num(o, r->total_control_vp_per_turn);
    jo_key(o, "troop_slots");
    jo_open(o, '[');
    for (int j = 0; j < r->troop_count; j++) jo_sym(o, r->troops[j]);
    jo_close(o, ']');
    jo_key(o, "vp_tokens");
    jo_num(o, r->vp_tokens);
    jo_close(o, '}');
}

static void walk_board(const Walk *w) {
    const GameState *s = w->s;
    int n = s->node_count < 0 ? 0 : (s->node_count > MAX_NODES ? MAX_NODES : s->node_count);
    if (w->hash) {
        /* The whole board folds into one local accumulator. */
        HashOut h = *w->hash;
        ih_word(&h, (uint64_t)(uint32_t)n);
        for (int i = 0; i < n; i++) {
            NodeRecord r;
            gather_node(s, i, &r);
            hash_node(&h, &r);
        }
        *w->hash = h;
        return;
    }
    jo_open(w->json, '[');
    for (int i = 0; i < n; i++) {
        NodeRecord r;
        gather_node(s, i, &r);
        json_node(w->json, &r);
    }
    jo_close(w->json, ']');
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

    w_obj_begin(w);
    for (int i = 0; i < n; i++) {
        const PlayerState *ps = &s->players[order[i]];
        if (w->json) {
            const char *pid = id_text(ps->player_id);
            jo_key(w->json, pid ? pid : "");
        } else {
            w_sym(w, ps->player_id); /* the key is data here: which player */
        }
        w_obj_begin(w);
        walk_fields(w, SUMMARY_FIELDS, FIELD_COUNT(SUMMARY_FIELDS), ps, VIS_OPPONENT);
        w_obj_end(w);
    }
    w_obj_end(w);
}

static void walk_fields(const Walk *w, const Field *fields, int count,
                        const PlayerState *ps, VisRelation rel) {
    const GameState *s = w->s;
    for (int f = 0; f < count; f++) {
        const Field *fd = &fields[f];
        if (fd->kind == F_CARDS && RULES[fd->arg][rel].vis != VIS_CARDS)
            continue;
        w_key(w, fd->key);
        switch (fd->kind) {
        case F_PLAYER_SCALAR: {
            int v = 0;
            switch ((PlayerScalar)fd->arg) {
            case PS_BARRACKS:        v = ps->barracks; break;
            case PS_SPIES_AVAILABLE: v = ps->spies_available; break;
            case PS_VP_TOKENS:       v = ps->vp_tokens; break;
            case PS_SCORE:           v = ps->score; break;
            }
            w_num(w, v);
            break;
        }
        case F_STATE_SCALAR: {
            int v = 0;
            switch ((StateScalar)fd->arg) {
            case SS_ROUND_NUMBER:       v = s->round_number; break;
            case SS_RESOURCE_POWER:     v = s->resource_pool.power; break;
            case SS_RESOURCE_INFLUENCE: v = s->resource_pool.influence; break;
            }
            w_num(w, v);
            break;
        }
        case F_SIZE:
            w_num(w, zone_size(s, ps, (VisZone)fd->arg));
            break;
        case F_CARDS: {
            const Sym *cards;
            int n = zone_cards(s, ps, (VisZone)fd->arg, &cards);
            walk_cards(w, cards, n);
            break;
        }
        case F_PUBLIC:
            w_obj_begin(w);
            walk_fields(w, PUBLIC_FIELDS, FIELD_COUNT(PUBLIC_FIELDS), NULL, VIS_OPPONENT);
            w_obj_end(w);
            break;
        case F_BOARD:
            walk_board(w);
            break;
        case F_CURRENT_PLAYER:
            if (id_text(s->current_player_id)) w_sym(w, s->current_player_id);
            else w_text(w, "");
            break;
        case F_PHASE: {
            int ph = (int)s->phase;
            int known = ph >= 0 && ph < (int)(sizeof(PHASE_NAMES) / sizeof(PHASE_NAMES[0]));
            if (w->hash) w_num(w, known ? ph : -1);
            else w_text(w, known ? PHASE_NAMES[ph] : "unknown");
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
static int walk_view(const Walk *w, Sym observer) {
    int me = find_player(w->s, observer);
    if (me < 0) return 0;
    w_obj_begin(w);
    walk_fields(w, OBSERVER_FIELDS, FIELD_COUNT(OBSERVER_FIELDS), &w->s->players[me], VIS_SELF);
    w_obj_end(w);
    return 1;
}

size_t engine_player_view_json(const GameState *state, Sym player_id, char *buf, size_t cap) {
    JsonOut o;
    memset(&o, 0, sizeof(o));
    o.buf = buf;
    o.cap = cap;
    Walk w = {state, NULL, &o};
    if (!state || !walk_view(&w, player_id)) o.len = 0;
    if (buf && cap > 0) buf[o.len < cap ? o.len : cap - 1] = '\0';
    return o.len;
}

void engine_infostate_hash(const GameState *state, Sym player_id, uint64_t out[2]) {
    if (out == NULL) return;
    out[0] = 0;
    out[1] = 0;
    if (state == NULL) return;
    HashOut h = {0xcbf29ce484222325ULL /* FNV-1a 64 offset basis */,
                 0x9e3779b97f4a7c15ULL /* golden-ratio seed */};
    ih_word(&h, 0x0700); /* schema tag: the ADR-0007 walk */
    Walk w = {state, &h, NULL};
    if (!walk_view(&w, player_id)) return;
    out[0] = h.h0;
    out[1] = h.h1;
}

/* ---- Determinization -----------------------------------------------------
 *
 * A sampled world the observer cannot tell from the real one: every zone the
 * rule marks for resampling is reshuffled, and nothing the observer sees
 * moves. A player's resampled zones are pooled in VisZone order (hand, deck)
 * and shuffled together; shared resampled zones (the market deck) shuffle
 * alone, after the players. Visible zones — every discard pile and the devour
 * pile — are never resampled.
 *
 * Each pool is sorted by card id before it is shuffled, so the world depends
 * only on what the observer knows and on the seed. Without the sort the
 * shuffle's input order leaks the real arrangement into the sampled world:
 * two states the observer cannot tell apart (different deck orders, or
 * different splits of an opponent's hidden hand+deck pool) would sample
 * different worlds for the same seed. Sorting draws nothing from the RNG. */
static Sym *zone_cards_mut(GameState *s, PlayerState *ps, VisZone z, int *count) {
    const Sym *cards;
    *count = zone_cards(s, ps, z, &cards);
    return (Sym *)cards;
}

/* Insertion sort by card text, the same key the view sorts its lists by. The
 * pool is small (at most a few dozen cards per player), so this is cheap and
 * keeps the sort stable for equal ids, which are interchangeable anyway. */
static void sort_pool(Sym *pool, int n) {
    for (int a = 1; a < n; a++) {
        Sym key = pool[a];
        int b = a - 1;
        while (b >= 0 && cmp_id_text(pool[b], key) > 0) {
            pool[b + 1] = pool[b];
            b--;
        }
        pool[b + 1] = key;
    }
}

GameState *engine_determinize(const GameState *src, Sym observing_player_id, uint64_t seed) {
    if (!src) return NULL;
    GameState *clone = engine_clone(src);
    if (!clone) return NULL;

    RNG rng;
    rng_seed(&rng, seed);

    for (int i = 0; i < clone->player_count && i < MAX_PLAYERS; i++) {
        PlayerState *ps = &clone->players[i];
        VisRelation rel = ps->player_id == observing_player_id ? VIS_SELF : VIS_OPPONENT;
        Sym pool[VZ_PLAYER_ZONE_COUNT * MAX_ZONE_SIZE];
        int n = 0;
        for (int z = 0; z < VZ_PLAYER_ZONE_COUNT; z++) {
            if (!RULES[z][rel].resample) continue;
            int count;
            Sym *cards = zone_cards_mut(clone, ps, (VisZone)z, &count);
            for (int j = 0; j < count; j++) pool[n++] = cards[j];
        }
        sort_pool(pool, n);
        rng_shuffle(&rng, (uint32_t *)pool, n); /* draws nothing when n <= 1 */
        n = 0;
        for (int z = 0; z < VZ_PLAYER_ZONE_COUNT; z++) {
            if (!RULES[z][rel].resample) continue;
            int count;
            Sym *cards = zone_cards_mut(clone, ps, (VisZone)z, &count);
            for (int j = 0; j < count; j++) cards[j] = pool[n++];
        }
    }

    for (int z = VZ_PLAYER_ZONE_COUNT; z < VZ_ZONE_COUNT; z++) {
        if (!RULES[z][VIS_OPPONENT].resample) continue;
        int count;
        Sym *cards = zone_cards_mut(clone, NULL, (VisZone)z, &count);
        sort_pool(cards, count);
        rng_shuffle(&rng, (uint32_t *)cards, count);
    }

    /* F-002: decouple the shared mid-game reshuffle/forced-discard stream
     * across sampled worlds. Every mid-game random event reseeds from
     * shuffle_seed/shuffle_counter; rerolling them here gives each world an
     * independent stream. Drawn after every other draw so the rerolled seed is
     * a deterministic function of `seed` (F-010 reproducibility). See
     * docs/validation/f002-f003-fix-plan.md Part A. */
    clone->shuffle_seed = rng_next(&rng);
    clone->shuffle_counter = 0;

    return clone;
}
