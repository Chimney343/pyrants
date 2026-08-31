> **RESOLVED (2026-08-30)** — both demons are fixed.
>
> - **Demon one** (`!action` dead-end) now closes the book properly instead of destroy-and-NULL — `engine_c/generic_runtime.c:761-783`.
> - **Demon two** is fixed at *play time*, not by fizzling: `card_play_modal_options_viable()` (`engine_c/generic_runtime.c:1244`, called from `engine_c/rules.c:243` and `rules.c:302`) prevents playing a modal card when every option is non-viable, so the "both doors nailed shut" state is unreachable. Tests: `engine_c/tests/test_generic_actions.c:471-480`.
>
> The body below is preserved as the original hunt log.

# two demon in resolve_generic, grug hunt them down

grug run robot-brain (IS-MCTS) against own game 2026-08-28. robot-brain not dumb like grug, robot-brain try every move, even weird move grug never try. weird move wake up demon.

demon live in `engine_c/generic_runtime.c`. demon name `resolve_generic`. two demon, actually. grug find both, grug write down here so future grug (or you, tribe-mate reading this) not need re-hunt.

grug also fix small unrelated demon while poking around. tell about that too, at end.

## grug see pattern before grug see bug

big brain build two part: **one part list what move ok** (call it `legal_moves()`), **other part actually do move** (call it `apply()`). big brain say these two part must always agree. grug agree, this good rule.

but sometime big brain build part one and part two on different day, forget what other part say, and now part one say "yes this legal!!" and part two say "no, reject, get out" for **same exact move**. grug call this demon. robot-brain trust part one, try move, part two eat it, whole game crash.

grug run big test:

- 8 game, everybody play, IS-MCTS think 50 time per move → **8 of 8 game die**
- 20 game same way → **20 of 20 game die**

grug not exaggerate. every single game die. this not "rare edge case", this "front door of house on fire."

not new demon from recent determinize-fix commit (`eaacde0`) either — demon live here long time, just recent commit make robot-brain roll random dice much more often (fresh reshuffle almost every think-step), so demon wake up almost every game instead of once in blue moon.

## demon one: card finish talking but game not let card leave room

**what robot-brain see:** move `resolve_generic(action_id=None, target_id=None, selection_index=0)` — this ONLY legal move offered (`legal_moves_count=1`) — then game say no, reject.

**where demon live:**

part-one brain (`generic_runtime.c:1238-1241`) say: "card `next_action_index` gone past end of action list? ok, card done, only legal move now is empty confirm-move, here you go."

part-two brain (`generic_runtime.c:761-762`) get that exact empty confirm-move, ask "what action pending?", get NULL back (card done, same as part-one saw), and say:

```c
const CardAction *action = pending_generic_active_action(p);
if (!action) { engine_destroy(state); return NULL; }
```

grug translate: "card done? ok DESTROY EVERYTHING, return NOTHING." not helpful, part-two. very not helpful.

funny thing — two neighbor check, right below this one in same function (`765-768` focus-not-met, `769-782` gate-not-met), BOTH know what to do when stuck: call `auto_resolve_pending_generic(state, pid)`, quietly move on, no crash. grug think whoever wrote "card done" check just forget to call same helper. easy mistake, big brain make it too sometimes.

**when demon wake up:** card use `sequence` shape (not "pick option A or B" shape), and LAST action in sequence need player pick something (deploy troop where, assassinate who, play which card, etc). player pick last thing, card say "done!", game then ask ONE more empty confirm-move to officially close book — and that confirm-move always get eaten by demon.

**grug catch red-handed:** `elder_brain` card. rule say: "promote top card, then play card from inner circle." last step (`play_card`, pick which inner-circle card) need pick. grug see 4-of-20 game die exactly here.

**grug also suspect but not personally watch die:** grug search all card file for same shape (sequence card, last step need pick, not one of few special force_discard case engine already auto-handle). find 32 card total match shape, including elder_brain. only elder_brain grug see die with own eye. rest just look like same demon wearing different mask — probably die too if grug throw enough dice at them, grug just not personally throw that many dice yet.

card that share elder_brain shape (last-step op shown too, so you know what kind of "pick something" it is):

| card | last step ask you to pick... |
|---|---|
| advance_scout | supplant_troop |
| aerisi_kalinoth | recruit_card |
| balor | deploy_troops |
| black_wyrmling | assassinate_troop |
| blue_wyrmling | return_unit |
| carrion_crawler | devour_cost |
| cranium_rats | force_discard (this one NOT auto-handled, still need pick) |
| crushing_wave_cultist | deploy_troops |
| cult_fanatic | devour_cost |
| deathblade | assassinate_troop |
| doppelganger | supplant_troop |
| **elder_brain** | play_card — **grug see this one die, confirmed** |
| flesh_golem | assassinate_troop |
| gar_shatterkeel | recruit_card |
| glabrezu | assassinate_troop |
| marlos_urnrayle | recruit_card |
| mercenary_squad | deploy_troops |
| ogre_zombie | supplant_troop |
| olhydra | deploy_troops |
| quaggoth | assassinate_troop |
| rath_modar | place_spy |
| ravenous_zombies | assassinate_troop |
| skeletal_horde | deploy_troops |
| spy_master | place_spy |
| succubus | assassinate_troop |
| ulitharid | devour_cost |
| underdark_ranger | assassinate_troop |
| vampire_spawn | return_unit |
| vanifer | recruit_card |
| white_wyrmling | devour_cost |
| wraith | assassinate_troop |
| yan_c_bin | place_spy |

