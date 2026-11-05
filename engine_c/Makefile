# Build system for engine_c
# Supports GCC (Linux/macOS/MinGW) and MSVC (Windows)
# Usage:
#   make            - build libengine.a (GCC)
#   make test       - build and run test suite (GCC)
#   nmake /f Makefile.msvc  - build with MSVC on Windows
#
# The library and test source lists live in sources.txt and tests.txt so the
# MSVC, ASan and profiling builds cannot drift from this one.

CC      ?= gcc
CFLAGS  ?= -Wall -Wextra -std=c11 -O2 -g
AR      ?= ar
ARFLAGS ?= rcs

define newline


endef

SOURCES = $(subst $(newline), ,$(file <sources.txt))
OBJS    = $(SOURCES:.c=.o)
LIB     = libengine.a

.PHONY: all clean test

all: $(LIB)

$(LIB): $(OBJS)
	$(AR) $(ARFLAGS) $@ $^

%.o: %.c
	$(CC) $(CFLAGS) -I. -c $< -o $@

clean:
	rm -f $(OBJS) $(LIB) *.obj *.lib \
	  test_engine test_engine.exe test_view test_view.exe \
	  test_describe test_describe.exe test_generic_actions test_generic_actions.exe \
	  test_saveload test_saveload.exe test_rollout test_rollout.exe \
	  test_infostate_hash test_infostate_hash.exe test_catalog_assembly test_catalog_assembly.exe \
	  test_dt_ched test_dt_ched.exe

test: $(LIB)
	@while IFS='|' read -r exe sources; do \
	  case "$$exe" in ''|\#*) continue;; esac; \
	  $(CC) $(CFLAGS) -I. -o "$$exe" $$sources -L. -lengine -lm || exit $$?; \
	  ./"$$exe" || exit $$?; \
	done < tests.txt

# Header dependencies
$(OBJS): state.h intern.h
cJSON.o: cJSON.h
arena.o: arena.h
rng.o: rng.h
loader.o: cJSON.h rng.h arena.h
rules.o: rules.h helpers.h phases.h scoring.h moves.h

