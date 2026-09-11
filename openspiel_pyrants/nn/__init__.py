"""Neural-network training-data layer (layers 0-2 of ``docs/nn-training-data.md``).

No pyspiel import at module level: the dataset builder runs in worker
processes without OpenSpiel, so this package depends only on the C-engine
bindings and numpy.
"""
