# deploy/

The declared target is GitHub Pages, static, with the committed artifacts served next to the app; see
[pages.md](pages.md). The nginx and systemd templates are kept for the alternative static host on the
machine-learning box, which is the fallback if the canonical bake outgrows what Pages serves comfortably.

The `app/` backend is dormant, so no service definition here is active.
