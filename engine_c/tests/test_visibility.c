/* Tests for the visibility module (engine_c/visibility.c): what one player can
 * know about a game state.
 *
 * The module's promise is that one rule decides what an observer sees, and
 * every consumer agrees with it:
 *
 *   - the rule never resamples a zone it shows;
 *   - the view shows hidden cards to their owner only;
 *   - the view is valid JSON with sorted keys, and reports the length it needs;
 *   - determinization leaves the observer's view byte-identical (this replaces
 *     the old source-text check that engine_determinize never touches the
 *     board, and is stronger: it covers every zone the observer sees);
 *   - two states share a tree key exactly when they share a view.
 *
 * Byte identity with the Python view this module replaced is pinned by the
 * F-013 G1 reference vectors (openspiel_pyrants/tests/test_board_projection.py).
 */
#include "../engine.h"
#include "../visibility.h"
#include "../intern.h"
#include "../arena.h"
#include "../saveload.h"
#include "catalog_dir.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const char *PLAYER_IDS[] = {"p1", "p2", "p3"};

/* One catalog for every game in this file. */
static Arena *g_arena;
static GameDefinition *g_def;

static GameState *fresh_game(int players) {
    GameState *gs = engine_create_game_definition(g_def, PLAYER_IDS, players, 42);
    assert(gs);
    return gs;
}

/* The observer's view as a malloc'd string, using the two-call protocol. */
static char *view_of(const GameState *gs, const char *pid) {
    size_t need = engine_player_view_json(gs, intern(pid), NULL, 0);
    char *buf = (char *)malloc(need + 1);
    assert(buf);
    size_t got = engine_player_view_json(gs, intern(pid), buf, need + 1);
    assert(got == need);
    assert(strlen(buf) == need);
    return buf;
}

static int hashes_equal(const uint64_t a[2], const uint64_t b[2]) {
    return a[0] == b[0] && a[1] == b[1];
}

/* Apply `steps` pseudo-random legal moves. Consumes gs. */
static GameState *advance(GameState *gs, int steps, uint64_t *lcg) {
    static Move moves[1024];
    for (int s = 0; s < steps && !engine_is_terminal(gs); s++) {
        int n = engine_legal_moves(gs, moves, 1024);
        if (n <= 0) break;
        int stored = n < 1024 ? n : 1024; /* clamp: n is the true total now */
        *lcg = *lcg * 6364136223846793005ULL + 1442695040888963407ULL;
        int pick = (int)((*lcg >> 33) % (uint64_t)stored);
        GameState *next = engine_apply(gs, &moves[pick]);
        if (!next) break;
        engine_destroy(gs);
        gs = next;
    }
    return gs;
}

/* The owner's rule shows every player's discard pile and the devour pile.
 * Seed both in every playout fixture so the view and determinize invariants
 * below actually exercise those fields. The rules are not under test here, so
 * the seeded cards need not balance against the other zones. */
static void seed_public_card_zones(GameState *gs) {
    for (int i = 0; i < gs->player_count && i < MAX_PLAYERS; i++) {
        if (gs->players[i].discard_pile_count == 0) {
            gs->players[i].discard_pile[0] = intern("vis_fixture_discard");
            gs->players[i].discard_pile_count = 1;
        }
    }
    if (gs->devour_pile_count == 0) {
        gs->devour_pile[0] = intern("vis_fixture_devour");
        gs->devour_pile_count = 1;
    }
}

/* A spread of reachable states: fresh games and playouts of several lengths. */
#define MAX_STATES 24
static int playout_states(GameState **out, int players) {
    int n = 0;
    static const int depths[] = {0, 15, 40, 80, 140, 220};
    for (uint64_t seed = 1; seed <= 4 && n < MAX_STATES; seed++) {
        for (size_t d = 0; d < sizeof(depths) / sizeof(depths[0]) && n < MAX_STATES; d++) {
            GameState *gs = fresh_game(players);
            uint64_t lcg = seed * 0x9E3779B97F4A7C15ULL;
            gs = advance(gs, depths[d], &lcg);
            seed_public_card_zones(gs);
            /* The view and tree-key tests below only cover the new fields if
             * the fixtures actually populate them. */
            assert(gs->devour_pile_count > 0);
            for (int i = 0; i < gs->player_count && i < MAX_PLAYERS; i++)
                assert(gs->players[i].discard_pile_count > 0);
            out[n++] = gs;
        }
    }
    return n;
}

