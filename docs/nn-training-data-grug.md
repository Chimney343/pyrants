# grug guide: save game so net can learn

grug read rulebook. grug read runner. grug poke 778 meg of artifacts with stick. here what grug learn. as of 2026-09-09.

long version with tables live in `nn-training-data.md`. this the fire-side version.

### what net eat

net eat one bite per decision. each bite have four part:

- what player see (obs)
- what moves allowed (legal mask)
- what search liked (visit counts)
- who won in end (value)

that is all. everything else is garnish.

big rule: obs only have what player allowed to know. own hand yes. board yes. what enemy recruit yes, everybody saw that. enemy hand no. deck order no.

net that peek at enemy hand learn to cheat. then play like idiot when cheat taken away.

### what grug find in cave

replay.json is good. seed plus deck names plus every move. grug replay all 134 games through engine. all 134 come back with same score.

this file is the real record. keep it. guard it.

decisions.jsonl mostly good. policy field is real visit fraction. grug check 101,230 decisions. all sum to one. all times (sims minus one) give whole number. so visit counts already hiding in there.

visit_counts field is fake. always {chosen: 1}. delete it or make it real.

nothing save what player saw. only hash of it. hash cannot un-hash. but replay can rebuild it. so is fine, as long as replay stay good.

steps.jsonl is 60 percent of the bytes. net not need it. snapshot after move, no hand. fine for human with viewer. not for net.

### where demon hide

game_0000 to game_0003 at top of artifacts folder are two games wearing one coat. decisions and steps from 4-player run at 23:17. replay and summary from 2-player run earlier same day.

loader think line N of decisions match step N of replay. it does not. this smell like F-018.

fix: every run write own folder, `<time>_<run_id>/`. experiment script already do this. main runner not. fix main runner.

16 game folders have no summary.json. run got killed. no summary mean no winner mean no value label.

rule: game count only when summary.json there and say terminal. write summary last. then it also mean "done".

action ids are seat numbers, not names. id 3 mean "fourth legal move here". next state, id 3 is something else. net need name.

name is in move payload. play_card noble. deploy site_skullport. save payload dict per legal move, not just pretty string.

### what to change in runner (small)

three add, one remove. right after step_with_policy in run_ismcts.py:

```python
# forced move: search skip root, so _root_node is stale from last decision. do not read.
root = bot._root_node if len(legal_ids) > 1 else None
visit_counts = {a: c.visits for a, c in root.child_info.items()} if root else {}
q_values = {a: c.return_sum / c.visits for a, c in root.child_info.items() if c.visits} if root else {}
root_value = sum(c.return_sum for c in root.child_info.values()) / root.total_visits if root else None
```

grug test this live. root is there after step. on forced move root is old one. guard matter.

also add: schema_version, engine git sha, run folder per run, summary written last. that is whole runner change. small. good.

### do not save tensors from runner

young grug want runner write big float array per decision. grug say no.

tensor shape will change ten times before net work. every change mean re-run all search. search is expensive part. replay is cheap part.

save what cannot recompute:

- search visits and q
- seed and deck names
- final scores
- config and engine sha

rebuild what can: state, obs, tensor.

one new script replay game, encode obs for acting player, join visits and final score, write npz shards. change encoder, rerun script. no search rerun. this is whole trick.

builder also assert at every step: engine legal moves equal decisions line legal moves, same order. one assert. catch whole F-018 family forever.

### obs and action, short

obs: acting player always seat 0. four seat slots, mask for missing seat. board is 81 nodes times about 24 numbers. cards are counts per card id, 125 cards plus unknown.

card bags: my hand, my played, my discard, my inner circle, my deck bag, enemy owned bag, market row, market deck bag. plus pending card choice (which card, which op). plus scalars. about 4.8k numbers. plain mlp fine to start.

action: one fixed slot per meaning. play_card by card id, not hand index. two nobles in hand are same move, merge visits. deploy by node. assassinate by node and owner, not slot. resolve_generic split by op.

about 1.9k slots, pad to 2048. every legal move land on exactly one slot or builder scream.

value: save raw final scores per seat. compute target at build time. 2 player: tanh of diff over 40. 4 player: vector of 4, each (mine minus mean of others) over 40, clipped. can change later without touching runs.

### how much shiney rock

about 840 real decisions per 4-player game after drop forced ones. 1000 games make 0.8 million bites. enough to see if pipe work.

5 to 20 thousand games before net good enough to put back in search.

use same sims for all seats, 200 or more. 50-sim seats make mushy targets. entropy 0.50 at 50 sims, 0.19 at 400.

### grug order of work

1. fix runner: run folder, real visits, q, payloads, schema version, summary last.
2. write encoders with tests over the 120 replays. every move map. no collision. obs same before and after determinize, that is the leak test.
3. write builder. run on 120-game experiment. look at shards with eyes.
4. then train small net. not before.

grug done. club back on wall.

### as of 2026-09-11, evening

everything in "grug order of work" 1 to 3 is built. tests pass. gate hold.

but one stowaway. same commit that fix encoders also make insane_outcast not recruitable. old 134 games all played under old rule. third of them break on replay. so owner burn the cave and start clean.

new corpus: 32 games, 4 player, 200 sims every seat like grug say. 50 minutes on 16 workers. 26 thousand bites in `datasets/teacher_v3_32`. leak zero. value mean near zero. census walk all 34, zero collision.

cost now known: about 40 games per hour on this box. 1000 games is one day. 5000 is a week. plan for that.

step 4, train small net, still not started. that is the next thing. not before the 1000-game run though, 26k bites is a taste not a meal.

one red test left from stowaway, F-013 byte-identity, frozen reference has old rule in it. written down as F-034. not grug's to fix tonight.
