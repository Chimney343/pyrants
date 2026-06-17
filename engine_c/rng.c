#include "rng.h"

/* ──────────────────────────────────────────────────────────────────────────
 * RNG contract (D15 — accepted divergence)
 *
 * The C engine uses xoshiro256** seeded via splitmix64, while the canonical
 * Python engine uses random.Random (Mersenne Twister). Both engines use the
 * SAME shuffle seed formula — `(seed << 16) ^ counter` — and both use
 * Fisher-Yates, BUT the underlying PRNG and the index-selection primitive
 * differ:
 *   - C      : rng_randint = lo + (int)(uniform * range)   (truncation)
 *   - Python : Random._randbelow                          (rejection sampling)
 *
 * Consequence: an identical (seed, counter) pair produces a DIFFERENT deck /
 * market order in C vs Python. The C engine remains fully deterministic
 * (same seed -> same order across C runs), but it is NOT bit-identical to the
 * Python engine.
 *
 * Decision (per audit plan): an independent but deterministic C RNG is
 * acceptable. Cross-engine replay / determinism MUST NOT be assumed — no test
 * may assert that a C shuffle matches a Python shuffle for the same seed.
 * Determinism within the C engine is the only contract guaranteed here.
 * ────────────────────────────────────────────────────────────────────────── */

static uint64_t splitmix64(uint64_t *x) {
    uint64_t z = (*x += 0x9e3779b97f4a7c15ULL);
    z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ULL;
    z = (z ^ (z >> 27)) * 0x94d049bb133111ebULL;
    return z ^ (z >> 31);
}

static inline uint64_t rotl(uint64_t x, int k) {
    return (x << k) | (x >> (64 - k));
}

void rng_seed(RNG *rng, uint64_t seed) {
    uint64_t sm = seed;
    rng->s[0] = splitmix64(&sm);
    rng->s[1] = splitmix64(&sm);
    rng->s[2] = splitmix64(&sm);
    rng->s[3] = splitmix64(&sm);
    rng->counter = 0;
}

uint64_t rng_next(RNG *rng) {
    const uint64_t result = rotl(rng->s[0] + rng->s[3], 23) + rng->s[0];
    const uint64_t t = rng->s[1] << 17;
    rng->s[2] ^= rng->s[0];
    rng->s[3] ^= rng->s[1];
    rng->s[1] ^= rng->s[2];
    rng->s[0] ^= rng->s[3];
    rng->s[2] ^= t;
    rng->s[3] = rotl(rng->s[3], 45);
    rng->counter++;
    return result;
}

double rng_uniform(RNG *rng) {
    uint64_t x = rng_next(rng);
    return (x >> 11) * 0x1.0p-53;
}

int rng_randint(RNG *rng, int lo, int hi) {
    if (lo >= hi) return lo;
    return lo + (int)(rng_uniform(rng) * (double)(hi - lo));
}

void rng_shuffle(RNG *rng, uint32_t *arr, int n) {
    for (int i = n - 1; i > 0; i--) {
        int j = rng_randint(rng, 0, i + 1);
        uint32_t tmp = arr[i];
        arr[i] = arr[j];
        arr[j] = tmp;
    }
}

int rng_counter(RNG *rng) {
    return (int)rng->counter;
}
