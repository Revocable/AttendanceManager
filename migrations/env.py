import logging
from logging.config import fileConfig

from alembic import context
import os
import sys

# Adicione o diretório raiz do projeto ao sys.path para importar app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import db, User, Party, Guest # Importe db e seus modelos

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
fileConfig(config.config_file_name)
logger = logging.getLogger('alembic.env')

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = db.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.

# Configura a URL do banco de dados diretamente da variável de ambiente
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    raise ValueError("A variável de ambiente 'DATABASE_URL' não foi definida. Ela é essencial para a conexão com o PostgreSQL.")

# Algumas plataformas (como Heroku e versões mais antigas do Render) usam "postgres://"
# enquanto o SQLAlchemy espera "postgresql://". Esta linha garante a compatibilidade.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

config.set_main_option('sqlalchemy.url', DATABASE_URL)


def run_migrations_offline():
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    from sqlalchemy import engine_from_config
    from sqlalchemy import pool

    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True, # Importante para detectar mudanças de tipo
            # this callback is used to prevent an auto-migration from being generated
            # when there are no changes to the schema
            # reference: http://alembic.zzzcomputing.com/en/latest/cookbook.html
            process_revision_directives=process_revision_directives,
        )

        with context.begin_transaction():
            context.run_migrations()

def process_revision_directives(context, revision, directives):
    if getattr(config.cmd_opts, 'autogenerate', False):
        script = directives[0]
        if script.upgrade_ops.is_empty():
            directives[:] = []
            logger.info('No changes in schema detected.')


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()