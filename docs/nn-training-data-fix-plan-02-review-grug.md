# grug look at fix plan 02 after it land

grug read plan. grug read commit `23196b7`. grug run every gate self, not trust status line. here what grug find. as of 2026-09-11.

long version with tables live in `nn-training-data-fix-plan-02-review.md`. this the fire-side version.

### the four fixes: all there

seat block now turn with player. grug check slot 0 is me, slot 1 is next guy, for every seat, 3 and 4 player. is fine.

trophy deploy now key on colour, not hall slot. lich state go 23 slot to 46 slot. white troop and enemy troop no longer share one hole. good. that was the big one.

pending reader give back base dict instead of none when extra read fail. one line. `return base`. grug like one-line fix.

`just test-all` run both tree now. grug make fake justfile with exit 1 stand-in. both tree run every time, exit 1 if either sad. fixed.

six small cleanup all done too. comments say 240. manifest has all four sha. clamp now raise. metrics say none not zero. grug find nothing missing from list.

every test plan name exist. every test grug read assert real thing. 115 pass where plan say 97. ruff clean.

so far grug happy.

### then grug count games

plan say census walk 139 games. grug run full census. 141 game dir now. 95 walk. 46 skip.

46 game. one third of cave. all skip on same move: recruit insane_outcast.

why? same commit also make insane_outcast not recruitable. setup file change. engine change. rides in with fix plan like stowaway. commit message even admit it: "concurrent working-tree work".

plan say very clear: no run need repeating, replay.json is canonical. that true of plan. not true of commit.

### what stowaway cost

census coverage table. plan complain 4 of 8 custom effect branch have no live census coverage. now 7 of 8 in uncovered list. census reach one branch. six times. self_purge_to_supply had 5,122 live states. now zero. all in games that skip.

live tests cover the 7 branch. good tests. but one state each. census had thousands. gate got thinner while docs say gate got better.

dataset. 120-game sims_vs_wins cannot rebuild. setup sha not match. builder say no to all 120. only v3 dataset is quick: 2 game, 1,653 sample. that not dataset. that snack.

tests. one new fail in each tree. tests/ was 4, now 5. openspiel was 10, now 11. new one in openspiel is F-013 byte-identity gate. docstring say "must stay true through all phases". neither fail written anywhere. closure note say "targeted suite re-run". targeted. not both tree. grug see what happen there.

### the part that make grug scratch head

grug dig. engine can replay old games fine. loader.c already say: no recruitable key means recruitable true. old games meant to work.

problem is replay loader. sims_vs_wins run has no manifest.json. so loader rebuild setup from today's base_setup.json. today's file say recruitable false. loader hand engine wrong rulebook for 2026-09-02 game.

so 46 games not dead. loader just confused about what year it is. one fix in `_build_setup_json`, plus honest escape hatch for sha gate, and all 120 build at v3 again. or run fresh 120 under new rule. day of compute. either fine. picking neither is not fine.

### two small things

T2.1 "block differ between seat" check is inside `if summaries differ`. if fixture ever boring, test pass under old bug too. assert precondition. make it fail loud.

T3.5 has `assert all(len(slots) >= 1)`. set with thing in it always len one or more. that assert cannot fail. line above it real. delete this one or make it `any(len > 1)`.

### grug verdict

fix plan done. done well. every line the plan ask for is there and tested.

but stowaway change in same commit ate third of corpus, left project with no training set, and put two red tests in tree with no name. plan status say "implemented". grug say "implemented, phase 5 open".

do first: write stowaway down as finding. then decide corpus: fix loader or run fresh. then re-bake F-013 reference. then small stuff.

one commit, one story. next time stowaway ride separate.
