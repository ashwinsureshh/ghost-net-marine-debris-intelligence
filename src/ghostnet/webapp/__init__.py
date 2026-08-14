"""Deployed operator web application (PRD §9.1).

    app.py       FastAPI routes — serves artefacts, plans live, records approval
    planning.py  live prioritisation over a precomputed artefact (FR-6.1/6.2)
    store.py     artefact loading + the FR-6.4 approval record

The datasets cannot be deployed, so the workstation exports run artefacts
(``ghostnet.export``) and this server recomputes only the cheap, operator-driven
half of the pipeline. See ``frontend/`` for the browser client.
"""