static void destroy_states(GameState **states, int n) {
    for (int i = 0; i < n; i++) engine_destroy(states[i]);
}

/* ---- the rule ------------------------------------------------------------ */

static void test_rule_never_resamples_a_shown_zone(void) {
    for (int z = 0; z < VZ_ZONE_COUNT; z++) {
        for (int r = 0; r < 2; r++) {
            VisRule rule = vis_rule((VisZone)z, (VisRelation)r);
            assert(!(rule.vis == VIS_CARDS && rule.resample));
        }
    }
    printf("PASS: the rule never resamples a zone it shows\n");
}

/* ---- the view ------------------------------------------------------------ */

static void test_hidden_cards_reach_only_their_owner(void) {
    GameState *gs = fresh_game(2);
    PlayerState *p1 = &gs->players[0];
    PlayerState *p2 = &gs->players[1];
    p2->hand_count = 1;
    p2->hand[0] = intern("vis_secret_hand");
    p2->discard_pile_count = 1;
    p2->discard_pile[0] = intern("vis_secret_discard");
    p2->deck_count = 1;
    p2->deck[0] = intern("vis_secret_deck");
    p1->deck_count = 1;
    p1->deck[0] = intern("vis_secret_own_deck");
    p1->hand_count = 1;
    p1->hand[0] = intern("vis_my_hand");

    char *v1 = view_of(gs, "p1");
    char *v2 = view_of(gs, "p2");

    /* An opponent's hand and deck are counts; their discard is shown as cards
     * (the owner's visibility rule). */
    assert(!strstr(v1, "vis_secret_hand"));
    assert(strstr(v1, "vis_secret_discard"));
    assert(!strstr(v1, "vis_secret_deck"));
    /* The owner sees their hand and discard, never their deck. */
    assert(strstr(v2, "vis_secret_hand"));
    assert(strstr(v2, "vis_secret_discard"));
    assert(!strstr(v2, "vis_secret_deck"));
    assert(strstr(v1, "vis_my_hand"));
    assert(!strstr(v1, "vis_secret_own_deck"));
    assert(!strstr(v2, "vis_my_hand"));

    free(v1);
    free(v2);
    engine_destroy(gs);
    printf("PASS: hidden cards reach only their owner\n");
}

/* The owner's rule: an opponent's discard pile and the devour pile are shown
 * as cards to every player. Hand and deck stay counts (control). */
