#include "intern.h"
#include <stdio.h>
#include <stdlib.h>
#include <assert.h>
#include <string.h>

#define LAZY_GROW_COUNT 2048

void test_intern_null_sym(void) {
    intern_init(1024);
    assert(intern_str(SYM_NULL) == NULL);
    intern_destroy();
    printf("PASS: test_intern_null_sym\n");
}

void test_intern_round_trip(void) {
    intern_init(1024);
    const char *words[] = {"alpha", "bravo", "charlie", "delta", "echo",
        "foxtrot", "golf", "hotel", "india", "juliet"};
    int n = 10;
    Sym syms[10];
    for (int i = 0; i < n; i++) {
        syms[i] = intern(words[i]);
        assert(syms[i] != SYM_NULL);
    }
    for (int i = 0; i < n; i++) {
        const char *back = intern_str(syms[i]);
        assert(back != NULL);
        assert(strcmp(back, words[i]) == 0);
    }
    intern_destroy();
    printf("PASS: test_intern_round_trip\n");
}

void test_intern_stable_pointer(void) {
    intern_init(1024);
    Sym s = intern("stable_test");
    const char *p1 = intern_str(s);
    const char *p2 = intern_str(s);
    assert(p1 == p2);
    intern_destroy();
    printf("PASS: test_intern_stable_pointer\n");
}

void test_intern_unknown_sym(void) {
    intern_init(1024);
    assert(intern_str(0xDEADBEEF) == NULL);
    intern_destroy();
    printf("PASS: test_intern_unknown_sym\n");
}

void test_intern_lazy_grow_round_trip(void) {
    intern_init(1024);
    char buf[32];
    Sym *syms = (Sym *)malloc(LAZY_GROW_COUNT * sizeof(Sym));

    for (int i = 0; i < LAZY_GROW_COUNT; i++) {
        snprintf(buf, sizeof(buf), "grow_str_%d", i);
        syms[i] = intern(buf);
        assert(syms[i] != SYM_NULL);
    }

    for (int i = 0; i < LAZY_GROW_COUNT; i++) {
        snprintf(buf, sizeof(buf), "grow_str_%d", i);
        const char *back = intern_str(syms[i]);
        assert(back != NULL);
        assert(strcmp(back, buf) == 0);
    }

    free(syms);
    intern_destroy();
    printf("PASS: test_intern_lazy_grow_round_trip\n");
}

void test_intern_destroy_clears(void) {
    intern_init(1024);
    Sym s = intern("ephemeral");
    assert(s != SYM_NULL);
    assert(intern_str(s) != NULL);
    intern_destroy();
    assert(intern_str(s) == NULL);
    printf("PASS: test_intern_destroy_clears\n");
}
