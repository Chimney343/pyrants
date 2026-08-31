# grug findings (small brain version)

grug read big findings.md. big findings.md have many word. grug brain smooth, cannot hold many word. grug make small version. grug write for grug. if grug forget, grug read this again.

nine finding total. four big rock (CRITICAL). two medium rock (MAJOR). three pebble (MINOR). grug explain like grug explain to smaller grug.

---

## the four big rock (fix these first, everything else wait)

### big rock 1: robot picks wrong door because doors get renumbered

grug game have "ISMCTS" robot brain. robot brain look at situation, robot brain remember "door number 3 good, robot pick door 3 next time."

problem: door number 3 not always same door!! sometime door 3 mean "recruit card." sometime door 3 mean "kill troop." door numbers get reshuffled every time robot imagines different hidden-card situation, because code LITERALLY SAYS SO in comment (grug not making this up, comment say "indices... never persist across determinizations").

so robot learn "door 3 good" from one imagined world, then walks through door 3 in DIFFERENT imagined world, robot does random unrelated thing instead. robot statistics become soup. robot get dumber, not smarter, with more thinking time.

this is worst rock. this is foundation-crack rock. house built on this rock, house fall down.

**file:** `openspiel_pyrants/action_encoding_c.py` lines 24-36, and the robot-brain library itself.

### big rock 2: dice look different but are secretly same dice

robot brain plays out many "what if" imaginary games to decide what to do. each imaginary game supposed to have its OWN random luck — own shuffled cards, own dice.

grug find: when game re-shuffles a hand mid-game (like "oops deck empty, shuffle discard pile back in"), it uses THE SAME dice/seed number every single imaginary game reaches that point. so 100 imaginary games, all imagining different hidden cards, all get IDENTICAL shuffle result once they hit that moment. like grug think he explore 100 caves but 100 caves secretly become same cave after first turn.

sneaky part: person who wrote code KNEW about this problem for ONE thing (market deck) and fixed it there, with comment explaining why. same fix just... not done for other shuffles. so grug know it not accident, grug know person just missed some spots.

**file:** `engine_c/state.c` lines 271-309 (`engine_determinize`), compare to `state.c:219-231` and `actions.c:404-412`.

### big rock 3: game has secret dice rolls robot brain never told about

game rulebook say: "if you run out of cards, shuffle your discard pile." this is a dice roll! this is random! but robot brain interface (`is_chance_node()`) only ever says "yes dice roll happening" ONE TIME, at very start of game (shuffling starting deck). every other dice roll during actual game (reshuffle, forced discard, monster card makes you discard random card) happens INVISIBLY, hidden inside a normal move, robot brain never sees it as a dice roll at all.

whitepaper (the paper explaining how robot brain SHOULD work) says: shuffling before anyone plays = ok to hide. shuffling DURING game = must show robot as real dice-roll moment. grug game breaking this rule constantly.

related to big rock 2 above — same crack, different angle.

**file:** `openspiel_pyrants/state_c.py` lines 202-210.

### big rock 4: score math broken for 3-4 player games

grug game supports 2, 3, or 4 players. default way grug run robot training is 4 PLAYERS (grug check justfile, `just ismcts` use 4 players by default!).

code declares: "scores always add up to zero, worst possible score is -400." this is LIE for 3-4 player games. real scores are victory points, victory points can't be negative, and they don't sum to zero, they sum to some big positive pile-of-points number. code just copy-pasted the 2-player math and forgot to change it for more players.

grug not 100% sure robot brain library actually USES this broken number during search (grug check, seems like maybe it doesn't, phew), but ANY other tool reading game info will get lied to. and it's just factually wrong, which grug no like.

**file:** `openspiel_pyrants/game_c.py` lines 65-75 vs `openspiel_pyrants/state_c.py` lines 171-187.

---

## the two medium rock (fix after big rocks)

### medium rock 5: rulebook say random first player, code always pick same player

board game rule book: "randomly choose who goes first." grug game code: always player #1 goes first, every single game, no dice involved anywhere. grug check whole engine, no random-first-player code exists ANYWHERE. simple bug, easy understand, easy fix, but changes game balance (going first probably good, so always-same-player-first could skew training).

**file:** `engine_c/state.c` line 99 (and a couple friends nearby).

### medium rock 6: robot brain "curiosity setting" is wrong number

robot brain has a dial called `uct_c` that controls "how much should robot try new things vs stick with what worked." the science paper this whole robot design comes from say: "we used 0.7 for every single test in this paper, that's the right number, others don't work as well." grug game code uses 1.4 instead — a generic default number some other unrelated robot design uses, not the number THIS paper says to use.

might not be end of world (grug game bigger/different than paper's test games, so maybe 1.4 fine anyway) but nobody LEFT A NOTE saying "we picked 1.4 on purpose." looks like default value nobody touched, not a real decision.

**file:** `scripts/run_ismcts.py` line 151.

---

## the three pebble (nice to know, not urgent)

- **pebble 7:** rulebook never says if discard pile is secret or face-up-on-table like most card games. code treats it as 100% secret (shuffled together with hidden deck). might be wrong, might be right, grug can't tell, rulebook just silent. someone check real physical rulebook.
- **pebble 8:** IF grug fixes big rock 3 (making shuffles visible dice-rolls to robot), the paper's method for handling dice-rolls only designed for SMALL dice (2-4 sides). grug game's shuffle-a-whole-discard-pile dice roll has WAY more than 4 sides. paper's trick might not work well here. future problem, not now problem.
- **pebble 9:** there's a setting called `shuffle_seed_count` you're supposed to be able to change, but a different number (`max_chance_outcomes`) that's supposed to match it is hardcoded and never updates. currently nobody changes that setting so nobody notices. sleeping bug, wakes up if someone touches that setting.

---

## grug tell you what to do

fix big rock 1 and big rock 2 first — they're really the SAME root problem (imagined worlds don't stay properly separate from each other) wearing two hats. once door-numbers are stable and dice-rolls are properly separate-per-imagined-world, robot brain might ACTUALLY start getting smarter with more thinking time, instead of quietly getting confused. everything else matters less until that's true.

grug done. grug go sit under tree now.