static void test_opponent_discard_and_devour_are_visible(void) {
    GameState *gs = fresh_game(2);
    PlayerState *p2 = &gs->players[1];

    p2->discard_pile_count = 2;
    p2->discard_pile[0] = intern("vis_public_discard_a");
    p2->discard_pile[1] = intern("vis_public_discard_b");
    gs->devour_pile_count = 2;
    gs->devour_pile[0] = intern("vis_public_devour_a");
    gs->devour_pile[1] = intern("vis_public_devour_b");

    /* Hidden zones stay hidden for the control below. */
    p2->hand_count = 1;
    p2->hand[0] = intern("vis_private_hand");
    p2->deck_count = 1;
    p2->deck[0] = intern("vis_private_deck");

    char *v1 = view_of(gs, "p1");
    char *v2 = view_of(gs, "p2");

    /* Every view shows the devour pile's cards. */
    assert(strstr(v1, "vis_public_devour_a"));
    assert(strstr(v1, "vis_public_devour_b"));
    assert(strstr(v2, "vis_public_devour_a"));

    /* Every player's discard cards are in every other player's view. */
    assert(strstr(v1, "vis_public_discard_a"));
    assert(strstr(v1, "vis_public_discard_b"));
    assert(strstr(v2, "vis_public_discard_a"));

    /* Hand and deck stay counts. */
    assert(!strstr(v1, "vis_private_hand"));
    assert(!strstr(v1, "vis_private_deck"));

    /* The fields are where the rule says: the public block's devour_pile and
     * each player summary's discard list. */
    cJSON *root = cJSON_Parse(v1);
    assert(root);
    cJSON *pub = cJSON_GetObjectItemCaseSensitive(root, "public");
    assert(cJSON_IsObject(pub));
    cJSON *devour = cJSON_GetObjectItemCaseSensitive(pub, "devour_pile");
    assert(cJSON_IsArray(devour));
    assert(cJSON_GetArraySize(devour) == 2);
    cJSON *summaries = cJSON_GetObjectItemCaseSensitive(pub, "public_player_summaries");
    assert(cJSON_IsObject(summaries));
    cJSON *p2_summary = cJSON_GetObjectItemCaseSensitive(summaries, "p2");
    assert(cJSON_IsObject(p2_summary));
    cJSON *discard = cJSON_GetObjectItemCaseSensitive(p2_summary, "discard");
    assert(cJSON_IsArray(discard));
    assert(cJSON_GetArraySize(discard) == 2);
    cJSON_Delete(root);

    free(v1);
    free(v2);
    engine_destroy(gs);
    printf("PASS: opponent discards and the devour pile are visible\n");
}

static void assert_sorted_keys(const cJSON *node) {
    if (cJSON_IsObject(node)) {
        const char *prev = NULL;
        for (const cJSON *c = node->child; c; c = c->next) {
            if (prev) assert(strcmp(prev, c->string) < 0);
            prev = c->string;
            assert_sorted_keys(c);
        }
    } else if (cJSON_IsArray(node)) {
        for (const cJSON *c = node->child; c; c = c->next) assert_sorted_keys(c);
    }
}

static void test_view_is_json_with_sorted_keys(void) {
    GameState *states[MAX_STATES];
    int n = playout_states(states, 3);
    int checked = 0;
    for (int i = 0; i < n; i++) {
        for (int p = 0; p < 3; p++) {
            char *v = view_of(states[i], PLAYER_IDS[p]);
            cJSON *root = cJSON_Parse(v);
            assert(root);
            assert(cJSON_GetObjectItemCaseSensitive(root, "public"));
            assert(cJSON_GetObjectItemCaseSensitive(root, "hand"));
            assert_sorted_keys(root);
            cJSON_Delete(root);
            free(v);
            checked++;
        }
    }
    destroy_states(states, n);
    assert(checked >= 30);
    printf("PASS: the view is JSON with sorted keys (%d views)\n", checked);
}

static void test_view_reports_the_length_it_needs(void) {
    GameState *gs = fresh_game(2);
    char *full = view_of(gs, "p1");
    size_t need = strlen(full);
    assert(need > 100);

    char short_buf[16];
    size_t got = engine_player_view_json(gs, intern("p1"), short_buf, sizeof(short_buf));
    assert(got == need);
    assert(strlen(short_buf) == sizeof(short_buf) - 1);
    assert(strncmp(short_buf, full, sizeof(short_buf) - 1) == 0);

    char none[8] = "garbage";
    assert(engine_player_view_json(gs, intern("not_a_player"), none, sizeof(none)) == 0);
    assert(none[0] == '\0');
    assert(engine_player_view_json(NULL, intern("p1"), none, sizeof(none)) == 0);

    free(full);
    engine_destroy(gs);
    printf("PASS: the view reports the length it needs\n");
}

/* ---- determinization ----------------------------------------------------- */

/* A card-id multiset: its entries, sorted. Used to check that resampling
 * rearranges a zone without adding, dropping or changing cards. */
