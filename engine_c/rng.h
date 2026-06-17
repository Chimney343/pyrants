#ifndef ENGINE_RNG_H
#define ENGINE_RNG_H

#include <stdint.h>

typedef struct {
    uint64_t s[4];
    uint64_t counter;
} RNG;

void rng_seed(RNG *rng, uint64_t seed);
uint64_t rng_next(RNG *rng);
double rng_uniform(RNG *rng);
int rng_randint(RNG *rng, int lo, int hi);
void rng_shuffle(RNG *rng, uint32_t *arr, int n);
int rng_counter(RNG *rng);

#endif
