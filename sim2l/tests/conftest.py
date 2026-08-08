# sim2l test session fixtures.
#
# Many tests rely on the well-known default ``admin/admin`` credentials that
# ``SessionManager`` creates in dev mode. In production the credential is
# randomized (see ``SessionManager._resolve_admin_password``), so we set
# ``SIM2L_DEV_MODE=true`` for the test session here.
#
# Dev mode alone is not enough to make that hermetic: the resolution order
# prefers a *persisted* password file under ``$SIM2L_HOME/admin_password``
# (``~/.sim2l`` by default) over the dev literal, so on a developer machine
# with a real sim2l deployment every admin/admin test would fail against the
# machine's actual credential. Tests must not read (or risk writing) the
# developer's ``~/.sim2l`` at all — point SIM2L_HOME at a throwaway directory
# and drop any operator-set admin override for the duration of the session.
import os
import tempfile

os.environ["SIM2L_HOME"] = tempfile.mkdtemp(prefix="sim2l-test-home-")
os.environ.pop("SIM2L_ADMIN_PASSWORD", None)
os.environ.setdefault("SIM2L_DEV_MODE", "true")
