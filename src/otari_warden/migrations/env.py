from alembic import context
from gateway.plugins.migrations import run_plugin_env

from otari_warden.models import Base

run_plugin_env(context, Base.metadata, "warden")
