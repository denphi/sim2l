# sim2l test session fixtures.
#
# Many tests rely on the well-known default ``admin/admin`` credentials that
# ``SessionManager`` creates in dev mode. In production the credential is
# randomized (see ``SessionManager._resolve_admin_password``), so we set
# ``SIM2L_DEV_MODE=true`` for the test session here.
import os

os.environ.setdefault("SIM2L_DEV_MODE", "true")
