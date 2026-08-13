# HTX metagenomic triage engine.
#
# The engine is Python 3 standard library only - no aligner, no reference database, no network,
# and NO pip install. That is a design constraint, not an accident, and it is what makes this
# image small, reproducible, and buildable on an air-gapped or elderly host.
#
# The image deliberately does NOT carry openpyxl/python-pptx. They serve `export_rules.py` and
# `build_deck.py`, which are reporting paths run by a human on a workstation, not pipeline steps -
# the WDL never calls them. Installing them cost a network fetch at build time and bought the
# image nothing, and the pip step was the ONLY part of this build that needed to spawn a thread,
# which is what broke it on CentOS 7 (see docs/howto_run_containerized.md).
#
#   docker build -t htx-triage:1.0.0 .
#   docker run --rm htx-triage:1.0.0 triage --selftest
#   docker run --rm -v "$PWD:/data" htx-triage:1.0.0 triage --outdir=/data/out /data/WBM232_en.html
FROM python:3.12-slim

LABEL org.opencontainers.image.title="htx-triage" \
      org.opencontainers.image.description="Deterministic triage of PFI metagenomic reports" \
      org.opencontainers.image.version="1.0.0" \
      org.opencontainers.image.licenses="MIT"

WORKDIR /opt/htx
# Code and rules only. No sample data, no reports - those arrive as mounted inputs, which is
# what keeps the image publishable and free of anything patient- or site-identifying.
COPY analysis/ /opt/htx/analysis/

# Fail the build if the rules are internally inconsistent. An image that ships broken rules is
# worse than no image, because the workflow will run and produce verdicts anyway.
RUN python3 /opt/htx/analysis/triage.py --selftest

# `triage` on PATH rather than an ENTRYPOINT. A python ENTRYPOINT breaks every WDL engine:
# Cromwell and miniwdl run `/bin/bash <script>` as the container COMMAND, which docker appends to
# the entrypoint, yielding `python3 triage.py /bin/bash script`. Exit 2, empty stderr, and a very
# confusing hour. A wrapper on PATH gives the workflow a clean `triage ...` command and keeps the
# interactive UX.
RUN printf '#!/bin/sh\nexec python3 /opt/htx/analysis/triage.py "$@"\n' > /usr/local/bin/triage \
    && chmod 0755 /usr/local/bin/triage

# NO `USER` DIRECTIVE, deliberately. The right uid is the engine's business, not the image's, and
# hardcoding one breaks portability in both directions:
#   - rootless docker (this dev host) maps the invoking host user to container root, so a
#     hardcoded non-root USER cannot write to its own mounted work directory;
#   - a rootful daemon running as container root writes host files the user cannot delete.
# Every WDL engine already has a policy - Cromwell runs as root, miniwdl passes --user by default
# and takes --no-outside-user to opt out - so the portable image states no preference and lets the
# engine apply its own. This was found by the container failing under miniwdl with exit 2 and an
# empty stderr, which is what a permission-denied `mkdir` in a `set -e` script looks like.
CMD ["triage", "--selftest"]
