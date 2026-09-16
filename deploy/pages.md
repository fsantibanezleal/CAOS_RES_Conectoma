# Deploy, GitHub Pages, static replay

The product is static: the app plus the committed artifacts, with no request-time backend. The deploy
workflow is added by the unit that builds the web surface; it will build the frontend, overlay the
committed artifacts, and publish. Deployment verifies checksums and publishes existing evidence; it never
regenerates canonical results.

Setup, once: repository Settings, Pages, Source set to GitHub Actions. The custom domain is set through the
API, because the CNAME file alone does not set it for Actions deploys.

Fallback: if the measured bake is too large for Pages to serve comfortably, the same static bundle is served
by nginx on the machine-learning host instead, and the decision is recorded with the measured size.
