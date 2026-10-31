# grug look at card playstats plan

grug read `card-playstats-plan.md`. grug give fire-side take. long version in that file, this the short one.

### three metric easy, grug not worried

recruited count, played count, modal choice. all come from `replay_log` grug already have. modal part need little care — some `resolve_generic` step is real choice, some just forced follow-up step, plan say filter by "action_id must be declared option_id" and grug agree, that the right filter. this part safe. build first, ship first.

### hand tracking — the expensive one, but grug agree keep it

user say clear: without this, grug cannot tell if computer recruit card and never touch again. that the whole point of post-mortem. grug agree, cut this and notebook answer wrong question.

so hand tracking stay. but grug still say respect the cost:

- replay whole game again through c engine, just to peek at hand
- do this for every seat, every step
- multiply by every game in folder

plan already build cache per game folder, keyed on file change. good. that the right fence. first time analyze folder, pay cost once. after that, cache remember. pick new folder later, only new games pay cost, old games free.

grug say: without that cache, this feature too slow to use twice. with cache, is fine. make sure cache actually get built first, not "add later" — this the part that make or break whole notebook feel snappy.

### folder picker in notebook, not separate app

good call putting picker inside notebook with ipywidgets instead of building second little app outside. one artifact, one place to open, one thing to maintain. grug like this. multi-folder select also smart because per-run config stay separate in table — mixing sims=200 run with sims=16 run into one silent blob would lie to reader.

### new dependency, five new friend join project

pandas, plotly, ipywidgets, jupyter, nbformat. none here before. plan put them in optional group, not core install. good, engine and training code not need to carry notebook weight just to run. grug approve keeping this fence up.

### what grug watch for when build happen

- decisions.jsonl not always there. code must work both way, not just happy path with telemetry on. two of three example folder grug check had no decisions.jsonl at all.
- cache key on file mtime is easy trap. if someone copy artifact folder to new machine, mtime change, cache think file new, re-pay full cost. not blocker, just grug leaving note by fire so future grug not confused why cache "not work" after `git clone` or folder copy.
- sanity check in plan (recruit count vs summary.json, modal played vs modal resolved) — keep these on by default, not flag-gated. cheap insurance, catch the "silent wrong number" demon before number end up in fancy chart looking very authoritative.

### grug verdict

plan good. three easy metric plus one hard metric plus one interactive picker, all pieces earn their place, nothing feel like decoration for decoration sake. one legit expensive part, engine handled by cache instead of avoided, that the correct answer not the lazy one.

build order grug suggest: cheap metrics and notebook shell first, prove picker and charts work end to end on small folder. then wire in hand tracking and cache. then run on real big folder, watch first run pay the toll, watch second run fly.

do that, ship it, grug happy.
