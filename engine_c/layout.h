#ifndef ENGINE_LAYOUT_H
#define ENGINE_LAYOUT_H

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Probe the C compiler's actual memory layout for the structs the Python
 * bindings mirror. Returns (size_t)-1 / -1 when the type or field is unknown. */
size_t engine_layout_size(const char *type_name);
long long engine_layout_offset(const char *type_name, const char *field_name);

#ifdef __cplusplus
}
#endif

#endif
