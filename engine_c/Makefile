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
	rm -f $(OBJS) $(LIB) *.obj *.lib
	@while IFS='|' read -r exe sources; do \
	  case "$$exe" in ''|\#*) continue;; esac; \
	  exe=$$(printf '%s' "$$exe" | tr -d '\r' | tr -d ' '); \
	  rm -f "$$exe" "$$exe.exe"; \
	done < tests.txt

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