static int sorted_ids(const Sym *cards, int n, Sym *out) {
    for (int i = 0; i < n; i++) out[i] = cards[i];
    for (int a = 1; a < n; a++) {
        Sym key = out[a];
        int b = a - 1;
        while (b >= 0 && out[b] > key) { out[b + 1] = out[b]; b--; }
        out[b + 1] = key;
    }
    return n;
}

static int same_multiset(const Sym *a, int na, const Sym *b, int nb) {
    if (na != nb) return 0;
    Sym sa[MAX_ZONE_SIZE], sb[MAX_ZONE_SIZE];
    sorted_ids(a, na, sa);
    sorted_ids(b, nb, sb);
    return memcmp(sa, sb, (size_t)na * sizeof(Sym)) == 0;
}

/* The observer cannot see their own deck. Determinization must therefore
 * reshuffle it: across seeds the order changes, while the cards, the count and
 * the observer's view stay put. */
static void test_determinize_shuffles_the_observers_own_deck(void) {
    GameState *gs = fresh_game(2);
    PlayerState *p1 = &gs->players[0];
    PlayerState *p2 = &gs->players[1];

    static const char *const deck_ids[] = {
        "vis_deck_a", "vis_deck_b", "vis_deck_c",
        "vis_deck_d", "vis_deck_e", "vis_deck_f",
    };
    int deck_count = (int)(sizeof(deck_ids) / sizeof(deck_ids[0]));
    p1->deck_count = deck_count;
    for (int i = 0; i < deck_count; i++) p1->deck[i] = intern(deck_ids[i]);
    p1->hand_count = 2;
    p1->hand[0] = intern("vis_own_hand_a");
    p1->hand[1] = intern("vis_own_hand_b");

    p2->deck_count = 3;
    p2->deck[0] = intern("vis_opp_deck_a");
    p2->deck[1] = intern("vis_opp_deck_b");
    p2->deck[2] = intern("vis_opp_deck_c");
    p2->hand_count = 2;
    p2->hand[0] = intern("vis_opp_hand_a");
    p2->hand[1] = intern("vis_opp_hand_b");
    p2->discard_pile_count = 2;
    p2->discard_pile[0] = intern("vis_opp_disc_a");
    p2->discard_pile[1] = intern("vis_opp_disc_b");

    Sym original[MAX_ZONE_SIZE];
    for (int i = 0; i < deck_count; i++) original[i] = p1->deck[i];
    char *view_before = view_of(gs, "p1");

    Sym first_order[MAX_ZONE_SIZE];
    int have_first = 0, order_changed = 0;
    for (uint64_t seed = 1; seed <= 24; seed++) {
        GameState *det = engine_determinize(gs, intern("p1"), seed * 7919ULL);
        assert(det);
        PlayerState *dp = &det->players[0];

        /* Same cards and count. */
        assert(dp->deck_count == deck_count);
        assert(same_multiset(dp->deck, dp->deck_count, original, deck_count));

        /* The observer's view cannot move. */
        char *after = view_of(det, "p1");
        assert(strcmp(view_before, after) == 0);
        free(after);

        if (!have_first) {
            for (int i = 0; i < deck_count; i++) first_order[i] = dp->deck[i];
            have_first = 1;
        } else if (memcmp(first_order, dp->deck, (size_t)deck_count * sizeof(Sym)) != 0) {
            order_changed++;
        }
        engine_destroy(det);
    }
    free(view_before);
    engine_destroy(gs);

    assert(have_first);
    assert(order_changed > 0);
    printf("PASS: determinize shuffles the observer's own deck (%d of 24 seeds changed order)\n",
           order_changed);
}

/* A sampled world depends only on what the observer knows and the seed. Two
 * states the observer cannot tell apart — one differs in the observer's own
 * deck order and in how an opponent's hidden hand+deck pool is split (counts
 * unchanged) — must determinize to the same world. The opponent's discard pile
 * and the devour pile are visible, so they are identical in both states here.
 * Byte identity is checked through engine_serialize_state. */
