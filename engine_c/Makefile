# Build system for engine_c
# Supports GCC (Linux/macOS/MinGW) and MSVC (Windows)
# Usage:
#   make            - build libengine.a (GCC)
#   make test       - build and run test suite (GCC)
#   nmake /f Makefile.msvc  - build with MSVC on Windows

CC      ?= gcc
CFLAGS  ?= -Wall -Wextra -std=c11 -O2 -g
AR      ?= ar
ARFLAGS ?= rcs

SRCS = cJSON.c arena.c intern.c rng.c state.c moves.c rules.c helpers.c \
       phases.c scoring.c generic_runtime.c actions.c selection.c \
       player_view.c loader.c view.c describe.c saveload.c
OBJS = $(SRCS:.c=.o)
LIB  = libengine.a

.PHONY: all clean test

all: $(LIB)

$(LIB): $(OBJS)
	$(AR) $(ARFLAGS) $@ $^

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -f $(OBJS) $(LIB) test_engine test_engine.exe *.obj *.lib

test: test_engine.c $(LIB)
	$(CC) $(CFLAGS) -o test_engine test_engine.c -L. -lengine -lm
	./test_engine

# Header dependencies
$(OBJS): state.h intern.h
cJSON.o: cJSON.h
arena.o: arena.h
rng.o: rng.h
loader.o: cJSON.h rng.h arena.h
rules.o: rules.h helpers.h phases.h scoring.h moves.h