(grug also check: four other force_discard-last card — `chuul`, `mindwitness`, `neogi`, `umber_hulk` — engine already know how auto-finish these, no pick needed, so demon leave them alone. grug not put on list.)

## demon two: card give you choice between two door, both door nailed shut

**what robot-brain see:** move `resolve_generic(action_id='option_N', target_id='unavailable', selection_index=0)` — TWO move offered, BOTH say `target_id='unavailable'` — then both get reject.

**where demon live:**

part-one brain mark option `"unavailable"` (`generic_runtime.c:1219-1226`) when option have zero legal target — this only supposed to be paint-the-button-grey signal for tkinter viewer human look at, comment literally say "generated for UI greying-out." part-two brain reject any move wearing "unavailable" tag on purpose (`generic_runtime.c:736-743`), also on purpose, this correct — grey button not supposed to be clickable.

normally python wrapper (`openspiel_pyrants/action_encoding_c.py:32-36`) strip grey-button moves out before robot-brain ever see them. good, working as intend.

BUT — what if BOTH option grey? wrapper end up with empty list. empty legal-move-list on non-finish game state = robot-brain confuse forever, worse than crash. so wrapper say "screw it" and hand back grey-only list anyway, comment literally say "fail loudly" instead of silent-forever-stuck. grug respect the honesty. still crash though.

so real problem: **nobody teach engine what to do when card offer choice and BOTH choice impossible.** engine just shrug and let it explode.

**when demon wake up:** card give exactly two option — option A "deploy troop, nothing else", option B "assassinate white troop, nothing else" — and RIGHT NOW player barrack empty (no troop to deploy) AND no white troop anywhere on board (nothing to assassinate). both door nailed shut same moment, robot-brain forced to pick, demon eat robot-brain.

**grug hunt whole card book, this time grug confident: only three card built this exact two-door shape, and grug watch all three die:**

| card | the two nailed door | how many time grug see it die (out of 20 game) |
|---|---|---|
| kobold | deploy 1 troop *or* assassinate 1 white troop | 9 |
| ettin | deploy 3 troop *or* assassinate 2 white troop (two step) | 6 |
| weaponmaster | deploy 1 troop *or* assassinate 1 white troop | 1 |

unlike demon one, grug pretty sure this list COMPLETE. grug check every card file, no fourth card built this shape. only three, all three confirmed guilty.

## how grug catch these (for next grug who need re-catch)

```
just ismcts 30 20 42 artifacts/ismcts/card_id_probe 8 4
```

but first grug had to teach crash message to SAY which card was talking when it died — engine already know card id internally (`pending_generic.source_card_id`), just nobody wire it into error message. grug wire it in, `engine_c/bindings/c_adapter.py`, inside `apply()`. small patch, currently sitting uncommitted in tree, very useful, grug recommend keep. without it, `failures.jsonl` still show crash, just not tell you WHICH card stabbed you.

each dead game leave one line in `<output_dir>/failures.jsonl`, full python stack trace under `"error"` key.

## grug also fix different, smaller demon while walking through here (not related, but grug not liar, tell you anyway)

`CEngineAdapter.__deepcopy__` (`engine_c/bindings/c_adapter.py:44`, before grug patch) just say `return self`. this mean every time IS-MCTS say "make copy of game to test random rollout on," code secretly hand back SAME game, not copy. rollout then punch holes in real game while pretending to punch holes in fake practice game. real bug, real demon, grug fix by making it call proper C-level clone instead.

grug fix this FIRST, thought maybe this was cause of demon one and two. re-ran 8-game test after fix. still 8-of-8 dead, same two error message as before. so: good fix, real fix, worth keeping — but NOT what kill these particular 20 game. demon one and two still out there, separate, still hungry.

## what grug think should happen (grug not fix yet, grug just hunter not surgeon)

both demon need someone with big-brain game-design hat on, not just code fix:

- **demon one:** the `!action` dead-end (`generic_runtime.c:761-762`) should close the book properly (pop to `p->parent`, or fully clear `pending_generic`) instead of destroy-and-scream — copy what neighbor checks already do with `auto_resolve_pending_generic`.
- **demon two:** engine need a real answer for "both door nailed shut" — probably: card just fizzle, choice auto-close, nothing happen. but somebody check `docs/tyrants-rulebook.md` first — does fizzled card still count as "played" (cost paid, VP counted)? grug not know rule that deep, grug just hunt demon, not write law.

grug done. go greenland card kill goblin.
