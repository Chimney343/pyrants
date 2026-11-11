#ifndef ENGINE_GENERIC_RUNTIME_H
#define ENGINE_GENERIC_RUNTIME_H

#include "state.h"

GameState *resolve_generic_execution(GameState *state, Sym player_id,
                                      const CardDefinition *card, Sym source_card_id);
GameState *auto_resolve_pending_generic(GameState *state, Sym player_id);
GameState *apply_resolve_generic_choice(GameState *state, const Move *move);
/* Returns the number of moves that exist, which can exceed max_out. At most
 * max_out are written. */
int        collect_pending_generic_choice_moves(GameState *state, Sym player_id, Move *out,
                                                unsigned char *applicable, int max_out,
                                                int applicable_only);
/* True for the UI-only placeholder moves legal_pending_generic_choice_moves
 * emits for non-viable modal options.  engine_apply refuses them, so any code
 * that applies a move drawn from engine_legal_moves() must skip these. */
int        move_is_unavailable_placeholder(const Move *move);

const CardAction *pending_generic_active_action(const PendingGenericChoiceState *p);
int action_requires_selection(const CardAction *action);
int action_focus_requirement_met(GameState *state, Sym player_id,
                                  const CardDefinition *card, Sym source_card_id,
                                  const CardAction *action);
int card_play_devour_costs_payable(const GameState *state, Sym player_id,
                                   const CardDefinition *card, int hand_index);
/* True iff at least one option of a modal/repeat card is currently viable;
 * sequence cards are always playable. False means the card may not be
 * played (every mode lacks a legal target — e.g. Vampire with no supplant
 * targets and an empty discard pile). Pure read. */
int card_play_modal_options_viable(const GameState *state, Sym player_id,
                                   const CardDefinition *card);

typedef GameState* (*ActionApplier)(GameState*, Sym, const CardDefinition*, Sym, const CardAction*, int* selection_keys, Sym* selection_values, int selection_count);
GameState *apply_generic_action(GameState *state, Sym player_id, const CardDefinition *card,
                                 Sym source_card_id, const CardAction *action,
                                 int *sel_keys, Sym *sel_vals, int sel_count);

typedef int (*SelectionGenerator)(const GameState*, Sym, const PendingGenericChoiceState*,
                                   const CardDefinition*, const CardAction*, Move*, int);
int legal_generic_target_selection_moves(const GameState *state, Sym player_id,
                                          const PendingGenericChoiceState *pending,
                                          const CardDefinition *card,
                                          const CardAction *action, Move *out, int max_out);
/* Existence probe: returns non-zero once any target exists, without counting the
 * rest. Use when only "is this list empty?" matters; the engine's internal
 * viability checks do. Public move queries use the counting variant above. */
int legal_generic_target_selection_probe(const GameState *state, Sym player_id,
                                          const PendingGenericChoiceState *pending,
                                          const CardDefinition *card,
                                          const CardAction *action, Move *scratch,
                                          int scratch_cap);

void register_generic_actions(void);
void register_selection_handlers(void);

#endif
