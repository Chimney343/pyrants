runs = [
    dict(name='Run 1 (baseline)',    cpu=105.1, actions=48262,   decisions=104, wall=300, deepcopy=85.5, cowclone=0,    modelcalls=146700,  model_cum=86.9, validate=0,    haspresence=0,   candeploy=0,   any_s=0),
    dict(name='Run 2 (clone_fast)',  cpu=284.9, actions=880393,  decisions=134, wall=298, deepcopy=0,   cowclone=19.4, modelcalls=1768000, model_cum=36.2, validate=31.6, haspresence=11.8, candeploy=6.8, any_s=17.2),
    dict(name='Run 3 (cow fixes)',   cpu=380.8, actions=1211526, decisions=176, wall=403, deepcopy=0,   cowclone=15.8, modelcalls=911000,  model_cum=43.3, validate=29.0, haspresence=31.8, candeploy=8.8, any_s=36.7),
]

print(f"{'Metric':<28} {'Run 1':>10} {'Run 2':>10} {'Run 3':>10}")
print('-' * 58)
for k, label in [
    ('cpu', 'CPU time (s)'),
    ('wall', 'Wall time (s)'),
    ('decisions', 'Decisions'),
    ('actions', '_apply_action calls'),
]:
    vals = [f'{r[k]:>10.0f}' if k in ('decisions','actions') else f'{r[k]:>10.1f}' for r in runs]
    print(f'{label:<28} {vals[0]} {vals[1]} {vals[2]}')

print()
pa = [r['cpu']/r['actions']*1e6 for r in runs]
vals = [f'{v:>10.0f}' for v in pa]
print(f'{"us/action":<28} {vals[0]} {vals[1]} {vals[2]}')
print(f'{"(lower is better)":<28}')
print()

for k, label in [
    ('deepcopy', 'deepcopy cum (s)'),
    ('modelcalls', 'model_copy calls'),
    ('model_cum', 'model_copy cum (s)'),
    ('validate', 'validate_python (s)'),
    ('cowclone', '_cow_clone self (s)'),
    ('haspresence', 'has_presence (s)'),
    ('candeploy', '_can_deploy_to_node (s)'),
    ('any_s', 'builtins.any (s)'),
]:
    fmt = '>10.0f' if k in ('modelcalls',) else '>10.1f'
    vals = [format(r[k], fmt) for r in runs]
    print(f'{label:<28} {vals[0]:>10} {vals[1]:>10} {vals[2]:>10}')