static void test_determinized_world_depends_only_on_observer_knowledge(void) {
    GameState *a = fresh_game(2);
    PlayerState *p1 = &a->players[0];
    PlayerState *p2 = &a->players[1];

    p1->deck_count = 4;
    p1->deck[0] = intern("vis_own_1");
    p1->deck[1] = intern("vis_own_2");
    p1->deck[2] = intern("vis_own_3");
    p1->deck[3] = intern("vis_own_4");
    p1->hand_count = 1;
    p1->hand[0] = intern("vis_hand_1");

    p2->hand_count = 2;
    p2->hand[0] = intern("vis_hidden_a");
    p2->hand[1] = intern("vis_hidden_b");
    p2->deck_count = 2;
    p2->deck[0] = intern("vis_hidden_c");
    p2->deck[1] = intern("vis_hidden_d");
    p2->discard_pile_count = 2;
    p2->discard_pile[0] = intern("vis_public_e");
    p2->discard_pile[1] = intern("vis_public_f");
    a->devour_pile_count = 1;
    a->devour_pile[0] = intern("vis_public_devour");

    /* b differs only inside hidden zones: p1's deck order is reversed, and an
     * opponent's hidden card swaps between hand and deck. Both states show the
     * same opponent discard and devour pile. */
    GameState *b = engine_clone(a);
    assert(b);
    PlayerState *bp1 = &b->players[0];
    PlayerState *bp2 = &b->players[1];
    for (int i = 0; i < bp1->deck_count / 2; i++) {
        Sym tmp = bp1->deck[i];
        bp1->deck[i] = bp1->deck[bp1->deck_count - 1 - i];
        bp1->deck[bp1->deck_count - 1 - i] = tmp;
    }
    Sym tmp = bp2->hand[0];
    bp2->hand[0] = bp2->deck[0];
    bp2->deck[0] = tmp;

    /* What p1 knows is identical in both states. */
    char *va = view_of(a, "p1");
    char *vb = view_of(b, "p1");
    assert(strcmp(va, vb) == 0);
    free(va);
    free(vb);

    static const int json_cap = 256 * 1024;
    char *ja = (char *)malloc((size_t)json_cap);
    char *jb = (char *)malloc((size_t)json_cap);
    assert(ja && jb);

    int compared = 0;
    for (uint64_t seed = 1; seed <= 12; seed++) {
        GameState *da = engine_determinize(a, intern("p1"), seed * 104729ULL);
        GameState *db = engine_determinize(b, intern("p1"), seed * 104729ULL);
        assert(da && db);

        int na = engine_serialize_state(da, "cards", "board", "setup", 0, 0, ja, json_cap);
        int nb = engine_serialize_state(db, "cards", "board", "setup", 0, 0, jb, json_cap);
        assert(na > 0 && na < json_cap);
        assert(nb == na);
        assert(memcmp(ja, jb, (size_t)na) == 0);

        engine_destroy(da);
        engine_destroy(db);
        compared++;
    }

    free(ja);
    free(jb);
    engine_destroy(b);
    engine_destroy(a);
    assert(compared == 12);
    printf("PASS: determinized worlds depend only on the observer's knowledge (%d seeds)\n",
           compared);
}

