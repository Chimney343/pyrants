#ifndef ENGINE_INTERN_H
#define ENGINE_INTERN_H

#include <stdint.h>

typedef uint32_t Sym;

#define SYM_NULL 0

void        intern_init(int capacity);
void        intern_destroy(void);
Sym         intern(const char *s);
Sym         intern_len(const char *s, int len);
const char *intern_str(Sym sym);
int         intern_count(void);

#endif
