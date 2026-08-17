#!/usr/bin/env bash
# =============================================================================
# OBSOLETE — this script must not be run. It is a guard, not a deployment.
#
# The original contents targeted an environment that does not exist:
#   * /srv/kinjo with a virtualenv     -> production runs Docker at /opt/kinjo
#   * systemd units kinjo-*.service    -> production runs docker compose services
#   * a pinned Alembic head            -> the project moved past that revision
#
# Run against the real droplet it would fail partway through, after it had
# already started mutating state. It kept working as a *file* — executable, at
# the repository root, with the most guessable possible name — which is exactly
# how it stays dangerous. Replacing the body with this refusal is deliberate:
# deleting it would let a stale checkout or a bookmarked path resurrect the old
# version silently.
#
# The canonical deploy is scripts/deploy_locked.sh, which runs ON the droplet and
# holds an exclusive lock across the whole mutation window. See DEPLOYMENT_GUIDE.md.
# =============================================================================
set -euo pipefail

cat >&2 <<'EOF'
ERROR: deploy.sh is obsolete and will not run.

  It targets /srv/kinjo + virtualenv + systemd. Production is Docker at /opt/kinjo.

  Deploy with, from the workstation:

    git archive --format=tar -o /tmp/deploy.tar HEAD
    scp /tmp/deploy.tar <deploy-user>@<droplet>:/tmp/deploy.tar
    ssh <deploy-user>@<droplet> \
      'bash /opt/kinjo/scripts/deploy_locked.sh /tmp/deploy.tar '"$(git rev-parse HEAD)"

  First-time droplet setup:  deploy/harden-droplet.sh, then deploy/issue-cert.sh
  Full procedure:            DEPLOYMENT_GUIDE.md
EOF
exit 64  # EX_USAGE