static void test_determinize_keeps_the_observer_view(void) {
    GameState *states[MAX_STATES];
    int n = playout_states(states, 3);
    int checked = 0, opponent_changed = 0;
    for (int i = 0; i < n; i++) {
        for (int p = 0; p < 3; p++) {
            const char *obs = PLAYER_IDS[p];
            const char *other = PLAYER_IDS[(p + 1) % 3];
            char *before = view_of(states[i], obs);
            char *other_before = view_of(states[i], other);
            for (uint64_t seed = 1; seed <= 20; seed++) {
                GameState *det = engine_determinize(states[i], intern(obs), seed * 7919ULL);
                assert(det);
                char *after = view_of(det, obs);
                assert(strcmp(before, after) == 0);
                char *other_after = view_of(det, other);
                if (strcmp(other_before, other_after) != 0) opponent_changed++;
                free(after);
                free(other_after);
                engine_destroy(det);
                checked++;
            }
            free(before);
            free(other_before);
        }
    }
    destroy_states(states, n);
    assert(checked >= 600);
    /* Determinization must do something: an opponent sees their own hidden
     * zones, so some sampled worlds look different to them. */
    assert(opponent_changed > 0);
    printf("PASS: determinize keeps the observer's view (%d worlds, %d changed an opponent's)\n",
           checked, opponent_changed);
}

/* ---- the tree key -------------------------------------------------------- */

static int pairs_checked = 0;

static void check_pair(const GameState *a, const GameState *b, const char *pid) {
    char *va = view_of(a, pid);
    char *vb = view_of(b, pid);
    uint64_t ha[2], hb[2];
    engine_infostate_hash(a, intern(pid), ha);
    engine_infostate_hash(b, intern(pid), hb);
    int same_view = strcmp(va, vb) == 0;
    assert(same_view == hashes_equal(ha, hb));
    pairs_checked++;
    free(va);
    free(vb);
}

static void test_tree_key_classes_match_view_classes(void) {
    GameState *states[MAX_STATES];
    int n = playout_states(states, 3);
    Sym swap_in = intern("vis_swapped_card");
    for (int i = 0; i < n; i++) {
        for (int p = 0; p < 3; p++) {
            const char *pid = PLAYER_IDS[p];
            /* Sampled worlds: same view, so the same key. */
            for (uint64_t seed = 1; seed <= 3; seed++) {
                GameState *det = engine_determinize(states[i], intern(pid), seed);
                check_pair(states[i], det, pid);
                engine_destroy(det);
            }
            /* Visible and hidden single-field changes, on clones. */
            for (int mut = 0; mut < 7; mut++) {
                GameState *c = engine_clone(states[i]);
                PlayerState *me = &c->players[p];
                PlayerState *them = &c->players[(p + 1) % 3];
                switch (mut) {
                case 0: if (me->deck_count > 0) me->deck[0] = swap_in; break;      /* hidden */
                case 1: if (them->hand_count > 0) them->hand[0] = swap_in; break;  /* hidden */
                case 2: if (me->hand_count > 0) me->hand[0] = swap_in; break;      /* shown */
                case 3: if (them->played_cards_count > 0) them->played_cards[0] = swap_in; break;
                case 4: c->devour_pile_count += 1; break;                          /* shown: devour */
                case 5: if (c->market.row_count > 0) c->market.row[0] = swap_in; break;
                case 6: if (them->discard_pile_count > 0) them->discard_pile[0] = swap_in; break; /* shown */
                }
                check_pair(states[i], c, pid);
                engine_destroy(c);
            }
            /* Different states from the spread. */
            check_pair(states[i], states[(i + 1) % n], pid);
        }
    }
    destroy_states(states, n);
    assert(pairs_checked >= 500);
    printf("PASS: tree-key classes match view classes (%d pairs)\n", pairs_checked);
}

int main(void) {
    intern_init(65536);
    g_arena = arena_create(4 * 1024 * 1024);
    g_def = test_load_definition(g_arena);
    assert(g_def);

    test_rule_never_resamples_a_shown_zone();
    test_hidden_cards_reach_only_their_owner();
    test_opponent_discard_and_devour_are_visible();
    test_view_is_json_with_sorted_keys();
    test_view_reports_the_length_it_needs();
    test_determinize_shuffles_the_observers_own_deck();
    test_determinized_world_depends_only_on_observer_knowledge();
    test_determinize_keeps_the_observer_view();
    test_tree_key_classes_match_view_classes();

    arena_destroy(g_arena);
    printf("\nAll visibility tests passed.\n");
    return 0;
}
