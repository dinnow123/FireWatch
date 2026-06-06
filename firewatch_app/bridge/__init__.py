"""Bridge to the validated ``firewatch.engine``.

``adapter.generate_ensemble()`` keeps the legacy simulator's signature/output
``(n_floors, n_timesteps, rows, cols)`` but computes it with the test-covered
``firewatch.engine`` (Building/Floor/CellState + EnsembleRunner), reusing the
sample building data (``sample_data.buildings``, ``sample_data.floorplan_gen``).
"""
